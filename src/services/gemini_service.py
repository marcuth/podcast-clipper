import asyncio
import json
import logging
import os
import time
from typing import Any, TypedDict

import ai
from ai.providers import OpenAICompatibleProvider
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import requests

from domain import Segment

from .video_titles import (
    MAX_LONG_TITLE_LENGTH,
    MAX_SHORT_TITLE_LENGTH,
    TITLE_RULES_PROMPT,
    clean_title,
    title_problem,
)

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

FALLBACK_GEMINI_MODELS = [
    model_name.strip()
    for model_name in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-flash-latest,gemini-3.5-flash-lite"
    ).split(",")
    if model_name.strip()
]


class ClipCandidate(TypedDict):
    clip_id: int
    title: str
    hook: str
    reason: str
    start_time: float
    end_time: float
    viral_score: float


class VideoDetails(TypedDict):
    title: str
    description: str
    tags: list[str]


GEMINI_VIDEO_DETAILS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {
            "type": "STRING",
            "description": "Frase completa e autossuficiente sobre a ideia central dita no trecho (máx 60 caracteres), sem prefixo 'Corte N', sem o título do episódio e sem o nome do canal",
        },
        "description": {
            "type": "STRING",
            "description": "Descrição rica de 2 a 3 frases explicando o contexto com pergunta provocativa no final",
        },
        "tags": {
            "type": "ARRAY",
            "description": "Lista de 6 a 10 hashtags e palavras-chave relevantes",
            "items": {"type": "STRING"},
        },
    },
    "required": ["title", "description", "tags"],
}


GEMINI_CLIPS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "clips": {
            "type": "ARRAY",
            "description": "Lista de cortes virais selecionados a partir da transcrição",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "clip_id": {
                        "type": "INTEGER",
                        "description": "Número de identificação do clipe (1, 2, 3...)",
                    },
                    "title": {
                        "type": "STRING",
                        "description": "Título chamativo, curioso e viral para redes sociais (Shorts/TikTok/Reels)",
                    },
                    "hook": {
                        "type": "STRING",
                        "description": "A frase ou gancho inicial impactante falado nos primeiros 3-5 segundos",
                    },
                    "reason": {
                        "type": "STRING",
                        "description": "Justificativa narrativa e psicológica de por que este trecho prende a atenção",
                    },
                    "start_time": {
                        "type": "NUMBER",
                        "description": "Timestamp exato de início do clipe em segundos (float)",
                    },
                    "end_time": {
                        "type": "NUMBER",
                        "description": "Timestamp exato de término do clipe em segundos (float)",
                    },
                    "viral_score": {
                        "type": "NUMBER",
                        "description": "Nota estimada de potencial viral de 0.0 a 10.0",
                    },
                },
                "required": [
                    "clip_id",
                    "title",
                    "hook",
                    "reason",
                    "start_time",
                    "end_time",
                    "viral_score",
                ],
            },
        }
    },
    "required": ["clips"],
}


def get_gemini_api_key() -> str | None:
    """Retrieve Gemini API key from environment variables."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class ClipCandidateItem(BaseModel):
    clip_id: int = Field(default=1, description="Número de identificação do clipe (1, 2, 3...)")
    title: str = Field(description="Título chamativo, curioso e viral para redes sociais (Shorts/TikTok/Reels)")
    hook: str = Field(default="", description="A frase ou gancho inicial impactante falado nos primeiros 3-5 segundos")
    reason: str = Field(default="", description="Justificativa narrativa e psicológica de por que este trecho prende a atenção")
    start_time: float = Field(description="Timestamp exato de início do clipe em segundos")
    end_time: float = Field(description="Timestamp exato de término do clipe em segundos")
    viral_score: float = Field(default=8.0, description="Nota estimada de potencial viral de 0.0 a 10.0")


class ClipsResponse(BaseModel):
    clips: list[ClipCandidateItem] = Field(default_factory=list)


class VideoDetailsResponse(BaseModel):
    title: str = Field(description="Frase completa e autossuficiente sobre a ideia central dita no trecho (máx 60 caracteres), sem prefixo 'Corte N', sem o título do episódio e sem o nome do canal")
    description: str = Field(description="Descrição rica de 2 a 3 frases explicando o contexto")
    tags: list[str] = Field(default_factory=list, description="Lista de 6 a 10 hashtags relevantes")


def _call_vercel_ai_sdk(
    prompt: str,
    output_type: type[Any],
    model_name: str = DEFAULT_GEMINI_MODEL,
    api_key: str | None = None,
) -> Any:
    """Invoca o Vercel AI SDK para geração estruturada com validação via Pydantic."""
    resolved_api_key = api_key or get_gemini_api_key()
    gateway_api_key = os.environ.get("AI_GATEWAY_API_KEY")

    if gateway_api_key:
        gateway_model_name = model_name if model_name.startswith("google/") else f"google/{model_name}"
        ai_model = ai.get_model(gateway_model_name)
    elif resolved_api_key:
        provider = OpenAICompatibleProvider(
            name="google",
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key_value=resolved_api_key,
        )
        ai_model = ai.Model(id=model_name, provider=provider)
    else:
        raise ValueError("Chave de API não informada (defina GEMINI_API_KEY ou AI_GATEWAY_API_KEY).")

    async def _execute_stream():
        messages = [ai.user_message(prompt)]
        async with ai.stream(ai_model, messages, output_type=output_type) as event_stream:
            async for stream_chunk in event_stream:
                pass
            return event_stream.output

    return asyncio.run(_execute_stream())


def _call_gemini_rest(
    model_name: str,
    prompt_text: str,
    api_key: str,
    schema: dict[str, Any] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Execute structured generation request against Google Gemini REST API."""
    url = f"{GEMINI_API_BASE}/{model_name}:generateContent?key={api_key}"

    generation_config: dict[str, Any] = {
        "temperature": 0.2,
        "responseMimeType": "application/json",
    }
    if schema:
        generation_config["responseSchema"] = schema

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_text}],
            }
        ],
        "generationConfig": generation_config,
    }

    response = requests.post(url, json=payload, timeout=timeout_seconds)

    if response.status_code != 200:
        error_details = response.text
        try:
            error_response = response.json()
            error_details = error_response.get("error", {}).get("message", error_details)
        except Exception:
            pass
        raise RuntimeError(f"Gemini API error ({response.status_code}): {error_details}")

    response_json = response.json()
    candidates = response_json.get("candidates", [])

    if not candidates:
        raise RuntimeError(f"Gemini API returned no candidates: {response_json}")

    content_parts = candidates[0].get("content", {}).get("parts", [])

    if not content_parts:
        raise RuntimeError(f"Gemini candidate has no content parts: {candidates[0]}")

    text_output = content_parts[0].get("text", "").strip()

    return json.loads(text_output)


def select_clips_with_gemini(
    formatted_transcript: str,
    video_title: str,
    min_duration: float = 20.0,
    max_duration: float = 85.0,
    max_clips: int = 8,
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    channel_name: str = "",
    video_description: str = "",
) -> list[ClipCandidate]:
    """Analyzes a full timestamped transcript using Gemini and returns structured viral clip suggestions.

    Args:
        formatted_transcript: Transcription text formatted with timestamp markers.
        video_title: Title of the original podcast/video for thematic context.
        min_duration: Minimum clip duration in seconds.
        max_duration: Maximum clip duration in seconds.
        max_clips: Maximum number of clips to select.
        api_key: Optional API key override; defaults to GEMINI_API_KEY environment variable.
        model: Gemini model identifier.
        channel_name: Optional channel or host name for context.
        video_description: Optional episode description/synopsis for context.

    Returns:
        A list of parsed ClipCandidate dictionaries matching GEMINI_CLIPS_SCHEMA.
    """
    resolved_api_key = api_key or get_gemini_api_key()
    if not resolved_api_key:
        raise ValueError(
            "GEMINI_API_KEY não foi encontrada nas variáveis de ambiente. "
            "Configure GEMINI_API_KEY no arquivo .env para usar a seleção por IA."
        )

    prompt = f"""Você é o editor-chefe e estrategista sênior de cortes virais para YouTube Shorts, TikTok e Instagram Reels.
Sua missão é analisar a transcrição completa abaixo e selecionar os {max_clips} MELHORES MOMENTOS com altíssimo potencial de retenção, compartilhamento e debate.

CONTEXTO DO EPISÓDIO ORIGINAL:
- Título do Podcast: "{video_title}"
- Canal / Host / Participante: {channel_name or 'Podcast'}
- Sinopse do Episódio: {video_description[:450] if video_description else 'N/A'}
- Formato: Conversa dinâmica entre apresentador e convidados.

DIRETRIZ DE OURO PARA TÍTULOS (ESTRITAMENTE ANTI-GENÉRICO):
- É TERMINANTEMENTE PROIBIDO criar títulos genéricos, clichês ou vazios como:
  'O segredo de...', 'Você não vai acreditar', 'A verdade sobre o sucesso', 'Isso mudou tudo', 'Não faça isso' ou 'Dica imperdível'.
- O título DEVE ser ancorado na realidade da fala: cite a pessoa, entidade, número, analogia, técnica ou situação concreta dita no trecho.
- Exemplo excelente: 'Por que o médico proibiu creatina com café' / 'O erro de 10 milhões no Shark Tank' / 'Como ele negociou a dívida do zero'.
- Exemplo péssimo: 'O segredo que ninguém te contou!' / 'Veja o que aconteceu'.

{TITLE_RULES_PROMPT}

REGRAS RÍGIDAS DE SELEÇÃO DOS CORTES:
1. DURAÇÃO: Cada clipe deve ter OBRIGATORIAMENTE entre {min_duration:.0f} e {max_duration:.0f} segundos (end_time - start_time).
2. GANCHO IMEDIATO (HOOK): O início (start_time) deve coincidir com uma fala de alto impacto, pergunta provocativa, afirmação surpreendente ou início de uma história forte. NUNCA comece no meio de uma frase solta que dependa de explicações anteriores.
3. CONCLUSÃO COMPLETA (SEM CORTE ABRUPTO): O final (end_time) deve ser após o fechamento da ideia, punchline ou lição. NUNCA corte a pessoa no meio de uma frase ou antes da resolução.
4. DIVERSIDADE DE MOMENTOS: Não escolha trechos sobrepostos ou repetidos. Espalhe os cortes pelos momentos mais ricos do episódio.
5. PRECISÃO DE TIMESTAMPS: Use os timestamps em segundos informados na transcrição para definir start_time e end_time com precisão decimal.

ESTRUTURA DE RESPOSTA OBRIGATÓRIA (JSON puro, conforme schema):
Para cada clipe retorne:
- clip_id: número inteiro sequencial (1, 2, 3...)
- title: Título ultra específico, magnético e contextualizado (máx 60 caracteres)
- hook: A primeira frase falada no clipe
- reason: Explicação contextualizada de por que este trecho específico do episódio tem alta retenção
- start_time: Segundo inicial exato (número decimal, ex: 145.2)
- end_time: Segundo final exato (número decimal, ex: 205.8)
- viral_score: Nota de 0.0 a 10.0 baseada em retenção e valor do conteúdo

TRANSCRIÇÃO COMPLETA DO VÍDEO (com timestamps de cada trecho):
\"\"\"
{formatted_transcript}
\"\"\"
"""

    models_to_try = [model] + [
        fallback_model for fallback_model in FALLBACK_GEMINI_MODELS if fallback_model != model
    ]
    last_error: Exception | None = None

    for candidate_model_name in models_to_try:
        try:
            logger.info(f"Chamando Vercel AI SDK ({candidate_model_name}) para seleção estruturada de clipes...")
            sdk_response: ClipsResponse = _call_vercel_ai_sdk(
                prompt=prompt,
                output_type=ClipsResponse,
                model_name=candidate_model_name,
                api_key=resolved_api_key,
            )

            if sdk_response and sdk_response.clips:
                valid_clips: list[ClipCandidate] = []
                for candidate_clip in sdk_response.clips:
                    valid_clips.append(
                        {
                            "clip_id": candidate_clip.clip_id,
                            "title": clean_title(candidate_clip.title, MAX_SHORT_TITLE_LENGTH),
                            "hook": candidate_clip.hook.strip(),
                            "reason": candidate_clip.reason.strip(),
                            "start_time": candidate_clip.start_time,
                            "end_time": candidate_clip.end_time,
                            "viral_score": candidate_clip.viral_score,
                        }
                    )

                logger.info(
                    f"Vercel AI SDK ({candidate_model_name}) retornou {len(valid_clips)} sugestões estruturadas de clipes."
                )
                return valid_clips

        except Exception as sdk_error:
            logger.warning(
                f"Tentativa via Vercel AI SDK falhou ({candidate_model_name}): {sdk_error}. Tentando fallback REST..."
            )

            try:
                data = _call_gemini_rest(
                    model_name=candidate_model_name,
                    prompt_text=prompt,
                    api_key=resolved_api_key,
                    schema=GEMINI_CLIPS_SCHEMA,
                )

                clips_raw = data.get("clips", [])
                logger.info(
                    f"Gemini REST ({candidate_model_name}) retornou com sucesso {len(clips_raw)} sugestões estruturadas de clipes."
                )

                valid_clips = []
                for raw_clip in clips_raw:
                    try:
                        start_seconds = float(raw_clip["start_time"])
                        end_seconds = float(raw_clip["end_time"])
                        duration_seconds = end_seconds - start_seconds
                        if duration_seconds < min_duration * 0.7 or duration_seconds > max_duration * 1.3:
                            logger.debug(
                                f"Ajustando ou descartando clipe fora dos limites de duração: {duration_seconds:.1f}s"
                            )
                        valid_clips.append(
                            {
                                "clip_id": int(raw_clip.get("clip_id", len(valid_clips) + 1)),
                                "title": clean_title(raw_clip.get("title", ""), MAX_SHORT_TITLE_LENGTH),
                                "hook": str(raw_clip.get("hook", "")).strip(),
                                "reason": str(raw_clip.get("reason", "")).strip(),
                                "start_time": start_seconds,
                                "end_time": end_seconds,
                                "viral_score": float(raw_clip.get("viral_score", 8.0)),
                            }
                        )
                    except Exception as parse_error:
                        logger.warning(f"Erro ao validar item de clipe do Gemini: {parse_error}")

                if valid_clips:
                    return valid_clips

            except Exception as rest_error:
                logger.warning(f"Falha ao chamar Gemini com modelo '{candidate_model_name}': {rest_error}")
                last_error = rest_error

    if last_error:
        raise last_error
    return []


def select_long_clips_with_gemini(
    formatted_transcript: str,
    video_title: str,
    min_duration: float = 180.0,
    max_duration: float = 1200.0,
    max_clips: int = 3,
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    channel_name: str = "",
    video_description: str = "",
) -> list[ClipCandidate]:
    """Analyzes a full timestamped transcript using Gemini and selects long horizontal podcast clips (up to 20 minutes).

    Focuses on comprehensive thematic discussions, deep-dives, debates, or complete narratives
    that make standalone horizontal YouTube video clips.
    """
    resolved_api_key = api_key or get_gemini_api_key()
    if not resolved_api_key:
        raise ValueError(
            "GEMINI_API_KEY não foi encontrada nas variáveis de ambiente. "
            "Configure GEMINI_API_KEY no arquivo .env para usar a seleção por IA."
        )

    minimum_minutes = int(min_duration // 60)
    maximum_minutes = int(max_duration // 60)

    prompt = f"""Você é um produtor e editor executivo sênior de canais de cortes de podcast no YouTube (formato 16:9 tradicional).
Sua missão é analisar a transcrição completa abaixo e identificar os {max_clips} MELHORES TEMAS / BLOCOS DE CONVERSA COMPLETOS para cortes longos independentes no YouTube.

CONTEXTO DO EPISÓDIO ORIGINAL:
- Título do Podcast: "{video_title}"
- Canal / Host / Participante: {channel_name or 'Podcast'}
- Sinopse: {video_description[:450] if video_description else 'N/A'}

REGRAS RÍGIDAS DE SELEÇÃO DE CORTES LONGOS:
1. DURAÇÃO: Cada clipe longo deve ter entre {minimum_minutes} e {maximum_minutes} minutos (aproximadamente entre {min_duration:.0f}s e {max_duration:.0f}s).
2. COESÃO TEMÁTICA TOTAL: O corte deve cobrir um assunto, debate, história ou ensinamento do início ao fim.
   - NUNCA comece no meio de um assunto que já estava sendo discutido.
   - O início (start_time) deve ser exatamente onde o tema é introduzido ou uma nova pergunta é feita.
   - O final (end_time) deve ser onde a discussão sobre aquele tema se conclui, antes de mudarem de assunto.
3. TÍTULO PARA YOUTUBE: Deve ser um título real, informativo e magnético para vídeo de corte no YouTube (ex: "O que ninguém te conta sobre investimentos no Brasil" / "A história bizarra de como ele foi preso por engano").
4. PRECISÃO DE TIMESTAMPS: Use os timestamps em segundos informados na transcrição para definir start_time e end_time com precisão decimal.

{TITLE_RULES_PROMPT}

ESTRUTURA DE RESPOSTA OBRIGATÓRIA (JSON puro, conforme schema):
Para cada corte longo retorne:
- clip_id: número inteiro sequencial (1, 2, 3...)
- title: Título completo e atrativo para vídeo no YouTube (máx 75 caracteres)
- hook: Resumo da introdução ou pergunta que abre o tema
- reason: Justificativa do porquê esse tema gera retenção e engajamento
- start_time: Segundo inicial exato (número decimal, ex: 340.5)
- end_time: Segundo final exato (número decimal, ex: 1120.0)
- viral_score: Nota de 0.0 a 10.0 baseada na relevância e interesse do tema

TRANSCRIÇÃO COMPLETA DO VÍDEO (com timestamps de cada trecho):
\"\"\"
{formatted_transcript}
\"\"\"
"""

    models_to_try = [model] + [
        fallback_model for fallback_model in FALLBACK_GEMINI_MODELS if fallback_model != model
    ]
    last_error: Exception | None = None

    for candidate_model_name in models_to_try:
        try:
            logger.info(
                f"Chamando Vercel AI SDK ({candidate_model_name}) para seleção de cortes longos..."
            )
            try:
                sdk_response: ClipsResponse = _call_vercel_ai_sdk(
                    prompt=prompt,
                    output_type=ClipsResponse,
                    model_name=candidate_model_name,
                    api_key=resolved_api_key,
                )

                if sdk_response and sdk_response.clips:
                    valid_clips: list[ClipCandidate] = []

                    for candidate_clip in sdk_response.clips:
                        valid_clips.append(
                            {
                                "clip_id": candidate_clip.clip_id,
                                "title": clean_title(candidate_clip.title, MAX_LONG_TITLE_LENGTH),
                                "hook": candidate_clip.hook.strip(),
                                "reason": candidate_clip.reason.strip(),
                                "start_time": candidate_clip.start_time,
                                "end_time": candidate_clip.end_time,
                                "viral_score": candidate_clip.viral_score,
                            }
                        )

                    logger.info(
                        f"Vercel AI SDK ({candidate_model_name}) retornou {len(valid_clips)} cortes longos com sucesso."
                    )
                    return valid_clips

            except Exception as sdk_error:
                logger.warning(
                    f"Tentativa via Vercel AI SDK falhou ({candidate_model_name}): {sdk_error}. Tentando fallback REST..."
                )

            data = _call_gemini_rest(
                model_name=candidate_model_name,
                prompt_text=prompt,
                api_key=resolved_api_key,
                schema=GEMINI_CLIPS_SCHEMA,
            )

            clips_raw = data.get("clips", [])
            logger.info(f"Gemini REST ({candidate_model_name}) retornou {len(clips_raw)} sugestões de cortes longos.")

            valid_clips = []

            for raw_clip in clips_raw:
                try:
                    start_seconds = float(raw_clip["start_time"])
                    end_seconds = float(raw_clip["end_time"])
                    valid_clips.append(
                        {
                            "clip_id": int(raw_clip.get("clip_id", len(valid_clips) + 1)),
                            "title": clean_title(raw_clip.get("title", ""), MAX_LONG_TITLE_LENGTH),
                            "hook": str(raw_clip.get("hook", "")).strip(),
                            "reason": str(raw_clip.get("reason", "")).strip(),
                            "start_time": start_seconds,
                            "end_time": end_seconds,
                            "viral_score": float(raw_clip.get("viral_score", 8.5)),
                        }
                    )

                except Exception as parse_error:
                    logger.warning(f"Erro ao validar item de corte longo do Gemini: {parse_error}")

            if valid_clips:
                return valid_clips

        except Exception as rest_error:
            logger.warning(
                f"Falha ao chamar Gemini com modelo '{candidate_model_name}' para cortes longos: {rest_error}"
            )
            last_error = rest_error

    if last_error:
        raise last_error

    return []


_DETAILS_ATTEMPTS_PER_MODEL = 3
_retired_models: set[str] = set()  # models the API answered 404 for during this run; not worth retrying per clip
_RETRY_BACKOFF_SECONDS = (3, 8)  # waits between attempts; 503 'high demand' spikes usually clear in seconds
_TRANSIENT_ERROR_MARKERS = ("429", "500", "502", "503", "504", "timeout", "timed out", "rate", "overload", "unavailable", "connection")


def _is_transient(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _is_quota_error(error: Exception) -> bool:
    """429 means this model's quota is spent; retrying it (or its REST twin) only burns more quota."""
    message = str(error).lower()
    return "429" in message or "resource_exhausted" in message or "quota" in message


def _clean_tags(raw_tags: list[Any]) -> list[str]:
    return [str(tag_item).strip().lstrip("#") for tag_item in raw_tags if str(tag_item).strip()]


def _request_video_details(prompt: str, model_name: str, api_key: str) -> VideoDetails:
    """One generation attempt: Vercel AI SDK first, then the REST API."""
    logger.info(f"Chamando Vercel AI SDK ({model_name}) para gerar título, descrição e tags...")

    try:
        sdk_response: VideoDetailsResponse = _call_vercel_ai_sdk(
            prompt=prompt,
            output_type=VideoDetailsResponse,
            model_name=model_name,
            api_key=api_key,
        )

        if sdk_response and sdk_response.title:
            return VideoDetails(
                title=sdk_response.title.strip(),
                description=sdk_response.description.strip(),
                tags=_clean_tags(sdk_response.tags),
            )
    except Exception as sdk_error:
        if _is_quota_error(sdk_error):
            raise

        logger.warning(f"Tentativa via Vercel AI SDK falhou ({model_name}): {sdk_error}. Tentando fallback REST...")

    data = _call_gemini_rest(
        model_name=model_name,
        prompt_text=prompt,
        api_key=api_key,
        schema=GEMINI_VIDEO_DETAILS_SCHEMA,
    )

    return VideoDetails(
        title=str(data.get("title", "")).strip(),
        description=str(data.get("description", "")).strip(),
        tags=_clean_tags(data.get("tags", [])),
    )


def generate_video_details(
    long_video_title: str,
    segments: list[Segment],
    channel_name: str = "",
    video_description: str = "",
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
) -> VideoDetails:
    """
    Gera título contextualizado, descrição e tags para um corte usando a API Gemini.

    Títulos inválidos (vazios, "Corte N - ...", cópia do título do episódio, cortados no meio
    de uma frase) são rejeitados e o Gemini é chamado de novo informando o motivo. Erros
    transitórios (429/5xx/timeout) são repetidos com espera crescente.

    Raises:
        Exception: se nenhum modelo devolver detalhes válidos; o chamador deve usar
            ``build_fallback_details``.
    """
    resolved_api_key = api_key or get_gemini_api_key()

    if not resolved_api_key:
        raise ValueError(
            "GEMINI_API_KEY não foi encontrada nas variáveis de ambiente. "
            "Configure GEMINI_API_KEY no arquivo .env para gerar detalhes com IA."
        )

    full_text = "\n".join(segment.text for segment in segments)

    prompt = f"""Você é um estrategista de conteúdo viral e copywriter sênior para redes sociais (TikTok, Reels, Shorts).
Sua função é criar títulos magnéticos, descrições ricas em contexto e tags precisas para cortes de podcasts.

DIRETRIZ CRÍTICA DE OURO (ESTRITAMENTE ANTI-GENÉRICO):
NUNCA crie títulos vagos, clichês ou genéricos como 'O segredo revelado', 'Você não vai acreditar', 'A verdade sobre o sucesso', 'Isso mudou tudo' ou 'Dica incrível'.
O título e a descrição DEVEM ancorar-se no que é DITO neste trecho, citando nomes específicos, entidades, fatos, dilemas, números ou ideias centrais.

CONTEXTO DO EPISÓDIO ORIGINAL (use apenas para entender o cenário; NÃO reaproveite este título):
- Título do Podcast/Episódio: "{long_video_title}"
- Canal / Host / Participante: {channel_name or 'Podcast'}
- Sinopse do Episódio: {video_description[:500] if video_description else 'N/A'}

TRANSCRIÇÃO DO CORTE:
\"\"\"
{full_text}
\"\"\"

{TITLE_RULES_PROMPT}

INSTRUÇÕES OBRIGATÓRIAS:
1. TÍTULO (máximo {MAX_SHORT_TITLE_LENGTH} caracteres, seguindo as regras absolutas acima):
   - Seja ultra específico sobre o ponto central dito neste trecho.
   - Desperte curiosidade honesta sem fórmulas genéricas ou clickbait falso.
   - Exemplos excelentes: 'Por que o médico proibiu creatina com café' / 'O erro de 10 milhões no Shark Tank' / 'A intuição de Carluxo por trás do fenômeno Bolsonaro'.
   - Exemplos péssimos: 'O segredo que ninguém te contou!' / 'Veja isso agora!' / 'Corte 1 - Ao vivo com Fulano e Dr. Ciclan' / 'Ao vivo com Fulano e Dr. Ci'.

2. DESCRIÇÃO (2 a 3 frases envolventes):
   - Situe o espectador sobre quem está conversando e qual a reflexão central do trecho (o episódio é "{long_video_title}").
   - Resuma a lição ou ponto de vista de forma inteligente.
   - Finalize com uma pergunta provocativa para gerar comentários e debate.
   - NUNCA use frases prontas como 'Trecho imperdível' ou 'Deixe seu like e comentário'.

3. TAGS (6 a 10 tags):
   - Misture o nome do podcast/canal, temas centrais do corte e palavras-chave que as pessoas buscam no nicho.
"""

    models_to_try = [model] + [
        fallback_model for fallback_model in FALLBACK_GEMINI_MODELS if fallback_model != model
    ]
    models_to_try = [name for name in models_to_try if name not in _retired_models] or models_to_try
    last_error: Exception | None = None

    for candidate_model_name in models_to_try:
        feedback = ""

        for attempt in range(_DETAILS_ATTEMPTS_PER_MODEL):
            try:
                details = _request_video_details(prompt + feedback, candidate_model_name, resolved_api_key)
            except Exception as request_error:
                last_error = request_error
                logger.warning(f"Falha ao gerar detalhes com Gemini no modelo '{candidate_model_name}': {request_error}")

                if "404" in str(request_error):
                    _retired_models.add(candidate_model_name)
                    break

                if _is_quota_error(request_error):
                    break  # quota is per model: go straight to the next one

                if _is_transient(request_error) and attempt < _DETAILS_ATTEMPTS_PER_MODEL - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
                    continue

                break

            details["title"] = clean_title(details["title"], MAX_SHORT_TITLE_LENGTH)
            problem = title_problem(details["title"], long_video_title, MAX_SHORT_TITLE_LENGTH)

            if problem is None:
                return details

            logger.warning(
                f"Título rejeitado ({candidate_model_name}, tentativa {attempt + 1}): '{details['title']}' {problem}."
            )
            last_error = ValueError(f"Gemini retornou um título inválido: '{details['title']}' ({problem})")
            feedback = (
                f"\n\nATENÇÃO: o título anterior \"{details['title']}\" foi REJEITADO porque {problem}. "
                "Gere um título COMPLETAMENTE DIFERENTE seguindo TODAS as regras absolutas."
            )

    raise last_error or RuntimeError("O Gemini não retornou detalhes válidos para o corte.")

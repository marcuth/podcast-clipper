import asyncio
import json
import logging
import os
from typing import Any, TypedDict

import ai
from ai.providers import OpenAICompatibleProvider
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import requests

from domain import Segment

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

FALLBACK_GEMINI_MODELS = [
    model_name.strip()
    for model_name in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-flash-latest,gemini-2.5-flash-lite"
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
            "description": "Título magnético, ultra específico e contextualizado para redes sociais (máx 60 caracteres)",
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
    title: str = Field(description="Título contextualizado, atrativo e de alto impacto (máx 60 caracteres)")
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
                            "title": candidate_clip.title.strip(),
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
                                "title": str(raw_clip.get("title", "")).strip(),
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
                                "title": candidate_clip.title.strip(),
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
                            "title": str(raw_clip.get("title", "")).strip(),
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


def generate_video_details(
    long_video_title: str,
    segments: list[Segment],
    channel_name: str = "",
    video_description: str = "",
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
) -> VideoDetails:
    """Gera título contextualizado, descrição e tags para um corte usando a API Gemini."""
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
O título e a descrição DEVEM ancorar-se no contexto real do episódio, citando nomes específicos, entidades, fatos, dilemas, números ou ideias centrais abordadas na conversa.

CONTEXTO DO EPISÓDIO ORIGINAL:
- Título do Podcast/Episódio: "{long_video_title}"
- Canal / Host / Participante: {channel_name or 'Podcast'}
- Sinopse do Episódio: {video_description[:500] if video_description else 'N/A'}

TRANSCRIÇÃO DO CORTE:
\"\"\"
{full_text}
\"\"\"

INSTRUÇÕES OBRIGATÓRIAS:
1. TÍTULO (máximo 60 caracteres):
   - Seja ultra específico sobre o ponto central dito neste trecho.
   - Cite pessoas, números, métodos ou conflitos reais abordados no áudio.
   - Desperte curiosidade honesta sem fórmulas genéricas ou clickbait falso.
   - Exemplo excelente: 'Por que o médico proibiu creatina com café' / 'O erro de 10 milhões no Shark Tank'.
   - Exemplo péssimo: 'O segredo que ninguém te contou!' / 'Veja isso agora!'.

2. DESCRIÇÃO (2 a 3 frases envolventes):
   - Situe o espectador sobre quem está conversando e qual a reflexão central no episódio "{long_video_title}".
   - Resuma a lição ou ponto de vista de forma inteligente.
   - Finalize com uma pergunta provocativa para gerar comentários e debate.

3. TAGS (6 a 10 tags):
   - Misture o nome do podcast/canal, temas centrais do corte e palavras-chave que as pessoas buscam no nicho.
"""

    models_to_try = [model] + [
        fallback_model for fallback_model in FALLBACK_GEMINI_MODELS if fallback_model != model
    ]
    last_error: Exception | None = None

    for candidate_model_name in models_to_try:
        try:
            logger.info(
                f"Chamando Vercel AI SDK ({candidate_model_name}) para gerar título, descrição e tags..."
            )

            sdk_response: VideoDetailsResponse = _call_vercel_ai_sdk(
                prompt=prompt,
                output_type=VideoDetailsResponse,
                model_name=candidate_model_name,
                api_key=resolved_api_key,
            )

            if sdk_response and sdk_response.title:
                clean_tags = [
                    str(tag_item).strip().lstrip("#")
                    for tag_item in sdk_response.tags
                    if str(tag_item).strip()
                ]

                return VideoDetails(
                    title=sdk_response.title.strip(),
                    description=sdk_response.description.strip(),
                    tags=clean_tags,
                )
        except Exception as sdk_error:
            logger.warning(
                f"Tentativa via Vercel AI SDK falhou ({candidate_model_name}): {sdk_error}. Tentando fallback REST..."
            )

            try:
                data = _call_gemini_rest(
                    model_name=candidate_model_name,
                    prompt_text=prompt,
                    api_key=resolved_api_key,
                    schema=GEMINI_VIDEO_DETAILS_SCHEMA,
                )

                raw_tags = data.get("tags", [])
                clean_tags = [
                    str(tag_item).strip().lstrip("#")
                    for tag_item in raw_tags
                    if str(tag_item).strip()
                ]

                return VideoDetails(
                    title=str(data.get("title", "")).strip(),
                    description=str(data.get("description", "")).strip(),
                    tags=clean_tags,
                )

            except Exception as rest_error:
                logger.warning(
                    f"Falha ao gerar detalhes com Gemini no modelo '{candidate_model_name}': {rest_error}"
                )
                last_error = rest_error

    if last_error:
        raise last_error

    return VideoDetails(
        title=long_video_title[:60],
        description=video_description[:200] if video_description else "Corte extraído do podcast.",
        tags=["podcast", "cortes", "shorts"],
    )

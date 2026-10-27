import base64
import json
import logging
from typing import Any, Callable

import cv2
import numpy as np

from services.gemini_service import get_gemini_api_key

try:
    from google import genai
    from google.genai import types
    from google.genai._gaos.utils.retries import RetryConfig
    HAVE_GOOGLE_GENAI = True
except Exception:
    HAVE_GOOGLE_GENAI = False
    types = None  # type: ignore
    RetryConfig = None  # type: ignore

logger = logging.getLogger(__name__)


def generate_fallback_hook(title: str) -> str:
    """Generate punchy 2-4 word fallback hook text from video title."""
    clean = title.replace("-", " ").replace(":", " ").replace("|", " ")
    words = [w.upper() for w in clean.split() if len(w) > 3 and w.lower() not in ("sobre", "como", "porque", "para", "quem")]
    if len(words) >= 3:
        return f"{words[0]} {words[1]} {words[2]}!"
    elif len(words) >= 2:
        return f"{words[0]} {words[1]}!"
    return "MOMENTO INÉDITO!"


def ask_gemini_thumbnail_strategy(
    frame: np.ndarray,
    video_title: str,
    clip_context: str = "",
    faces: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model: str = "gemini-3.8-flash",
) -> dict[str, Any]:
    """Call Gemini to generate explosive high-CTR thumbnail text, badge and color strategy using google-genai SDK."""
    api_key = api_key or get_gemini_api_key()
    faces = faces or []

    if not api_key:
        logger.warning("GEMINI_API_KEY não disponível. Usando estratégia heurística para thumbnail.")
        return {
            "hook_text": generate_fallback_hook(video_title),
            "badge_text": "DESTAQUE",
            "color": "#FFE500",
            "placement": "top-left",
        }

    # Encode frame to lightweight JPEG
    resized = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 80])

    face_hint = f"{len(faces)} pessoas visíveis na imagem."
    prompt = f"""
Você é o maior especialista em Thumbnails virais de alta conversão (High CTR) para Podcasts e Cortes no YouTube.
Analise a imagem da cena e o contexto do vídeo:
- Título do corte: "{video_title}"
- Contexto da fala: "{clip_context[:250]}"
- Pessoas na cena: {face_hint}

Crie a estratégia visual perfeita para a Thumbnail:
1. "hook_text": Uma frase CURTÍSSIMA de 2 a 4 palavras de ALTÍSSIMO IMPACTO e curiosidade (EM MAIÚSCULAS). Ex: "450 NÃO LEEM?!", "REVELOU O SEGREDO!", "VOTAM SEM SABER!", "BASTIDOR EXPOSTO!". Não use títulos longos.
2. "badge_text": Uma única palavra em maiúsculas para um selo de contexto (ex: "EXPOSTO", "URGENTE", "BASTIDORES", "POLÍTICA", "CHOCANTE").
3. "color": Cor em código HEX para o texto principal com contraste máximo contra fundo escuro (ex: "#FFE500" para amarelo ouro de alta conversão, "#FF2A2A" para vermelho alerta, ou "#00FFAA" para verde neon).
4. "placement": Posição ideal na imagem onde há mais espaço vazio para o texto sem cobrir os rostos dos participantes ("top-left", "bottom-left", "top-right", "bottom-right", "center-top").

Retorne APENAS um objeto JSON válido com essas 4 propriedades.
"""

    if HAVE_GOOGLE_GENAI:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=buffer.tobytes(), mime_type="image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            raw_text = response.text.strip()
            result = json.loads(raw_text)
            logger.info(f"Gemini gerou estratégia de thumbnail: '{result.get('hook_text')}' ({result.get('color')})")
            return result
        except Exception as exc:
            logger.warning(f"Exceção ao chamar Gemini via SDK para estratégia de thumbnail: {exc}")

    return {
        "hook_text": generate_fallback_hook(video_title),
        "badge_text": "EXCLUSIVO",
        "color": "#FFE500",
        "placement": "top-left",
    }


def try_gemini_image_generation(
    frame_bgr: np.ndarray,
    prompt: str,
    api_key: str | None = None,
    model: str = "models/gemini-3.1-flash-lite-image",
    on_log: Callable[[str, str], None] | None = None,
) -> np.ndarray | None:
    """Attempt multimodal AI generation/editing with Gemini Image models (Nano Banana).

    Uses client.interactions.create with models/gemini-3.1-flash-lite-image to instruct
    Gemini to render the hook text, badge, and visual enhancements directly on the image.
    Zero text insertion via Pillow: all typography is rendered by Gemini AI.
    Gracefully falls back if quota exceeded (429) or billing not yet enabled on Google AI Studio.
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        elif level == "warning":
            logger.warning(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    api_key = api_key or get_gemini_api_key()
    if not api_key:
        return None

    if not HAVE_GOOGLE_GENAI:
        _log("warning", "SDK google-genai não disponível. Não é possível chamar modelo de imagem Gemini.")
        return None

    primary_model = model if model.startswith("models/") else f"models/{model}"
    candidate_models = [
        primary_model,
        "models/gemini-3.1-flash-lite-image",
        "models/gemini-3.1-flash-image",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

    # Resize frame to balanced resolution for API payload
    resized = cv2.resize(frame_bgr, (960, 540), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 86])
    b64_image = base64.b64encode(buffer).decode("utf-8")

    try:
        client = genai.Client(api_key=api_key)
        if RetryConfig and hasattr(client, "interactions") and hasattr(client.interactions, "sdk_configuration"):
            client.interactions.sdk_configuration.retry_config = RetryConfig(
                strategy="none",
                backoff=None,
                retry_connection_errors=False,
            )

        generation_config = {
            "temperature": 1,
            "max_output_tokens": 65536,
            "top_p": 0.95,
            "thinking_level": "minimal",
        }

        input_data = [
            {
                "type": "image",
                "data": b64_image,
                "mime_type": "image/jpeg",
            },
            {
                "type": "text",
                "text": prompt,
            },
        ]

        for current_model in models_to_try:
            try:
                interaction = client.interactions.create(
                    model=current_model,
                    input=input_data,
                    generation_config=generation_config,
                    response_modalities=["image"],
                    timeout=60.0,
                )

                for step in getattr(interaction, "steps", []):
                    if getattr(step, "type", None) == "model_output" and getattr(step, "content", None):
                        for part in step.content:
                            part_type = getattr(part, "type", None)
                            if part_type == "text" and hasattr(part, "text") and part.text:
                                _log("info", f"Gemini Text: {part.text[:100]}")
                            elif part_type == "image" and hasattr(part, "data") and part.data:
                                raw_data = base64.b64decode(part.data)
                                img_arr = np.frombuffer(raw_data, dtype=np.uint8)
                                decoded = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                                if decoded is not None and decoded.size > 0:
                                    _log("info", f"Imagem e tipografia geradas com sucesso pelo modelo {current_model}!")
                                    return decoded
            except Exception as sdk_err:
                err_str = str(sdk_err)
                if "429" in err_str or "Rate limit" in err_str or "too_many_requests" in err_str:
                    _log(
                        "warning",
                        f"Google AI Studio ({current_model}) retornou cota excedida (429). "
                        "Ative o Billing no AI Studio para cota multimodal dedicada. Utilizando fallback local limpo."
                    )
                    break
                else:
                    logger.warning(f"Tentativa com google-genai interactions ({current_model}) falhou: {sdk_err}")
    except Exception as client_init_err:
        logger.warning(f"Falha ao inicializar genai.Client: {client_init_err}")

    return None

import base64
import json
import logging
import os
import random
from typing import Any, Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
import requests

from services.gemini_service import get_gemini_api_key
from utils.detect_face_center import detect_faces

logger = logging.getLogger(__name__)

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def sample_best_thumbnail_frame(
    video_path: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
    num_samples: int = 24,
    on_log: Callable[[str, str], None] | None = None,
) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    """Sample video frames to find the best shot showcasing primary speakers clearly.

    Scores frames based on:
    - Number of prominent faces (bonus for 2 speakers visible)
    - Face bounding box area / closeness
    - Image sharpness (Laplacian variance)
    - Center positioning
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    if not os.path.exists(video_path):
        _log("error", f"Vídeo não encontrado para extração de thumbnail: {video_path}")
        return None, []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        _log("error", f"Não foi possível abrir o vídeo: {video_path}")
        return None, []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_frames / fps

    eff_start = max(0.0, start_time)
    eff_end = end_time if end_time > eff_start + 1.0 else video_duration
    eff_end = min(eff_end, video_duration)
    duration = max(1.0, eff_end - eff_start)

    _log("info", f"Buscando melhor frame para thumbnail entre {eff_start:.1f}s e {eff_end:.1f}s ({num_samples} amostras)...")

    # Sample timestamps evenly across duration (ignoring first/last 2% for transitions)
    sample_timestamps = [
        eff_start + (duration * (0.05 + 0.9 * i / max(1, num_samples - 1)))
        for i in range(num_samples)
    ]

    best_frame: np.ndarray | None = None
    best_faces: list[dict[str, Any]] = []
    best_score = -1.0

    for ts in sample_timestamps:
        frame_idx = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        h, w, _ = frame.shape
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Reject severely blurred frames
        if sharpness < 25.0:
            continue

        try:
            faces = detect_faces(frame, min_confidence=0.40)
        except Exception:
            faces = []

        num_faces = len(faces)
        total_face_area = sum(f.get("area", 0) for f in faces)
        area_ratio = total_face_area / max(1, w * h)

        # Scoring heuristics:
        # - 2 faces (interlocutores na conversa): huge +120 points
        # - 1 face: +50 points
        # - Large facial area: up to +60 points
        # - Sharpness: up to +30 points
        frame_score = 0.0
        if num_faces >= 2:
            frame_score += 120.0
        elif num_faces == 1:
            frame_score += 50.0

        frame_score += min(60.0, area_ratio * 400.0)
        frame_score += min(30.0, sharpness / 15.0)

        if frame_score > best_score:
            best_score = frame_score
            best_frame = frame.copy()
            best_faces = faces

    cap.release()

    if best_frame is None and total_frames > 0:
        # Fallback to middle frame
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames / 2))
        ret, fallback_frame = cap.read()
        cap.release()
        if ret and fallback_frame is not None:
            best_frame = fallback_frame

    face_count = len(best_faces)
    face_desc = f"{face_count} interlocutores detectados" if face_count > 1 else f"{face_count} interlocutor detectado"
    _log("info", f"Melhor frame selecionado com sucesso ({face_desc}, score: {best_score:.1f})!")

    return best_frame, best_faces


def ask_gemini_thumbnail_strategy(
    frame: np.ndarray,
    video_title: str,
    clip_context: str = "",
    faces: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model: str = "gemini-3.8-flash",
) -> dict[str, Any]:
    """Call Gemini to generate explosive high-CTR thumbnail text, badge and color strategy."""
    api_key = api_key or get_gemini_api_key()
    faces = faces or []

    # Encode frame to lightweight JPEG
    resized = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
    b64_image = base64.b64encode(buffer).decode("utf-8")

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

    if not api_key:
        logger.warning("GEMINI_API_KEY não disponível. Usando estratégia heurística para thumbnail.")
        return {
            "hook_text": _generate_fallback_hook(video_title),
            "badge_text": "DESTAQUE",
            "color": "#FFE500",
            "placement": "top-left",
        }

    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_image,
                        }
                    },
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "response_mime_type": "application/json",
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            result = json.loads(raw_text)
            logger.info(f"Gemini gerou estratégia de thumbnail: '{result.get('hook_text')}' ({result.get('color')})")
            return result
        else:
            logger.warning(f"Erro na API do Gemini para thumbnail ({response.status_code}): {response.text[:150]}")
    except Exception as exc:
        logger.warning(f"Exceção ao chamar Gemini para thumbnail: {exc}")

    return {
        "hook_text": _generate_fallback_hook(video_title),
        "badge_text": "EXCLUSIVO",
        "color": "#FFE500",
        "placement": "top-left",
    }


def _generate_fallback_hook(title: str) -> str:
    """Generate punchy 2-4 word fallback hook text from video title."""
    clean = title.replace("-", " ").replace(":", " ").replace("|", " ")
    words = [w.upper() for w in clean.split() if len(w) > 3 and w.lower() not in ("sobre", "como", "porque", "para", "quem")]
    if len(words) >= 3:
        return f"{words[0]} {words[1]} {words[2]}!"
    elif len(words) >= 2:
        return f"{words[0]} {words[1]}!"
    return "MOMENTO INÉDITO!"


def clean_frame_overlays(
    frame: np.ndarray,
    clean_bottom_band: bool = True,
    inpaint_corners: bool = True,
    bottom_ratio: float = 0.12,
    faces: list[dict[str, Any]] | None = None,
) -> np.ndarray:
    """Clean lower third tickers, superchats and QR codes from broadcast video frames.

    Abordagem A (100% Offline & Gratuito):
    1. Re-enquadramento: Corta a faixa inferior onde superchats, tickers e QR codes
       costumam se concentrar (últimos ~12% da tela), re-centralizando os rostos dos
       interlocutores e preservando a proporção 16:9.
    2. Inpainting: Onde houver marcas d'água restantes nos cantos inferiores, aplica
       o algoritmo Telea do OpenCV para reconstruir a textura da mesa/estúdio.
    """
    if frame is None or frame.size == 0:
        return frame

    h, w, _ = frame.shape
    cleaned = frame.copy()

    # 1. Re-framing (crop bottom strip where superchats/tickers reside)
    if clean_bottom_band and bottom_ratio > 0.01:
        new_h = int(h * (1.0 - bottom_ratio))
        new_w = int(new_h * (16.0 / 9.0))
        if new_w > w:
            new_w = w
            new_h = int(new_w * (9.0 / 16.0))

        if faces:
            centers_x = [f.get("center", (w // 2, h // 2))[0] for f in faces]
            avg_cx = int(sum(centers_x) / len(centers_x))
        else:
            avg_cx = w // 2

        x1 = max(0, min(avg_cx - new_w // 2, w - new_w))
        x2 = x1 + new_w
        y1 = 0
        y2 = new_h

        cropped = cleaned[y1:y2, x1:x2]
        cleaned = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LANCZOS4)

    # 2. Inpaint lower corner watermarks / QR code remnants
    if inpaint_corners:
        mask = np.zeros((h, w), dtype=np.uint8)
        # Bottom-right corner (frequent location for QR codes and channel logos)
        br_h = int(h * 0.18)
        br_w = int(w * 0.16)
        mask[h - br_h : h, w - br_w : w] = 255

        # Bottom-left corner (sponsor badges or tickers)
        bl_h = int(h * 0.15)
        bl_w = int(w * 0.15)
        mask[h - bl_h : h, 0 : bl_w] = 255

        try:
            cleaned = cv2.inpaint(cleaned, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
        except Exception as inpaint_err:
            logger.warning(f"Erro ao aplicar inpainting local nos cantos: {inpaint_err}")

    return cleaned


def try_gemini_image_generation(
    frame_bgr: np.ndarray,
    prompt: str,
    api_key: str | None = None,
    model: str = "gemini-3.1-flash-image",
    on_log: Callable[[str, str], None] | None = None,
) -> np.ndarray | None:
    """Attempt multimodal AI generation/editing with Gemini Image models (Nano Banana).

    Sends the video frame and a descriptive prompt instructing Gemini to render
    the hook text, badge, and visual enhancements directly on the image.
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

    candidate_models = [
        model,
        "gemini-3.1-flash-image",
        "gemini-2.5-flash-image",
        "gemini-3.1-flash-lite-image",
        "gemini-3-pro-image",
        "nano-banana-pro-preview",
        "gemini-nano-banana-2.1",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

    # Resize frame to balanced resolution for API payload
    resized = cv2.resize(frame_bgr, (960, 540), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 86])
    b64_image = base64.b64encode(buffer).decode("utf-8")

    for current_model in models_to_try:
        url = f"{GEMINI_API_BASE}/{current_model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "responseModalities": ["IMAGE"],
            },
        }

        try:
            response = requests.post(url, json=payload, timeout=25)
            # If rejected because of responseModalities field, retry without it
            if response.status_code == 400 and "responseModalities" in response.text:
                payload["generationConfig"].pop("responseModalities", None)
                response = requests.post(url, json=payload, timeout=25)

            if response.status_code == 200:
                data = response.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for part in parts:
                    inline = part.get("inline_data") or part.get("inlineData")
                    if inline and inline.get("data"):
                        raw_data = base64.b64decode(inline["data"])
                        img_arr = np.frombuffer(raw_data, dtype=np.uint8)
                        decoded = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                        if decoded is not None and decoded.size > 0:
                            _log("info", f"Imagem e tipografia geradas com sucesso pelo modelo {current_model}!")
                            return decoded
            elif response.status_code == 429:
                _log(
                    "warning",
                    f"Google AI Studio ({current_model}) retornou cota excedida (429). "
                    "Ative o Billing no AI Studio para cota multimodal dedicada. Utilizando fallback local limpo."
                )
                break
            else:
                logger.warning(f"Resposta do modelo {current_model} ({response.status_code}): {response.text[:120]}")
        except Exception as exc:
            logger.warning(f"Tentativa de chamada para {current_model} falhou: {exc}")

    return None


# Backward-compatible alias
try_nano_banana_image_generation = try_gemini_image_generation


def compose_thumbnail_image(
    frame_bgr: np.ndarray,
    overlay_image_path: str | None = None,
) -> Image.Image:
    """Compose the final YouTube thumbnail in 1280x720 (cinematic enhancement, vignette, overlay).

    Zero text insertion via Pillow: all typography is rendered exclusively by Gemini AI models.
    """
    # 1. Resize base frame to 1280x720
    frame_resized = cv2.resize(frame_bgr, (THUMB_WIDTH, THUMB_HEIGHT), interpolation=cv2.INTER_LANCZOS4)
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    base_img = Image.fromarray(frame_rgb)

    # 2. Cinematic YouTube Pop enhancements (contrast & saturation boost)
    enhancer_sat = ImageEnhance.Color(base_img)
    base_img = enhancer_sat.enhance(1.24)
    enhancer_con = ImageEnhance.Contrast(base_img)
    base_img = enhancer_con.enhance(1.16)

    # 3. Vignette mask for depth
    vignette = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vignette)
    vig_draw.rectangle([0, 0, THUMB_WIDTH, THUMB_HEIGHT], fill=(0, 0, 0, 40))
    vig_draw.rectangle([0, THUMB_HEIGHT - 130, THUMB_WIDTH, THUMB_HEIGHT], fill=(0, 0, 0, 85))
    vig_draw.rectangle([0, 0, THUMB_WIDTH, 110], fill=(0, 0, 0, 75))
    base_img = Image.alpha_composite(base_img.convert("RGBA"), vignette).convert("RGB")

    # 4. Apply custom overlay if present
    if overlay_image_path:
        clean_ov = overlay_image_path.strip().strip('"').strip("'")
        if os.path.exists(clean_ov):
            try:
                ov_img = Image.open(clean_ov).convert("RGBA")
                ov_img = ov_img.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)
                base_img = Image.alpha_composite(base_img.convert("RGBA"), ov_img).convert("RGB")
            except Exception as ov_err:
                logger.warning(f"Erro ao aplicar overlay na thumbnail: {ov_err}")

    return base_img


def generate_thumbnail_for_clip(
    video_path: str,
    output_thumb_path: str,
    clip_title: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
    clip_context: str = "",
    overlay_image_path: str | None = None,
    style: str = "nano-banana",
    custom_hook: str | None = None,
    custom_badge: str | None = None,
    custom_color: str | None = None,
    remove_overlays: bool = True,
    on_log: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Complete end-to-end thumbnail generator for a clip with AI and inpainting options.

    1. Finds best frame showing interlocutors
    2. Cleans broadcast overlays/superchats/QR codes (Abordagem A: Re-framing & Inpainting local)
    3. Consults Gemini for viral hook, badge, color and placement
    4. Solicits Gemini multimodal AI to render typography directly onto the image
    5. Composes and exports high-quality 1280x720 JPEG (without any text insertion via Pillow)
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    _log("info", f"Iniciando geração de Thumbnail (estilo: {style}) para '{clip_title}'...")

    # 1. Sample best frame
    best_frame, faces = sample_best_thumbnail_frame(
        video_path=video_path,
        start_time=start_time,
        end_time=end_time,
        num_samples=24,
        on_log=on_log,
    )

    if best_frame is None:
        _log("error", "Não foi possível extrair nenhum frame válido para a thumbnail.")
        return {"success": False, "error": "Falha na extração de frame."}

    # 2. Clean broadcast overlays (Abordagem A: Re-framing & Inpainting local)
    if remove_overlays:
        _log("info", "Removendo QR codes, superchats e faixas inferiores do podcast original...")
        best_frame = clean_frame_overlays(
            best_frame,
            clean_bottom_band=True,
            inpaint_corners=True,
            bottom_ratio=0.12,
            faces=faces,
        )

    # 3. Determine Strategy (Gemini or User Custom)
    hook_text = custom_hook
    badge_text = custom_badge
    color = custom_color
    placement = "top-left"

    if style != "studio-clean" and style != "minimal":
        if not hook_text or not badge_text:
            _log("info", "Consultando inteligência do Gemini para gancho viral da Thumbnail...")
            strategy = ask_gemini_thumbnail_strategy(
                frame=best_frame,
                video_title=clip_title,
                clip_context=clip_context,
                faces=faces,
            )
            hook_text = hook_text or strategy.get("hook_text", _generate_fallback_hook(clip_title))
            badge_text = badge_text or strategy.get("badge_text", "EXCLUSIVO")
            color = color or strategy.get("color", "#FFE500")
            placement = strategy.get("placement", "top-left")
    else:
        hook_text = hook_text or ""
        badge_text = badge_text or ""
        color = color or "#FFE500"

    # 4. Solicit Gemini to render the typography directly onto the image
    text_rendered_by_gemini = False
    if hook_text and style in ("nano-banana", "classic-viral"):
        _log("info", f"Solicitando ao Gemini que renderize e posicione o texto '{hook_text}' diretamente na imagem...")
        prompt = (
            f"You are a professional YouTube thumbnail artist and designer. "
            f"Using the provided podcast video frame, render a viral high-CTR YouTube thumbnail (1280x720): "
            f"1. TYPOGRAPHY: Render the exact hook text \"{hook_text}\" in massive, bold, viral YouTube thumbnail typography in the {placement} area of the frame. "
            f"Use vibrant {color} font color, heavy black stroke/border, and dramatic 3D drop shadow. "
            f"DO NOT cover the faces or eyes of any person in the scene. "
            f"2. BADGE: Place a high-contrast badge sticker with the word \"{badge_text}\" in bold white text near the hook headline. "
            f"3. VISUAL QUALITY: Enhance studio lighting, cinematic contrast and saturation. "
            f"Clean up and remove any broadcast tickers, superchats, channel logos or QR codes. "
            f"Preserve the realistic facial features and expressions of the people in the podcast."
        )
        ai_frame = try_gemini_image_generation(best_frame, prompt, on_log=on_log)
        if ai_frame is not None:
            best_frame = ai_frame
            text_rendered_by_gemini = True
            _log("info", "✅ Imagem e tipografia geradas e posicionadas pelo próprio Gemini!")
        else:
            _log("info", "Gemini multimodal de imagem indisponível (cota/billing). Mantendo frame cinematográfico limpo (inserção de texto local via Pillow desativada).")
    elif style == "nano-banana":
        # Without hook text, attempt background cleanup via Gemini
        prompt = (
            "Remove lower thirds, watermark, superchat overlay and QR code from the bottom of this podcast frame. "
            "Reconstruct the microphone, studio table and background with realistic lighting while preserving the exact "
            "facial identity of both speakers."
        )
        ai_frame = try_gemini_image_generation(best_frame, prompt, on_log=on_log)
        if ai_frame is not None:
            best_frame = ai_frame
            _log("info", "Frame aprimorado com sucesso pela IA Gemini!")

    _log("info", f"Compondo Thumbnail final (Texto no Gemini: {text_rendered_by_gemini} | Pillow Text: desativado)...")

    # 5. Compose image (1280x720, realce de cor e vinheta, sem texto via Pillow)
    thumb_img = compose_thumbnail_image(
        frame_bgr=best_frame,
        overlay_image_path=overlay_image_path,
    )

    # 6. Save JPEG
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    thumb_img.save(output_thumb_path, "JPEG", quality=92, optimize=True)

    _log("info", f"[SUCESSO] Thumbnail gerada com sucesso em: {os.path.basename(output_thumb_path)}!")

    return {
        "success": True,
        "thumbnail_path": output_thumb_path,
        "hook_text": hook_text,
        "badge_text": badge_text,
        "color": color,
        "rendered_by_gemini": text_rendered_by_gemini,
    }

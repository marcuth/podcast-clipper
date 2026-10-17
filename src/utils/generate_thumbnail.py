import base64
import json
import logging
import os
import random
from typing import Any, Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import requests

from services.gemini_service import get_gemini_api_key
from utils.detect_face_center import detect_faces

logger = logging.getLogger(__name__)

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def find_system_font(font_name: str = "impact.ttf", size: int = 72) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find a bold high-impact system font on Windows/Linux or fallback to default."""
    candidates = [
        os.path.join(r"C:\Windows\Fonts", font_name),
        os.path.join(r"C:\Windows\Fonts", "impact.ttf"),
        os.path.join(r"C:\Windows\Fonts", "ariblk.ttf"),
        os.path.join(r"C:\Windows\Fonts", "arialbd.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Impact.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


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


def compose_thumbnail_image(
    frame_bgr: np.ndarray,
    hook_text: str,
    badge_text: str = "",
    text_color: str = "#FFE500",
    placement: str = "top-left",
    overlay_image_path: str | None = None,
    faces: list[dict[str, Any]] | None = None,
) -> Image.Image:
    """Compose the final high-CTR YouTube thumbnail in 1280x720."""
    # 1. Resize base frame to 1280x720
    frame_resized = cv2.resize(frame_bgr, (THUMB_WIDTH, THUMB_HEIGHT), interpolation=cv2.INTER_LANCZOS4)
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    base_img = Image.fromarray(frame_rgb)

    # 2. Cinematic YouTube Pop enhancements (contrast & saturation boost)
    enhancer_sat = ImageEnhance.Color(base_img)
    base_img = enhancer_sat.enhance(1.22)
    enhancer_con = ImageEnhance.Contrast(base_img)
    base_img = enhancer_con.enhance(1.15)

    # 3. Vignette mask for depth
    vignette = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vignette)
    vig_draw.rectangle([0, 0, THUMB_WIDTH, THUMB_HEIGHT], fill=(0, 0, 0, 45))
    # Darker gradient at the bottom and top
    vig_draw.rectangle([0, THUMB_HEIGHT - 120, THUMB_WIDTH, THUMB_HEIGHT], fill=(0, 0, 0, 90))
    vig_draw.rectangle([0, 0, THUMB_WIDTH, 100], fill=(0, 0, 0, 80))
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

    draw = ImageDraw.Draw(base_img)

    # 5. Determine text placement coordinates
    # Default top-left padding
    pad_x = 60
    pad_y = 50

    if "right" in placement.lower():
        pad_x = THUMB_WIDTH - 650
    if "bottom" in placement.lower():
        pad_y = THUMB_HEIGHT - 220

    current_y = pad_y

    # 6. Draw Badge if provided
    if badge_text:
        badge_clean = badge_text.strip().upper()
        badge_font = find_system_font("ariblk.ttf", size=24)
        bbox = draw.textbbox((0, 0), badge_clean, font=badge_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]

        badge_bg_rect = [
            pad_x,
            current_y,
            pad_x + bw + 24,
            current_y + bh + 14,
        ]
        # Rounded pill badge with vibrant red or dark backdrop
        draw.rounded_rectangle(badge_bg_rect, radius=6, fill="#E61A1A")
        draw.text((pad_x + 12, current_y + 6), badge_clean, font=badge_font, fill="#FFFFFF")
        current_y += bh + 26

    # 7. Draw Hook Text (Big bold letters with massive dark stroke and drop shadow)
    hook_clean = hook_text.strip().upper()
    font_size = 76 if len(hook_clean) <= 15 else 64
    hook_font = find_system_font("impact.ttf", size=font_size)

    # Wrap hook into 2 lines if needed
    words = hook_clean.split()
    lines: list[str] = []
    if len(words) > 2 and len(hook_clean) > 16:
        mid = len(words) // 2
        lines.append(" ".join(words[:mid]))
        lines.append(" ".join(words[mid:]))
    else:
        lines.append(hook_clean)

    # Parse color
    if not text_color.startswith("#"):
        text_color = "#FFE500"

    stroke_width = 8
    shadow_offset = 6

    for line in lines:
        # Drop shadow
        draw.text(
            (pad_x + shadow_offset, current_y + shadow_offset),
            line,
            font=hook_font,
            fill="#000000",
            stroke_width=stroke_width + 2,
            stroke_fill="#000000",
        )
        # Main text with black outline
        draw.text(
            (pad_x, current_y),
            line,
            font=hook_font,
            fill=text_color,
            stroke_width=stroke_width,
            stroke_fill="#000000",
        )
        bbox = draw.textbbox((0, 0), line, font=hook_font)
        line_height = bbox[3] - bbox[1]
        current_y += line_height + 14

    return base_img


def generate_thumbnail_for_clip(
    video_path: str,
    output_thumb_path: str,
    clip_title: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
    clip_context: str = "",
    overlay_image_path: str | None = None,
    on_log: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Complete end-to-end thumbnail generator for a clip.

    1. Finds best frame showing interlocutors
    2. Consults Gemini for viral hook and styling
    3. Composes and exports high-quality 1280x720 JPEG
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    _log("info", f"Iniciando geração de Thumbnail inteligente para '{clip_title}'...")

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

    # 2. Get Gemini Strategy
    _log("info", "Consultando inteligência do Gemini para gancho viral da Thumbnail...")
    strategy = ask_gemini_thumbnail_strategy(
        frame=best_frame,
        video_title=clip_title,
        clip_context=clip_context,
        faces=faces,
    )

    hook_text = strategy.get("hook_text", _generate_fallback_hook(clip_title))
    badge_text = strategy.get("badge_text", "EXCLUSIVO")
    color = strategy.get("color", "#FFE500")
    placement = strategy.get("placement", "top-left")

    _log("info", f"Compondo Thumbnail: Gancho='{hook_text}' | Selo='{badge_text}' | Cor={color}...")

    # 3. Compose image
    thumb_img = compose_thumbnail_image(
        frame_bgr=best_frame,
        hook_text=hook_text,
        badge_text=badge_text,
        text_color=color,
        placement=placement,
        overlay_image_path=overlay_image_path,
        faces=faces,
    )

    # 4. Save JPEG
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    thumb_img.save(output_thumb_path, "JPEG", quality=92, optimize=True)

    _log("info", f"[SUCESSO] Thumbnail gerada com sucesso em: {os.path.basename(output_thumb_path)}!")

    return {
        "success": True,
        "thumbnail_path": output_thumb_path,
        "hook_text": hook_text,
        "badge_text": badge_text,
        "color": color,
    }

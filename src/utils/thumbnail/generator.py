import logging
import os
from typing import Any, Callable

from utils.thumbnail.composer import compose_thumbnail_image
from utils.thumbnail.frame_cleaner import clean_frame_overlays
from utils.thumbnail.frame_selector import sample_best_thumbnail_frame
from utils.thumbnail.gemini_client import (
    ask_gemini_thumbnail_strategy,
    generate_fallback_hook,
    try_gemini_image_generation,
)

logger = logging.getLogger(__name__)


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
    2. Cleans broadcast overlays/superchats/QR codes (Re-framing & Inpainting local)
    3. Consults Gemini SDK for viral hook, badge, color and placement
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

    # 2. Clean broadcast overlays (Re-framing & Inpainting local)
    if remove_overlays:
        _log("info", "Removendo QR codes, superchats e faixas inferiores do podcast original...")
        best_frame = clean_frame_overlays(
            best_frame,
            clean_bottom_band=True,
            inpaint_corners=True,
            bottom_ratio=0.12,
            faces=faces,
        )

    # 3. Determine Strategy (Gemini SDK or User Custom)
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
            hook_text = hook_text or strategy.get("hook_text", generate_fallback_hook(clip_title))
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

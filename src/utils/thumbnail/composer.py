import logging
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

logger = logging.getLogger(__name__)

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


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

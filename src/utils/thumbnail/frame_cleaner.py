import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def clean_frame_overlays(
    frame: np.ndarray,
    clean_bottom_band: bool = True,
    inpaint_corners: bool = True,
    bottom_ratio: float = 0.12,
    faces: list[dict[str, Any]] | None = None,
) -> np.ndarray:
    """Clean lower third tickers, superchats and QR codes from broadcast video frames.

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

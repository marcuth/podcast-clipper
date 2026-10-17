"""YouTube Thumbnail Generation for Podcast Cuts.

Modularized architecture located in `utils.thumbnail`:
- `frame_selector`: Video frame analysis, face counting and sharpness scoring.
- `frame_cleaner`: Re-framing and local inpainting for watermarks and superchats.
- `gemini_client`: Multimodal strategy and AI image typography generation via google-genai SDK.
- `composer`: 1280x720 cinematic framing, color grading, vignette and custom overlays.
- `generator`: End-to-end orchestration pipeline.
"""

from utils.thumbnail import (
    THUMB_HEIGHT,
    THUMB_WIDTH,
    ask_gemini_thumbnail_strategy,
    clean_frame_overlays,
    compose_thumbnail_image,
    generate_fallback_hook,
    generate_thumbnail_for_clip,
    sample_best_thumbnail_frame,
    try_gemini_image_generation,
    try_nano_banana_image_generation,
)

__all__ = [
    "generate_thumbnail_for_clip",
    "sample_best_thumbnail_frame",
    "clean_frame_overlays",
    "ask_gemini_thumbnail_strategy",
    "try_gemini_image_generation",
    "try_nano_banana_image_generation",
    "compose_thumbnail_image",
    "generate_fallback_hook",
    "THUMB_WIDTH",
    "THUMB_HEIGHT",
]

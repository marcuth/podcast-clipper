from utils.thumbnail.composer import (
    THUMB_HEIGHT,
    THUMB_WIDTH,
    compose_thumbnail_image,
)
from utils.thumbnail.frame_cleaner import clean_frame_overlays
from utils.thumbnail.frame_selector import sample_best_thumbnail_frame
from utils.thumbnail.gemini_client import (
    ask_gemini_thumbnail_strategy,
    generate_fallback_hook,
    try_gemini_image_generation,
)
from utils.thumbnail.generator import generate_thumbnail_for_clip

# Backward-compatible alias
try_nano_banana_image_generation = try_gemini_image_generation

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

"""
Render CapCut-style animated captions as a transparent WebM overlay using the
Remotion project in ``remotion/``, and composite it over a finished clip.

Every failure is non-fatal: callers get ``None``/``False`` back and are expected
to fall back to the burned-in ASS subtitles.
"""

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

_REMOTION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "remotion"))
_RENDER_TIMEOUT_S = 600


def _flatten_words(segments: list[dict]) -> list[dict]:
    words: list[dict] = []

    for segment in segments:
        for word in segment.get("words") or []:
            words.append({"word": word["word"], "start": word["start"], "end": word["end"]})

    return sorted(words, key=lambda item: item["start"])


def _ensure_dependencies(npm: str) -> bool:
    if os.path.isdir(os.path.join(_REMOTION_DIR, "node_modules")):
        return True

    logger.info("Instalando dependências do Remotion (primeira execução)...")
    result = subprocess.run(
        [npm, "install"],
        cwd=_REMOTION_DIR,
        capture_output=True,
        text=True,
        timeout=_RENDER_TIMEOUT_S,
    )

    if result.returncode != 0:
        logger.warning(f"npm install falhou: {result.stderr[-500:]}")
        return False

    return True


def render_remotion_captions(
    segments: list[dict],
    duration: float,
    output_path: str,
) -> str | None:
    """
    Render a transparent caption overlay.

    Args:
        segments: Whisper segments relative to t=0 of the final clip, each with a ``words`` list.
        duration: Duration of the final clip in seconds.
        output_path: Destination ``.webm`` path.

    Returns:
        *output_path* on success, ``None`` if anything went wrong.
    """
    words = _flatten_words(segments)

    if not words:
        logger.warning("Sem timestamps por palavra; não é possível renderizar legendas Remotion.")
        return None

    npx = shutil.which("npx")
    npm = shutil.which("npm")

    if not npx or not npm or not os.path.isdir(_REMOTION_DIR):
        logger.warning("Node/npx ou pasta remotion/ não encontrados; usando legendas ASS.")
        return None

    props_path = os.path.splitext(output_path)[0] + ".props.json"

    try:
        if not _ensure_dependencies(npm):
            return None

        with open(props_path, "w", encoding="utf-8") as file:
            json.dump({"words": words, "durationInSeconds": duration}, file, ensure_ascii=False)

        result = subprocess.run(
            [
                npx, "remotion", "render", "src/index.ts", "Captions", os.path.abspath(output_path),
                f"--props={os.path.abspath(props_path)}",
                "--codec=vp8",
                "--image-format=png",
                "--pixel-format=yuva420p",
                "--log=error",
            ],
            cwd=_REMOTION_DIR,
            capture_output=True,
            text=True,
            timeout=_RENDER_TIMEOUT_S,
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            logger.warning(f"Remotion falhou: {(result.stderr or result.stdout)[-500:]}")
            return None

        return output_path

    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(f"Remotion falhou: {exc}")
        return None

    finally:
        if os.path.exists(props_path):
            os.remove(props_path)


def overlay_captions(video_path: str, overlay_path: str, output_path: str) -> bool:
    """Composite the transparent *overlay_path* over *video_path*, copying the audio untouched."""
    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        logger.warning("ffmpeg não encontrado; não foi possível aplicar o overlay de legendas.")
        return False

    # Forcing the libvpx decoder on the overlay input: ffmpeg's native vp8 decoder drops the alpha channel.
    result = subprocess.run(
        [
            ffmpeg, "-y",
            "-i", video_path,
            "-c:v", "libvpx", "-i", overlay_path,
            "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.warning(f"ffmpeg overlay falhou: {result.stderr[-500:]}")
        return False

    return True

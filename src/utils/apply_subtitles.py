"""
Burn dynamic subtitles into an already rendered clip.

The clip's own audio is transcribed with Whisper (so timestamps are relative to t=0
of the clip) and the subtitles are applied without re-cropping or touching the audio.
"""

import logging
import os
import subprocess

import ffmpeg

from domain.segment import Segment
from utils.generate_subtitles import generate_subtitles
from utils.render_remotion_captions import overlay_captions, render_remotion_captions
from utils.transcribe_clip import transcribe_clip

logger = logging.getLogger(__name__)


def _burn_ass(video_path: str, ass_path: str, output_path: str) -> None:
    # Relative filename + cwd avoids the Windows drive-letter escaping problems of the subtitles filter.
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", os.path.abspath(video_path),
            "-vf", f"subtitles={os.path.basename(ass_path)}",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
            "-c:a", "copy",
            "-movflags", "+faststart",
            os.path.abspath(output_path),
        ],
        cwd=os.path.dirname(os.path.abspath(ass_path)),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao queimar legendas: {result.stderr[-500:]}")


def apply_subtitles_to_video(video_path: str, output_path: str, caption_style: str = "remotion") -> None:
    """
    Transcribe *video_path* and write a copy with burned-in subtitles to *output_path*.

    Args:
        video_path: Rendered clip without subtitles.
        output_path: Destination file (must differ from *video_path*).
        caption_style: ``"remotion"`` (default) or ``"ass"``; ``"remotion"`` falls back to ``"ass"`` if the render fails.

    Raises:
        ValueError: if no speech is detected.
        RuntimeError: if FFmpeg fails.
    """
    whisper_segments = transcribe_clip(video_path)
    subtitle_segments = [
        Segment(start=item["start"], end=item["end"], text=item["text"])
        for item in whisper_segments
        if item["text"]
    ]

    if not subtitle_segments:
        raise ValueError("Nenhuma fala detectada no corte para gerar legendas.")

    if caption_style == "remotion":
        duration = float(ffmpeg.probe(video_path)["format"]["duration"])
        overlay_path = render_remotion_captions(
            whisper_segments,
            duration,
            os.path.splitext(output_path)[0] + "_captions.webm",
        )

        if overlay_path is not None:
            try:
                if overlay_captions(video_path, overlay_path, output_path):
                    return
            finally:
                os.remove(overlay_path)

        logger.warning("Legendas Remotion indisponíveis; usando legendas ASS.")

    ass_path = os.path.splitext(output_path)[0] + "_subs.ass"

    try:
        with open(ass_path, "w", encoding="utf-8") as file:
            file.write(generate_subtitles(subtitle_segments, 0.0))

        _burn_ass(video_path, ass_path, output_path)
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)

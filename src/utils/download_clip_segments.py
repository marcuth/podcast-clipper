import subprocess
import logging
import os
import sys

logger = logging.getLogger(__name__)

def download_clip_segment(
    video_url: str,
    start: float,
    end: float,
    output_path: str,
    format_spec: str = "bestvideo[height<=720]+bestaudio/best"
) -> str:
    """
    Download only a specific segment of a YouTube video using yt-dlp's
    --download-sections flag. This avoids downloading the entire video
    when only specific clips are needed.

    Args:
        video_url: The YouTube video URL.
        start: Start time in seconds.
        end: End time in seconds.
        output_path: Full path (with .mp4 extension) where the clip will be saved.
        format_spec: yt-dlp format specification.

    Returns:
        The path to the downloaded clip file.
    """
    if os.path.exists(output_path):
        logger.info(f"Segment already exists at {output_path}, skipping download.")
        return output_path

    # yt-dlp accepts --download-sections with a timestamp range like *HH:MM:SS-HH:MM:SS
    start_str = _seconds_to_hms(start)
    end_str   = _seconds_to_hms(end)
    section   = f"*{start_str}-{end_str}"

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--download-sections", section,
        "--format", format_spec,
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "-o", output_path,
        video_url
    ]

    logger.info(f"Downloading segment {start_str} → {end_str} from {video_url}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(f"yt-dlp failed:\n{result.stderr}")
        raise RuntimeError(f"Failed to download segment {start_str}-{end_str}: {result.stderr}")

    logger.info(f"Segment downloaded successfully → {output_path}")
    return output_path


def _seconds_to_hms(seconds: float) -> str:
    """Convert a float number of seconds to HH:MM:SS format."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

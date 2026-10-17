import subprocess
import logging
import os
import sys

logger = logging.getLogger(__name__)

def get_video_resolution(video_path: str) -> tuple[int, int]:
    """Get video width and height using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            video_path,
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        if "x" in out:
            w, h = out.split("x", 1)
            return int(w), int(h)
    except Exception:
        pass
    return (0, 0)


def download_clip_segment(
    video_url: str,
    start: float,
    end: float,
    output_path: str,
    format_spec: str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
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
        w, h = get_video_resolution(output_path)
        if h >= 720:
            logger.info(f"Segment already exists at {output_path} ({w}x{h}), skipping download.")
            return output_path
        else:
            logger.warning(f"Segment existing at {output_path} has low resolution ({w}x{h} < 720p). Discarding and re-downloading in HD...")
            try:
                os.remove(output_path)
            except Exception:
                pass

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
        "--format-sort", "res:1080,res,fps",
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "-o", output_path,
        video_url
    ]

    logger.info(f"Downloading segment in HD (up to 1080p) {start_str} → {end_str} from {video_url}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(f"yt-dlp failed:\n{result.stderr}")
        raise RuntimeError(f"Failed to download segment {start_str}-{end_str}: {result.stderr}")

    w, h = get_video_resolution(output_path)
    logger.info(f"Segment downloaded successfully → {output_path} ({w}x{h})")
    return output_path


def _seconds_to_hms(seconds: float) -> str:
    """Convert a float number of seconds to HH:MM:SS format."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

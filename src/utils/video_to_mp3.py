from tqdm import tqdm
import subprocess
import logging
import ffmpeg
import re

logger = logging.getLogger(__name__)

def video_to_mp3(video_path: str, output_path: str) -> None:
    try:
        probe = ffmpeg.probe(video_path)
        total_duration = float(probe["format"]["duration"])
    except ffmpeg.Error as e:
        logger.error(f"Error checking video duration: {e.stderr}")
        total_duration = 0

    args = (
        ffmpeg
        .input(video_path)
        .output(output_path, acodec="libmp3lame", audio_bitrate="192k")
        .compile(overwrite_output=True)
    )

    with tqdm(total=total_duration, unit="s", desc="Converting to MP3", disable=total_duration == 0) as pbar:
        process = subprocess.Popen(
            args,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8"
        )

        pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})")
        
        if process.stderr:
            for line in process.stderr:
                match = pattern.search(line)
                if match:
                    h, m, s = map(float, match.groups())
                    current_time = h * 3600 + m * 60 + s
                    pbar.update(max(0, current_time - pbar.n))
        
        process.wait()
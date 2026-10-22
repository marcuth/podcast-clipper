import logging

import ffmpeg

logger = logging.getLogger(__name__)

_MERGE_GAP_S = 0.01


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []

    for start, end in sorted(ranges):
        if end <= start:
            continue

        # Only fuse back-to-back ranges: cut_clip repeats overlapping ones, so the audio must too.
        if merged and abs(start - merged[-1][1]) <= _MERGE_GAP_S:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    return [(start, end) for start, end in merged]


def extract_clip_audio(video_path: str, ranges: list[tuple[float, float]], output_path: str) -> None:
    """
    Extract the audio of *ranges* from *video_path* and concatenate it into one MP3.

    The result follows the same concatenated timeline that ``cut_clip`` renders, so
    transcribing it yields timestamps relative to t=0 of the final clip.

    Args:
        video_path: Source video (usually the full downloaded video).
        ranges: ``(start, end)`` pairs in seconds within the source video.
        output_path: Destination ``.mp3`` path.
    """
    merged = _merge_ranges(ranges)

    if not merged:
        raise ValueError("Nenhum trecho válido para extrair áudio.")

    source = ffmpeg.input(video_path)
    parts = [
        source.audio.filter("atrim", start=start, end=end).filter("asetpts", "PTS-STARTPTS")
        for start, end in merged
    ]
    audio = ffmpeg.concat(*parts, v=0, a=1) if len(parts) > 1 else parts[0]

    try:
        audio.output(output_path, acodec="libmp3lame", audio_bitrate="128k").overwrite_output().run(quiet=True)
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")[-500:] if exc.stderr else ""
        raise RuntimeError(f"Falha ao extrair áudio do corte: {stderr}") from exc

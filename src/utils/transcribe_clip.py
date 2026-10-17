"""
Transcribe a single video/audio clip with faster-whisper and return
segments normalised to the clip's own timeline (i.e. starting at t=0).
"""

from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)


def transcribe_clip(clip_path: str, language: str = "pt") -> list[dict]:
    """
    Transcribe a short audio/video clip using faster-whisper (Whisper small
    model) and return a list of segment dicts relative to the clip start
    (t=0).

    This is used after clip extraction so that subtitles are generated from
    the actual spoken audio rather than the (sometimes inaccurate) YouTube
    captions.

    Args:
        clip_path: Path to an audio or video file accepted by faster-whisper.
        language:  Language hint passed to Whisper (default "pt").

    Returns:
        List of dicts with keys ``start``, ``end``, and ``text``.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        "small",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
    )

    segments_iter, info = model.transcribe(
        clip_path,
        language=language,
        beam_size=1,
        vad_filter=True,
    )

    total_duration = info.duration
    segments_data: list[dict] = []

    with tqdm(total=total_duration, unit="s", desc="Transcribing clip", leave=False) as pbar:
        for segment in segments_iter:
            segments_data.append({
                "start": segment.start,
                "end":   segment.end,
                "text":  segment.text.strip(),
            })
            pbar.update(segment.end - pbar.n)

    return segments_data

from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

def transcribe_audio(audio_path: str) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        "small",
        device="cpu",
        compute_type="int8",
        cpu_threads=2
    )

    segments_interator, info = model.transcribe(
        audio_path,
        beam_size=1,
        vad_filter=True
    )

    total_duration = info.duration
    
    segments_data = []

    with tqdm(total=total_duration, unit="s", desc="Transcribing") as pbar:
        for segment in segments_interator:
            segments_data.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text
            })
            
            pbar.update(segment.end - pbar.n)

    return segments_data
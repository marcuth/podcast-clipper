"""Strategy pattern: how the full video is transcribed before clips are selected."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from utils import (
    get_youtube_transcription,
    transcribe_audio,
    transcribe_audio_assemblyai,
    video_to_mp3,
)

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionContext:
    """What a strategy needs; ``video_path`` is filled in if a strategy had to download the video."""

    video_url: str
    output_dir: str
    video_path: str | None
    download_video: Callable[[], str]
    log: Callable[[str, str], None]

    def ensure_audio(self) -> str:
        """Return the project's ``audio.mp3``, downloading the video and extracting it if needed."""
        if not self.video_path:
            self.video_path = self.download_video()

        audio_path = os.path.join(self.output_dir, "audio.mp3")

        if not os.path.exists(audio_path):
            self.log("info", "Extraindo áudio do vídeo para MP3...")
            video_to_mp3(self.video_path, audio_path)

        return audio_path


class TranscriptionStrategy(ABC):
    label: str = ""
    # Whether the whole video must be downloaded before transcribing (and so reused for cutting).
    requires_full_video: bool = True

    @abstractmethod
    def transcribe(self, context: TranscriptionContext) -> list[dict]: ...


class WhisperTranscription(TranscriptionStrategy):
    label = "Whisper local"

    def transcribe(self, context: TranscriptionContext) -> list[dict]:
        audio_path = context.ensure_audio()
        context.log("info", "Transcrevendo áudio com Whisper local...")
        return transcribe_audio(audio_path)


class AssemblyAITranscription(TranscriptionStrategy):
    label = "AssemblyAI Cloud"

    def transcribe(self, context: TranscriptionContext) -> list[dict]:
        audio_path = context.ensure_audio()
        context.log("info", "Transcrevendo áudio com AssemblyAI Cloud API...")

        try:
            return transcribe_audio_assemblyai(audio_path)
        except Exception as exc:
            context.log("warning", f"Transcrição com AssemblyAI falhou ({exc}). Alternando para Whisper local...")
            return transcribe_audio(audio_path)


class YouTubeCaptionsTranscription(TranscriptionStrategy):
    """Official YouTube captions, falling back to local Whisper when the video has none."""

    label = "Legendas do YouTube"

    def __init__(self, full_download: bool) -> None:
        self.requires_full_video = full_download

    def transcribe(self, context: TranscriptionContext) -> list[dict]:
        context.log("info", "Buscando transcrição oficial das legendas do YouTube...")

        try:
            return get_youtube_transcription(context.video_url)
        except Exception as exc:
            context.log("warning", f"Legendas do YouTube indisponíveis ({exc}). Alternando automaticamente para Whisper local...")
            return WhisperTranscription().transcribe(context)

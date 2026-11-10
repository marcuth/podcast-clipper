"""Strategy pattern: which provider transcribes a clip's audio to sync the dynamic captions."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ClipTranscriber(ABC):
    @abstractmethod
    def transcribe(self, clip_path: str, language: str) -> list[dict]:
        """Segments with word timestamps, relative to the clip start."""


class WhisperClipTranscriber(ClipTranscriber):
    def transcribe(self, clip_path: str, language: str) -> list[dict]:
        from utils.transcribe_clip import transcribe_clip_whisper

        return transcribe_clip_whisper(clip_path, language)


class AssemblyAIClipTranscriber(ClipTranscriber):
    def transcribe(self, clip_path: str, language: str) -> list[dict]:
        from utils.transcribe_assemblyai import transcribe_clip_assemblyai

        return transcribe_clip_assemblyai(clip_path, language)


class FallbackClipTranscriber(ClipTranscriber):
    def __init__(self, primary: ClipTranscriber, fallback: ClipTranscriber) -> None:
        self._primary = primary
        self._fallback = fallback

    def transcribe(self, clip_path: str, language: str) -> list[dict]:
        try:
            return self._primary.transcribe(clip_path, language)
        except Exception as exc:
            logger.warning(f"{type(self._primary).__name__} falhou para legendas ({exc}); usando Whisper local.")
            return self._fallback.transcribe(clip_path, language)

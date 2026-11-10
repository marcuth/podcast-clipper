"""Simple Factory: the one place that maps option values to strategy objects."""

from .caption_sync import (
    AssemblyAIClipTranscriber,
    ClipTranscriber,
    FallbackClipTranscriber,
    WhisperClipTranscriber,
)
from .clip_selection import (
    ClipSelectionStrategy,
    CustomRangeLongSelection,
    FallbackSelection,
    GeminiLongSelection,
    GeminiShortSelection,
    HeuristicShortSelection,
    SequentialLongSelection,
)
from .modes import (
    CAPTION_PROVIDER_ASSEMBLYAI,
    MODE_ASSEMBLYAI,
    MODE_WHISPER,
    MODE_YT_PARTIAL,
    STRATEGY_AI,
)
from .transcription import (
    AssemblyAITranscription,
    TranscriptionStrategy,
    WhisperTranscription,
    YouTubeCaptionsTranscription,
)


class StrategyFactory:
    @staticmethod
    def transcription(mode: str) -> TranscriptionStrategy:
        if mode == MODE_ASSEMBLYAI:
            return AssemblyAITranscription()

        if mode == MODE_WHISPER:
            return WhisperTranscription()

        # yt_full (default) and yt_partial both read YouTube captions; they differ in when the video is downloaded.
        return YouTubeCaptionsTranscription(full_download=mode != MODE_YT_PARTIAL)

    @staticmethod
    def clip_selection(
        clipping_strategy: str,
        is_long_clip: bool,
        has_custom_range: bool = False,
    ) -> ClipSelectionStrategy:
        if is_long_clip:
            if has_custom_range:
                return CustomRangeLongSelection()

            return FallbackSelection(GeminiLongSelection(), SequentialLongSelection())

        if clipping_strategy == STRATEGY_AI:
            return FallbackSelection(GeminiShortSelection(), HeuristicShortSelection())

        return HeuristicShortSelection()

    @staticmethod
    def caption_sync(provider: str) -> ClipTranscriber:
        if provider == CAPTION_PROVIDER_ASSEMBLYAI:
            return FallbackClipTranscriber(AssemblyAIClipTranscriber(), WhisperClipTranscriber())

        return WhisperClipTranscriber()

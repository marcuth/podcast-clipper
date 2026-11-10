"""Strategy pattern: how the clips (groups of segments) are picked from the transcript."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from domain import Segment
from heuristics import apply_heuristics
from utils import ai_create_clips, ai_create_long_clips, create_clips

logger = logging.getLogger(__name__)

SHORT_MIN_DURATION = 20.0
SHORT_MAX_DURATION = 85.0


def _seconds_to_hms(seconds: float) -> str:
    total = int(seconds)
    hours, minutes, secs = total // 3600, (total % 3600) // 60, total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


@dataclass
class ClipSelectionContext:
    segments: list[Segment]
    video_title: str
    channel_name: str
    video_description: str
    max_clips: int
    gemini_key: str | None
    gemini_model: str
    log: Callable[[str, str], None]
    report: Callable[[str], None]  # progress message for the UI
    heatmap: list[dict] = field(default_factory=list)
    min_duration: float = 0.0
    max_duration: float = 0.0
    custom_start: float | None = None
    custom_end: float | None = None


class ClipSelectionStrategy(ABC):
    label: str = ""

    @abstractmethod
    def select(self, context: ClipSelectionContext) -> list[list[Segment]]: ...


def _require_gemini_key(context: ClipSelectionContext) -> str:
    if not context.gemini_key:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")

    return context.gemini_key


class GeminiShortSelection(ClipSelectionStrategy):
    label = "IA (Gemini)"

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        api_key = _require_gemini_key(context)
        context.report("IA (Gemini) analisando transcrição e selecionando momentos virais...")
        context.log("info", "Enviando transcrição para o Google Gemini selecionar os melhores cortes virais...")

        clips, _ = ai_create_clips(
            segments=context.segments,
            video_title=context.video_title,
            min_duration=SHORT_MIN_DURATION,
            max_duration=SHORT_MAX_DURATION,
            max_clips=context.max_clips,
            api_key=api_key,
            model=context.gemini_model,
            channel_name=context.channel_name,
            video_description=context.video_description,
        )
        context.log("info", f"IA (Gemini) selecionou e planejou {len(clips)} cortes com sucesso!")
        return clips


class HeuristicShortSelection(ClipSelectionStrategy):
    label = "Heurísticas"

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        context.report("Aplicando heurísticas e pontuando momentos mais engajantes...")
        context.log("info", "Aplicando heurísticas virais nos segmentos...")

        for segment in context.segments:
            apply_heuristics(segment, context.segments, heatmap=context.heatmap or None)

        context.log("info", "Agrupando segmentos em clipes ideais...")
        return create_clips(context.segments, max_clips=context.max_clips)


class GeminiLongSelection(ClipSelectionStrategy):
    label = "IA (Gemini) para cortes longos"

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        api_key = _require_gemini_key(context)
        context.report("IA (Gemini) analisando transcrição e selecionando temas longos (até 20 min)...")
        context.log(
            "info",
            f"Buscando cortes longos de {context.min_duration / 60:.0f} a {context.max_duration / 60:.0f} minutos com IA...",
        )

        clips, _ = ai_create_long_clips(
            segments=context.segments,
            video_title=context.video_title,
            min_duration=context.min_duration,
            max_duration=context.max_duration,
            max_clips=context.max_clips,
            api_key=api_key,
            model=context.gemini_model,
            channel_name=context.channel_name,
            video_description=context.video_description,
        )
        context.log("info", f"IA (Gemini) selecionou {len(clips)} cortes longos temáticos!")
        return clips


class SequentialLongSelection(ClipSelectionStrategy):
    label = "Blocos longos sequenciais"

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        context.log("info", "Agrupando segmentos em blocos longos sequenciais...")
        block_target = min(context.max_duration, max(context.min_duration, 600.0))
        clips: list[list[Segment]] = []
        current: list[Segment] = []

        for segment in context.segments:
            current.append(segment)

            if (current[-1].end - current[0].start) >= block_target:
                clips.append(current)
                current = []

                if len(clips) >= context.max_clips:
                    break

        if current and len(clips) < context.max_clips:
            clips.append(current)

        return clips


class CustomRangeLongSelection(ClipSelectionStrategy):
    """A single long clip over the interval the user picked in the studio."""

    label = "Intervalo personalizado"

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        start = max(0.0, float(context.custom_start or 0.0))
        end = max(start + 1.0, float(context.custom_end or 0.0))
        matching = [seg for seg in context.segments if seg.end > start and seg.start < end]

        if not matching:
            matching = [Segment(start=start, end=end, text="Corte Personalizado", norm="", score=8.5)]

        setattr(
            matching[0],
            "ai_metadata",
            {
                "title": f"Corte - {context.video_title[:50]}",
                "hook": "Intervalo selecionado pelo usuário",
                "reason": "Trecho personalizado selecionado no estúdio",
                "viral_score": 9.0,
            },
        )
        context.log(
            "info",
            f"Usando intervalo customizado de corte longo: {_seconds_to_hms(start)} -> {_seconds_to_hms(end)}",
        )
        return [matching]


class FallbackSelection(ClipSelectionStrategy):
    """Tries each strategy in order; an error or an empty result moves on to the next one."""

    def __init__(self, *strategies: ClipSelectionStrategy) -> None:
        self._strategies = strategies
        self.label = " -> ".join(strategy.label for strategy in strategies)

    def select(self, context: ClipSelectionContext) -> list[list[Segment]]:
        *attempts, last = self._strategies

        for strategy in attempts:
            try:
                clips = strategy.select(context)

                if clips:
                    return clips
            except Exception as exc:
                context.log("warning", f"{strategy.label} indisponível: {exc}. Usando a próxima alternativa...")

        return last.select(context)

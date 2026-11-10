"""Observer pattern for the pipeline: the engine publishes events, observers react to them."""

import logging
from typing import Callable, Protocol, runtime_checkable

from core.pipeline_progress import PipelineProgress

logger = logging.getLogger(__name__)


@runtime_checkable
class PipelineObserver(Protocol):
    def on_progress(self, progress: PipelineProgress) -> None: ...
    def on_log(self, level: str, message: str) -> None: ...
    def on_clip_done(self, clip: dict) -> None: ...


class BasePipelineObserver:
    """No-op observer: subclass and override only the events you care about."""

    def on_progress(self, progress: PipelineProgress) -> None:
        pass

    def on_log(self, level: str, message: str) -> None:
        pass

    def on_clip_done(self, clip: dict) -> None:
        pass


class LoggingObserver(BasePipelineObserver):
    """Mirrors pipeline log events to the Python logger (the terminal)."""

    def __init__(self, target: logging.Logger) -> None:
        self._logger = target

    def on_log(self, level: str, message: str) -> None:
        if level == "error":
            self._logger.error(message)
        elif level == "warning":
            self._logger.warning(message)
        else:
            self._logger.info(message)


class CallbackObserver(BasePipelineObserver):
    """Adapts plain callables to the observer interface."""

    def __init__(
        self,
        on_progress: Callable[[PipelineProgress], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
        on_clip_done: Callable[[dict], None] | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._on_log = on_log
        self._on_clip_done = on_clip_done

    def on_progress(self, progress: PipelineProgress) -> None:
        if self._on_progress:
            self._on_progress(progress)

    def on_log(self, level: str, message: str) -> None:
        if self._on_log:
            self._on_log(level, message)

    def on_clip_done(self, clip: dict) -> None:
        if self._on_clip_done:
            self._on_clip_done(clip)


class PipelineEventBus:
    """Subject: keeps the observers and notifies them; one failing observer never breaks the run."""

    def __init__(self) -> None:
        self._observers: list[PipelineObserver] = []

    def subscribe(self, observer: PipelineObserver) -> Callable[[], None]:
        """Register *observer*; returns a function that unsubscribes it."""
        self._observers.append(observer)
        return lambda: self.unsubscribe(observer)

    def unsubscribe(self, observer: PipelineObserver) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def emit_progress(self, progress: PipelineProgress) -> None:
        self._dispatch("on_progress", progress)

    def emit_log(self, level: str, message: str) -> None:
        self._dispatch("on_log", level, message)

    def emit_clip_done(self, clip: dict) -> None:
        self._dispatch("on_clip_done", clip)

    def _dispatch(self, event: str, *args: object) -> None:
        for observer in list(self._observers):
            try:
                getattr(observer, event)(*args)
            except Exception as exc:
                logger.warning(f"Observer {type(observer).__name__}.{event} falhou: {exc}")


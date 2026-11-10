"""Observer that forwards pipeline events to the web UI and keeps the state used for UI re-syncs."""

from typing import Any

from src.core.events import BasePipelineObserver
from src.core.pipeline_progress import PipelineProgress


class UiBridgeObserver(BasePipelineObserver):
    def __init__(self, api: Any) -> None:
        self._api = api

    def on_progress(self, progress: PipelineProgress) -> None:
        data = {
            "step": progress.step,
            "step_index": progress.step_index,
            "percentage": progress.percentage,
            "message": progress.message,
            "current_clip": progress.current_clip,
            "total_clips": progress.total_clips,
            "data": progress.data,
        }
        self._api._current_progress = data
        self._api._emit_to_js("progress", data)

    def on_log(self, level: str, message: str) -> None:
        log_item = {"level": level, "message": message}
        recent = self._api._recent_logs
        recent.append(log_item)

        if len(recent) > self._api._max_logs:
            recent.pop(0)

        self._api._emit_to_js("log", log_item)

    def on_clip_done(self, clip: dict[str, Any]) -> None:
        self._api._emit_to_js("clip_done", clip)

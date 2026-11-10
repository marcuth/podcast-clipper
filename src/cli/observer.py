"""Observer that renders pipeline events in the terminal with rich (progress bar + colored log lines)."""

from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from core.events import BasePipelineObserver
from core.pipeline_progress import PipelineProgress

STEP_LABELS = {
    "init": "Iniciando",
    "metadata": "Vídeo",
    "heatmap": "Heatmap",
    "download": "Download",
    "transcribe": "Transcrição",
    "heuristics": "Seleção",
    "clips_plan": "Plano",
    "cutting": "Cortes",
    "done": "Concluído",
}

_LOG_STYLES = {
    "info": ("dim", "·"),
    "warning": ("yellow", "!"),
    "error": ("bold red", "x"),
}


class CliObserver(BasePipelineObserver):
    def __init__(self, console: Console) -> None:
        self.console = console
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.fields[step]:<12}[/]"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.description}", justify="left"),
            console=console,
            transient=False,
        )
        self._task = self._progress.add_task("", total=100, step="Iniciando")

    def __enter__(self) -> "CliObserver":
        self._progress.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._progress.stop()

    def on_progress(self, progress: PipelineProgress) -> None:
        if progress.step in ("error", "cancelled"):
            return

        self._progress.update(
            self._task,
            completed=progress.percentage,
            step=STEP_LABELS.get(progress.step, progress.step),
            description=escape(progress.message),
        )

    def on_log(self, level: str, message: str) -> None:
        style, marker = _LOG_STYLES.get(level, _LOG_STYLES["info"])
        self._progress.console.print(f"[{style}]{marker} {escape(message)}[/]", markup=True, highlight=False)

    def on_clip_done(self, clip: dict) -> None:
        title = (clip.get("details") or {}).get("title", "")
        self._progress.console.print(
            f"[bold green]+ {clip['name']}[/] [dim]{clip['start_formatted']} -> {clip['end_formatted']} "
            f"({clip['duration']:.0f}s)[/] {escape(title)}",
            highlight=False,
        )

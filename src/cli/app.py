"""CLI entry point: flags -> assistant -> summary -> pipeline run with live progress."""

import logging
import shutil
import sys
import threading
from typing import Any

import questionary
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from core.pipeline import MODE_LABELS, STRATEGY_LABELS, PipelineEngine, PipelineOptions
from services import get_gemini_api_key
from strategies import MODE_ASSEMBLYAI, STRATEGY_AI
from utils import get_assemblyai_api_key

from .args import build_parser
from .observer import CliObserver
from .wizard import UserAborted, build_options

EXIT_OK, EXIT_ERROR, EXIT_CANCELLED = 0, 1, 130

console = Console()


def _banner() -> None:
    console.print(
        Panel.fit(
            "[bold magenta]Podcast Clipper[/]\n[dim]Cortes automáticos a partir de vídeos do YouTube[/]",
            border_style="magenta",
            padding=(0, 4),
        )
    )


def _format_label(options: PipelineOptions) -> str:
    if options.only_timestamps:
        return "Só timestamps e metadados"

    return "Cortes longos 16:9" if options.is_long_clip else "Shorts verticais 9:16"


def _summary(options: PipelineOptions) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("Vídeo", options.video_url)
    table.add_row("Formato", _format_label(options))
    table.add_row("Seleção", STRATEGY_LABELS.get(options.clipping_strategy, options.clipping_strategy))
    table.add_row("Transcrição", MODE_LABELS.get(options.transcription_mode, options.transcription_mode))
    table.add_row("Máx. de cortes", str(options.max_clips))

    if options.is_long_clip:
        table.add_row("Silêncios", "removidos" if options.remove_silence else "mantidos")
        table.add_row("Overlay", options.long_clip_overlay or "nenhum")
    elif not options.only_timestamps:
        if options.render_subtitles:
            table.add_row("Legendas", f"{options.caption_style} (sincronia: {options.caption_transcriber})")
        else:
            table.add_row("Legendas", "desligadas")

        table.add_row("Vinheta", options.vignette_angle if options.apply_vignette else "desligada")
        table.add_row(
            "Split-screen",
            f"{options.split_screen_chance:.0%} de chance" if options.enable_split_screen else "desligado",
        )

    return table


def _preflight(options: PipelineOptions) -> list[str]:
    """Problems that will not stop the run but change what it does."""
    notes: list[str] = []

    if options.clipping_strategy == STRATEGY_AI and not get_gemini_api_key():
        notes.append("GEMINI_API_KEY ausente: a seleção por IA vai cair para as heurísticas.")

    needs_assembly = options.transcription_mode == MODE_ASSEMBLYAI or (
        options.render_subtitles and options.caption_transcriber == "assemblyai"
    )
    if needs_assembly and not get_assemblyai_api_key():
        notes.append("ASSEMBLY_AI_API_KEY ausente: a AssemblyAI vai cair para o Whisper local (mais lento).")

    if not options.only_timestamps and not shutil.which("ffmpeg"):
        notes.append("FFmpeg não encontrado no PATH: os vídeos não poderão ser renderizados.")

    if options.render_subtitles and options.caption_style == "remotion" and not shutil.which("node"):
        notes.append("Node não encontrado: as legendas Remotion vão usar o estilo simples (ASS).")

    return notes


def _result_table(result: dict[str, Any]) -> Table:
    table = Table(title="Cortes gerados", title_style="bold", header_style="bold cyan")
    table.add_column("Corte")
    table.add_column("Início -> Fim")
    table.add_column("Duração", justify="right")
    table.add_column("Título", overflow="fold")

    for clip in result.get("clips", []):
        table.add_row(
            clip["name"],
            f"{clip['start_formatted']} -> {clip['end_formatted']}",
            f"{clip['duration']:.0f}s",
            escape((clip.get("details") or {}).get("title", "")),
        )

    return table


def _run_pipeline(options: PipelineOptions) -> tuple[dict | None, BaseException | None]:
    """Run the engine in a worker thread so Ctrl+C can cancel it gracefully (second Ctrl+C forces exit)."""
    cancel_token = threading.Event()
    outcome: dict[str, Any] = {}

    with CliObserver(console) as observer:
        engine = PipelineEngine(cancel_token=cancel_token, observers=[observer], log_to_terminal=False)

        def worker() -> None:
            try:
                outcome["result"] = engine.run(options)
            except BaseException as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while thread.is_alive():
            try:
                thread.join(timeout=0.2)
            except KeyboardInterrupt:
                if cancel_token.is_set():
                    console.print("\n[bold red]Encerrando agora.[/]")
                    raise

                cancel_token.set()
                observer.on_log("warning", "Cancelando ao fim da etapa atual... (Ctrl+C de novo para sair já)")

    return outcome.get("result"), outcome.get("error")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, show_time=False)],
    )

    _banner()

    try:
        options = build_options(args)
    except UserAborted:
        console.print("[yellow]Cancelado.[/]")
        return EXIT_CANCELLED
    except ValueError as exc:
        console.print(f"[bold red]Erro:[/] {exc}")
        return EXIT_ERROR

    console.print()
    console.print(Panel(_summary(options), title="Resumo", border_style="cyan"))

    for note in _preflight(options):
        console.print(f"[yellow]! {note}[/]")

    if not args.yes:
        try:
            if not questionary.confirm("Iniciar?", default=True).ask():
                console.print("[yellow]Cancelado.[/]")
                return EXIT_CANCELLED
        except KeyboardInterrupt:
            return EXIT_CANCELLED

    console.print()

    try:
        result, error = _run_pipeline(options)
    except KeyboardInterrupt:
        return EXIT_CANCELLED

    if error is not None:
        console.print(f"\n[bold red]Falhou:[/] {error}")
        return EXIT_ERROR

    status = (result or {}).get("status")

    if status == "cancelled":
        console.print("\n[yellow]Processamento cancelado.[/]")
        return EXIT_CANCELLED

    clips = (result or {}).get("clips", [])

    if clips:
        console.print()
        console.print(_result_table(result))

    console.print(
        Panel.fit(
            f"[bold green]{len(clips)} corte(s) gerado(s)[/]\n[dim]{(result or {}).get('output_dir', '')}[/]",
            border_style="green",
        )
    )
    return EXIT_OK

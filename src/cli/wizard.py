"""Interactive assistant that turns flags + answers into PipelineOptions."""

import argparse
import os
import re
from pathlib import Path
from typing import Any, Callable

import questionary

from core.pipeline import PipelineOptions
from services import get_gemini_api_key
from strategies import (
    CAPTION_PROVIDER_ASSEMBLYAI,
    CAPTION_PROVIDER_WHISPER,
    MODE_ASSEMBLYAI,
    MODE_WHISPER,
    MODE_YT_FULL,
    MODE_YT_PARTIAL,
    STRATEGY_AI,
    STRATEGY_HEURISTICS,
)
from utils import get_assemblyai_api_key

YOUTUBE_URL = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/.+$")
MIN_CLIPS, MAX_CLIPS = 1, 15


class UserAborted(Exception):
    """The user pressed Ctrl+C / Esc in a prompt."""


def _ask(question: Any) -> Any:
    answer = question.ask()

    if answer is None:
        raise UserAborted

    return answer


def _valid_url(value: str) -> bool | str:
    return True if YOUTUBE_URL.match(value.strip()) else "Informe um link válido (youtube.com/watch?v=... ou youtu.be/...)"


def _valid_clip_count(value: str) -> bool | str:
    if value.strip().isdigit() and MIN_CLIPS <= int(value) <= MAX_CLIPS:
        return True

    return f"Digite um número de {MIN_CLIPS} a {MAX_CLIPS}"


def save_env_key(key: str, value: str) -> None:
    """Write ``key`` into the project's .env, replacing an existing line."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True) if env_path.exists() else []
    updated = [f'{key} = "{value}"\n' if line.strip().startswith(key) else line for line in lines]

    if not any(line.strip().startswith(key) for line in lines):
        updated.append(f'\n{key} = "{value}"\n')

    env_path.write_text("".join(updated), encoding="utf-8")


def _ask_overlay(interactive: bool) -> str | None:
    default = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
    has_default = bool(default and os.path.exists(default))

    if not interactive:
        return default if has_default else None

    choices = []

    if has_default:
        choices.append(questionary.Choice(f"Usar o overlay padrão ({os.path.basename(default)})", value="default"))

    choices += [
        questionary.Choice("Informar um arquivo de imagem (PNG/JPG)", value="custom"),
        questionary.Choice("Não aplicar overlay", value="none"),
    ]
    choice = _ask(
        questionary.select(
            "Overlay (moldura/marca d'água 16:9) nos cortes longos?",
            choices=choices,
            default=choices[0].value,
        )
    )

    if choice == "default":
        return default

    if choice == "none":
        return None

    path = _ask(
        questionary.path(
            "Caminho da imagem:",
            validate=lambda value: os.path.isfile(value.strip().strip('"')) or "Arquivo não encontrado",
        )
    ).strip().strip('"')

    if _ask(questionary.confirm("Salvar como overlay padrão no .env?", default=not has_default)):
        os.environ["DEFAULT_LONG_CLIP_OVERLAY"] = path
        save_env_key("DEFAULT_LONG_CLIP_OVERLAY", path)

    return path


def build_options(args: argparse.Namespace) -> PipelineOptions:
    """Ask only what the flags did not answer; with ``--yes`` nothing is asked."""
    interactive = not args.yes
    has_gemini = bool(get_gemini_api_key())
    has_assembly = bool(get_assemblyai_api_key())

    def pick(value: Any, make_question: Callable[[], Any], default: Any) -> Any:
        if value is not None:
            return value

        return _ask(make_question()) if interactive else default

    def confirm(flag_disabled: bool, text: str, default: bool = True) -> bool:
        if flag_disabled:
            return False

        return _ask(questionary.confirm(text, default=default)) if interactive else default

    # ── Video ────────────────────────────────────────────────────────────────
    url = args.url
    if url and not YOUTUBE_URL.match(url.strip()):
        raise ValueError(f"URL do YouTube inválida: {url}")

    if not url:
        if not interactive:
            raise ValueError("Informe a URL do vídeo (ex.: poetry run start URL --yes).")

        url = _ask(questionary.text("URL do vídeo do YouTube:", validate=_valid_url)).strip()

    # ── Selection & transcription ────────────────────────────────────────────
    ai_label = "Inteligência Artificial (Gemini): analisa narrativa e ganchos"
    strategy = pick(
        args.strategy,
        lambda: questionary.select(
            "Como selecionar os melhores cortes?",
            choices=[
                questionary.Choice(ai_label + ("" if has_gemini else "  [sem GEMINI_API_KEY]"), value=STRATEGY_AI),
                questionary.Choice("Heurísticas & Heatmap (regras de palavras-chave)", value=STRATEGY_HEURISTICS),
            ],
            default=STRATEGY_AI if has_gemini else STRATEGY_HEURISTICS,
        ),
        STRATEGY_AI if has_gemini else STRATEGY_HEURISTICS,
    )

    mode = pick(
        args.transcription,
        lambda: questionary.select(
            "De onde vem a transcrição?",
            choices=[
                questionary.Choice(
                    "AssemblyAI Cloud: rápido e preciso" + ("" if has_assembly else "  [sem ASSEMBLY_AI_API_KEY]"),
                    value=MODE_ASSEMBLYAI,
                ),
                questionary.Choice("Legendas do YouTube, baixando o vídeo inteiro (rápido)", value=MODE_YT_FULL),
                questionary.Choice("Legendas do YouTube, download parcial (lento, gasta menos banda)", value=MODE_YT_PARTIAL),
                questionary.Choice("Whisper local (lento, sem internet após o download)", value=MODE_WHISPER),
            ],
            default=MODE_ASSEMBLYAI if has_assembly else MODE_YT_FULL,
        ),
        MODE_ASSEMBLYAI if has_assembly else MODE_YT_FULL,
    )

    # ── Output format ────────────────────────────────────────────────────────
    output_format = pick(
        args.output_format,
        lambda: questionary.select(
            "O que gerar?",
            choices=[
                questionary.Choice("Shorts verticais 9:16 (enquadramento facial + legendas)", value="short"),
                questionary.Choice("Cortes longos 16:9 (remoção de silêncio + overlay)", value="long"),
                questionary.Choice("Só timestamps e metadados (rápido, sem renderizar)", value="timestamps"),
            ],
            default="short",
        ),
        "short",
    )
    only_timestamps = output_format == "timestamps"
    is_long_clip = output_format == "long"

    use_heatmap = False
    if strategy == STRATEGY_HEURISTICS:
        use_heatmap = confirm(
            args.no_heatmap,
            'Reforçar a pontuação com o "mais reproduzidos" do YouTube? (recomendado)',
        )

    options = PipelineOptions(
        video_url=url.strip(),
        transcription_mode=mode,
        clipping_strategy=strategy,
        use_heatmap=use_heatmap,
        only_timestamps=only_timestamps,
        is_long_clip=is_long_clip,
        render_subtitles=False,
        use_whisper_subtitles=False,
        apply_vignette=False,
        enable_split_screen=False,
        delete_original_video=not args.keep_video,
    )

    # ── Format-specific settings ─────────────────────────────────────────────
    if is_long_clip:
        options.remove_silence = confirm(False, "Remover pausas de silêncio (jump cut)?")
        options.long_clip_overlay = _ask_overlay(interactive)
    elif not only_timestamps:
        _ask_short_settings(options, args, interactive, has_assembly, confirm, pick)

    # ── How many clips ───────────────────────────────────────────────────────
    default_clips = 3 if is_long_clip else 8

    if args.max_clips is not None:
        options.max_clips = min(MAX_CLIPS, max(MIN_CLIPS, args.max_clips))
    elif interactive:
        options.max_clips = int(
            _ask(
                questionary.text(
                    f"Quantidade máxima de cortes ({MIN_CLIPS} a {MAX_CLIPS}):",
                    default=str(default_clips),
                    validate=_valid_clip_count,
                )
            )
        )
    else:
        options.max_clips = default_clips

    return options


def _ask_short_settings(options: PipelineOptions, args: argparse.Namespace, interactive: bool, has_assembly: bool, confirm: Any, pick: Any) -> None:
    options.render_subtitles = confirm(args.no_subtitles, "Queimar legendas dinâmicas no vídeo?")

    if options.render_subtitles:
        options.caption_style = pick(
            args.caption_style,
            lambda: questionary.select(
                "Estilo das legendas:",
                choices=[
                    questionary.Choice("Remotion: animação palavra a palavra (requer Node)", value="remotion"),
                    questionary.Choice("ASS: simples e rápido, sem dependências extras", value="ass"),
                ],
                default="remotion",
            ),
            "remotion",
        )

        # Remotion always re-transcribes each clip for word timestamps; ASS only does it on request.
        if options.caption_style == "ass" and options.transcription_mode != MODE_ASSEMBLYAI:
            options.use_whisper_subtitles = confirm(
                False,
                "Re-transcrever cada corte para sincronizar melhor as legendas? (mais lento)",
            )

        if options.caption_style == "remotion" or options.use_whisper_subtitles:
            options.caption_transcriber = pick(
                args.caption_provider,
                lambda: questionary.select(
                    "Quem sincroniza as palavras das legendas?",
                    choices=[
                        questionary.Choice("Whisper local (grátis, mais lento)", value=CAPTION_PROVIDER_WHISPER),
                        questionary.Choice(
                            "AssemblyAI Cloud (rápido)" + ("" if has_assembly else "  [sem ASSEMBLY_AI_API_KEY]"),
                            value=CAPTION_PROVIDER_ASSEMBLYAI,
                        ),
                    ],
                    default=CAPTION_PROVIDER_ASSEMBLYAI if has_assembly else CAPTION_PROVIDER_WHISPER,
                ),
                CAPTION_PROVIDER_ASSEMBLYAI if has_assembly else CAPTION_PROVIDER_WHISPER,
            )

    options.apply_vignette = confirm(args.no_vignette, "Aplicar vinheta (escurecer as bordas)?")

    if options.apply_vignette and interactive:
        options.vignette_angle = _ask(
            questionary.select(
                "Intensidade da vinheta:",
                choices=[
                    questionary.Choice("Moderada (recomendada)", value="PI/4"),
                    questionary.Choice("Sutil", value="PI/5"),
                    questionary.Choice("Intensa (cinematográfica)", value="PI/3.5"),
                ],
                default="PI/4",
            )
        )

    options.enable_split_screen = confirm(
        args.no_split_screen,
        "Dividir a tela em 2 quando houver 2 pessoas conversando (split-screen)?",
    )

    if options.enable_split_screen and interactive:
        options.split_screen_chance = _ask(
            questionary.select(
                "Chance de usar split-screen em tomadas com 2 pessoas:",
                choices=[
                    questionary.Choice("50%: equilibrado (padrão)", value=0.5),
                    questionary.Choice("100%: sempre dividir", value=1.0),
                    questionary.Choice("30%: ocasional", value=0.3),
                ],
                default=0.5,
            )
        )

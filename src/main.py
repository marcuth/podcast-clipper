from tqdm import tqdm
# pyrefly: ignore [missing-import]
import questionary
import warnings
import logging
import yt_dlp
import json
import os
import re
import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (

    video_to_mp3,
    transcribe_audio,
    create_clips,
    cut_clip,
    get_youtube_transcription,
    slugify,
    download_clip_segment,
    transcribe_clip,
    get_youtube_heatmap,
)
from services import generate_video_details
from heuristics import apply_heuristics
from domain import Segment

warnings.filterwarnings("ignore", category=UserWarning)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

from src.core.pipeline import (
    MODE_WHISPER,
    MODE_YT_FULL,
    MODE_YT_PARTIAL,
    STRATEGY_AI,
    STRATEGY_HEURISTICS,
    PipelineEngine,
    PipelineOptions,
    PipelineProgress,
)

# ──────────────────────────────────────────────────────────────────────────────
# Mode labels
# ──────────────────────────────────────────────────────────────────────────────

_MODE_WHISPER    = "Local Whisper (Slower, but more accurate)"
_MODE_YT_FULL    = "YouTube Captions – full download (Fast)"
_MODE_YT_PARTIAL = "YouTube Captions – partial download (Fastest, downloads only needed clips)"

_STRATEGY_AI_LABEL = "🤖 Inteligência Artificial (Gemini API - analisa narrativa e ganchos) [Recomendado]"
_STRATEGY_HEURISTICS_LABEL = "📊 Heurísticas & Estatísticas (Regras de palavras-chave + Heatmap)"

# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_youtube_video_url() -> str:
    input_url = input("Enter YouTube video URL: ")

    if not re.match(r"^(https?\:\/\/)?(www\.youtube\.com|youtu\.be)\/.+$", input_url):
        logger.error("Invalid YouTube video URL, Try again...")
        return get_youtube_video_url()

    return input_url

# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("Initializing Application")

    video_url = get_youtube_video_url()

    # ── Choose clipping selection strategy ───────────────────────────────────
    strategy_label = questionary.select(
        "Como deseja selecionar os melhores cortes do vídeo?",
        choices=[_STRATEGY_AI_LABEL, _STRATEGY_HEURISTICS_LABEL],
        default=_STRATEGY_AI_LABEL,
    ).ask()

    clipping_strategy = STRATEGY_AI if strategy_label == _STRATEGY_AI_LABEL else STRATEGY_HEURISTICS

    # ── Choose transcription / download strategy ──────────────────────────────
    transcription_mode_label = questionary.select(
        "How do you want to get the transcription?",
        choices=[_MODE_WHISPER, _MODE_YT_FULL, _MODE_YT_PARTIAL],
    ).ask()

    mode_map = {
        _MODE_WHISPER: MODE_WHISPER,
        _MODE_YT_FULL: MODE_YT_FULL,
        _MODE_YT_PARTIAL: MODE_YT_PARTIAL,
    }
    mode = mode_map.get(transcription_mode_label, MODE_YT_PARTIAL)

    # ── Choose output processing mode ─────────────────────────────────────────
    process_mode_label = questionary.select(
        "Como deseja processar os clipes?",
        choices=[
            "🎬 Renderizar vídeos verticais completos (.mp4 + enquadramento facial + metadados)",
            "⏱️ Apenas gerar timestamps e metadados (Ultra rápido - sem renderizar vídeos)",
        ],
        default="🎬 Renderizar vídeos verticais completos (.mp4 + enquadramento facial + metadados)",
    ).ask()

    only_timestamps = "Apenas gerar timestamps" in (process_mode_label or "")

    render_subtitles = True
    use_whisper_subtitles = False
    apply_vignette = False
    vignette_angle = "PI/4"
    enable_split_screen = False
    split_screen_chance = 0.5

    # ── Fetch YouTube heatmap (most replayed) ─────────────────────────────────
    use_heatmap = False
    if clipping_strategy == STRATEGY_HEURISTICS:
        use_heatmap = questionary.confirm(
            "Boost clip scores using YouTube's \"most replayed\" data? "
            "(recommended — requires a quick page fetch)",
            default=True,
        ).ask()

    if not only_timestamps:
        # ── Ask whether to render burned-in subtitles on the video ────────────────
        render_subtitles = questionary.confirm(
            "Renderizar legendas dinâmicas no vídeo? (burned-in subtitles)",
            default=True,
        ).ask()

        # ── Ask whether to re-transcribe each clip with Whisper for subtitles ─────
        if render_subtitles and mode in (MODE_YT_FULL, MODE_YT_PARTIAL):
            use_whisper_subtitles = questionary.confirm(
                "Re-transcribe each clip with Whisper for accurate subtitles? "
                "(slower, but much better subtitle quality)",
                default=True,
            ).ask()

        # ── Vignette effect (darken edges/borders) ────────────────────────────────
        apply_vignette = questionary.confirm(
            "Apply vignette effect (darken video borders/edges)?",
            default=True,
        ).ask()

        if apply_vignette:
            vignette_intensity = questionary.select(
                "Vignette intensity:",
                choices=[
                    "Moderate (Recommended - PI/4)",
                    "Subtle (Soft - PI/5)",
                    "Intense (Cinematic - PI/3.5)",
                ],
                default="Moderate (Recommended - PI/4)",
            ).ask()

            if "Subtle" in (vignette_intensity or ""):
                vignette_angle = "PI/5"
            elif "Intense" in (vignette_intensity or ""):
                vignette_angle = "PI/3.5"
            else:
                vignette_angle = "PI/4"

        # ── Split-Screen for 2 people ─────────────────────────────────────────────
        enable_split_screen = questionary.confirm(
            "Dividir tela em 2 blocos (split-screen) quando houver 2 pessoas conversando?",
            default=True,
        ).ask()

        if enable_split_screen:
            chance_choice = questionary.select(
                "Chance de aplicar split-screen em tomadas com 2 pessoas:",
                choices=[
                    "50% (Equilibrado / Dinâmico - Padrão)",
                    "100% (Sempre dividir quando houver 2 pessoas)",
                    "30% (Ocasional / Mais raro)",
                ],
                default="50% (Equilibrado / Dinâmico - Padrão)",
            ).ask()
            if "100%" in (chance_choice or ""):
                split_screen_chance = 1.0
            elif "30%" in (chance_choice or ""):
                split_screen_chance = 0.3
            else:
                split_screen_chance = 0.5

    options = PipelineOptions(
        video_url=video_url,
        transcription_mode=mode,
        render_subtitles=render_subtitles,
        use_whisper_subtitles=use_whisper_subtitles,
        use_heatmap=use_heatmap,
        apply_vignette=apply_vignette,
        vignette_angle=vignette_angle,
        enable_split_screen=enable_split_screen,
        split_screen_chance=split_screen_chance,
        only_timestamps=only_timestamps,
        clipping_strategy=clipping_strategy,
    )

    def on_progress(p: PipelineProgress) -> None:
        logger.info(f"[{p.step.upper()} - {p.percentage:.0f}%] {p.message}")

    engine = PipelineEngine(on_progress=on_progress)
    result = engine.run(options)
    logger.info(f"Execution finished with status: {result.get('status')}")

if __name__ == "__main__":
    main()
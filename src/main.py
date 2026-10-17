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
    MODE_ASSEMBLYAI,
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

_MODE_ASSEMBLYAI = "🚀 AssemblyAI Cloud (Mais rápido, preciso e com pontuação IA) [Recomendado]"
_MODE_WHISPER    = "🎯 Local Whisper (Slower, but more accurate)"
_MODE_YT_FULL    = "📺 YouTube Captions – full download (Fast)"
_MODE_YT_PARTIAL = "⚡ YouTube Captions – partial download (Fastest, downloads only needed clips)"

_STRATEGY_AI_LABEL = "🤖 Inteligência Artificial (Gemini API - analisa narrativa e ganchos) [Recomendado]"
_STRATEGY_HEURISTICS_LABEL = "📊 Heurísticas & Estatísticas (Regras de palavras-chave + Heatmap)"

# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def _save_env_key(variable_key: str, variable_value: str) -> None:
    """Save an environment variable key and value directly into the project .env file."""
    workspace_root = Path(__file__).resolve().parent.parent
    env_file_path = workspace_root / ".env"
    try:
        existing_lines = []
        key_found = False
        if env_file_path.exists():
            with open(env_file_path, "r", encoding="utf-8") as env_read_file:
                existing_lines = env_read_file.readlines()

        updated_lines = []
        for current_line in existing_lines:
            if current_line.strip().startswith(variable_key):
                updated_lines.append(f'{variable_key} = "{variable_value}"\n')
                key_found = True
            else:
                updated_lines.append(current_line)

        if not key_found:
            updated_lines.append(f'\n{variable_key} = "{variable_value}"\n')

        with open(env_file_path, "w", encoding="utf-8") as env_write_file:
            env_write_file.writelines(updated_lines)

        logger.info(f"Salvo {variable_key} com sucesso no arquivo .env")
    except Exception as env_error:
        logger.warning(f"Não foi possível salvar {variable_key} no .env: {env_error}")

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
        "Como deseja obter a transcrição do áudio?",
        choices=[_MODE_ASSEMBLYAI, _MODE_YT_PARTIAL, _MODE_YT_FULL, _MODE_WHISPER],
        default=_MODE_ASSEMBLYAI,
    ).ask()

    mode_map = {
        _MODE_ASSEMBLYAI: MODE_ASSEMBLYAI,
        _MODE_WHISPER: MODE_WHISPER,
        _MODE_YT_FULL: MODE_YT_FULL,
        _MODE_YT_PARTIAL: MODE_YT_PARTIAL,
    }
    mode = mode_map.get(transcription_mode_label, MODE_ASSEMBLYAI)

    # ── Choose output processing mode ─────────────────────────────────────────
    process_mode_label = questionary.select(
        "Como deseja processar os clipes?",
        choices=[
            "🎬 Shorts Verticais 9:16 (.mp4 + enquadramento facial + legendas)",
            "📺 Cortes Longos 16:9 (.mp4 horizontal + remoção de silêncio + overlay)",
            "⏱️ Apenas gerar timestamps e metadados (Ultra rápido - sem renderizar vídeos)",
        ],
        default="🎬 Shorts Verticais 9:16 (.mp4 + enquadramento facial + legendas)",
    ).ask()

    only_timestamps = "Apenas gerar timestamps" in (process_mode_label or "")
    is_long_clip = "Cortes Longos" in (process_mode_label or "")

    render_subtitles = True
    use_whisper_subtitles = False
    apply_vignette = False
    vignette_angle = "PI/4"
    enable_split_screen = False
    split_screen_chance = 0.5
    remove_silence = True
    long_clip_overlay: str | None = None

    # ── Fetch YouTube heatmap (most replayed) ─────────────────────────────────
    use_heatmap = False
    if clipping_strategy == STRATEGY_HEURISTICS:
        use_heatmap = questionary.confirm(
            "Boost clip scores using YouTube's \"most replayed\" data? "
            "(recommended — requires a quick page fetch)",
            default=True,
        ).ask()

    if not only_timestamps and is_long_clip:
        # ── Long clips options ────────────────────────────────────────────────
        remove_silence = questionary.confirm(
            "Remover pausas de silêncio automaticamente (Jump Cut FFmpeg)?",
            default=True,
        ).ask()

        default_overlay = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
        has_default = bool(default_overlay and os.path.exists(default_overlay))

        if has_default:
            overlay_choice = questionary.select(
                f"Deseja aplicar overlay nos cortes longos?",
                choices=[
                    f"Sim, usar overlay padrão ({os.path.basename(default_overlay)})",
                    "Sim, informar outro arquivo de imagem (PNG/JPG)",
                    "Não aplicar overlay",
                ],
                default=f"Sim, usar overlay padrão ({os.path.basename(default_overlay)})",
            ).ask()

            if "overlay padrão" in (overlay_choice or ""):
                long_clip_overlay = default_overlay
            elif "outro arquivo" in (overlay_choice or ""):
                custom_overlay_input = questionary.text("Caminho do arquivo de imagem (PNG/JPG):").ask()
                if custom_overlay_input and os.path.exists(custom_overlay_input.strip()):
                    long_clip_overlay = custom_overlay_input.strip()
                    save_as_default = questionary.confirm("Deseja salvar este overlay como padrão no .env?", default=False).ask()
                    if save_as_default:
                        os.environ["DEFAULT_LONG_CLIP_OVERLAY"] = long_clip_overlay
                        _save_env_key("DEFAULT_LONG_CLIP_OVERLAY", long_clip_overlay)
        else:
            want_overlay = questionary.confirm(
                "Deseja aplicar uma imagem de overlay (moldura/marca d'água 16:9) sobre os vídeos longos?",
                default=False,
            ).ask()

            if want_overlay:
                custom_overlay_input = questionary.text("Caminho do arquivo de imagem (ex: assets/overlays/frame.png):").ask()
                if custom_overlay_input and os.path.exists(custom_overlay_input.strip()):
                    long_clip_overlay = custom_overlay_input.strip()
                    save_as_default = questionary.confirm("Deseja salvar este overlay como padrão no .env?", default=True).ask()
                    if save_as_default:
                        os.environ["DEFAULT_LONG_CLIP_OVERLAY"] = long_clip_overlay
                        _save_env_key("DEFAULT_LONG_CLIP_OVERLAY", long_clip_overlay)

    elif not only_timestamps:
        # ── Shorts (9:16) options ─────────────────────────────────────────────
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

    default_clips_target = 3 if is_long_clip else 8

    max_clips_prompt = questionary.text(
        "Quantidade máxima de cortes a extrair (1 a 15):",
        default=str(default_clips_target),
    ).ask()

    try:
        max_clips = int((max_clips_prompt or "").strip())
        
    except ValueError:
        max_clips = default_clips_target

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
        is_long_clip=is_long_clip,
        remove_silence=remove_silence,
        long_clip_overlay=long_clip_overlay,
        max_clips=max_clips,
    )

    def on_progress(progress: PipelineProgress) -> None:
        logger.info(f"[{progress.step.upper()} - {progress.percentage:.0f}%] {progress.message}")

    engine = PipelineEngine(on_progress=on_progress)
    result = engine.run(options)
    logger.info(f"Execution finished with status: {result.get('status')}")

if __name__ == "__main__":
    main()
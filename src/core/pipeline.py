from dataclasses import dataclass, field
from typing import Callable
import json
import logging
import os
import re
import threading

import yt_dlp

import sys
from pathlib import Path

# Ensure src root is in sys.path for consistent imports across CLI and GUI
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (
    ai_create_clips,
    ai_create_long_clips,
    create_clips,
    cut_clip,
    cut_horizontal_clip_with_silence_removal,
    download_clip_segment,
    extract_clip_audio,
    get_video_resolution,
    get_youtube_heatmap,
    get_youtube_transcription,
    slugify,
    transcribe_audio,
    transcribe_audio_assemblyai,
    transcribe_clip,
    video_to_mp3,
)
from domain import Segment
from heuristics import apply_heuristics
from services import (
    build_fallback_details,
    generate_video_details,
    get_gemini_api_key,
    is_fallback_details,
    title_problem,
)


logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Modes & Strategies
# ──────────────────────────────────────────────────────────────────────────────

MODE_ASSEMBLYAI = "assemblyai"
MODE_WHISPER = "whisper"
MODE_YT_FULL = "yt_full"
MODE_YT_PARTIAL = "yt_partial"

MODE_LABELS = {
    MODE_ASSEMBLYAI: "AssemblyAI Cloud (Mais preciso e rápido via API)",
    MODE_WHISPER: "Local Whisper (Slower, but more accurate)",
    MODE_YT_FULL: "YouTube Captions – full download (Fast)",
    MODE_YT_PARTIAL: "YouTube Captions – partial download (Very slow, but uses less bandwidth)",
}

STRATEGY_AI = "ai"
STRATEGY_HEURISTICS = "heuristics"

STRATEGY_LABELS = {
    STRATEGY_AI: "Inteligência Artificial (Gemini API)",
    STRATEGY_HEURISTICS: "Heurísticas & Heatmap (Estatísticas)",
}


def _seconds_to_hms(seconds: float) -> str:
    total_seconds_int = int(seconds)
    hours = total_seconds_int // 3600
    minutes = (total_seconds_int % 3600) // 60
    remaining_seconds = total_seconds_int % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
        
    return f"{minutes:02d}:{remaining_seconds:02d}"


@dataclass
class PipelineOptions:
    video_url: str
    transcription_mode: str = MODE_YT_FULL
    render_subtitles: bool = True
    use_whisper_subtitles: bool = True
    caption_style: str = "remotion"
    use_heatmap: bool = True
    output_base_dir: str = "output"
    apply_vignette: bool = True
    vignette_angle: str = "PI/4"
    enable_split_screen: bool = True
    split_screen_chance: float = 0.5
    only_timestamps: bool = False
    clipping_strategy: str = STRATEGY_AI
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    )
    # Long clips (16:9) and silence removal options
    is_long_clip: bool = False
    remove_silence: bool = True
    silence_threshold_db: float = -30.0
    min_silence_duration: float = 0.6
    silence_padding: float = 0.15
    min_clip_duration: float = 180.0
    max_clip_duration: float = 1200.0
    max_clips: int = 3
    custom_start_time: float | None = None
    custom_end_time: float | None = None
    delete_original_video: bool = True
    long_clip_overlay: str | None = None


@dataclass
class PipelineProgress:
    step: str  # 'init', 'metadata', 'heatmap', 'download', 'transcribe', 'heuristics', 'clips_plan', 'cutting', 'done', 'error', 'cancelled'
    step_index: int  # 1 to 6
    total_steps: int = 6
    percentage: float = 0.0
    message: str = ""
    current_clip: int = 0
    total_clips: int = 0
    data: dict = field(default_factory=dict)


class PipelineEngine:
    """Executes the podcast clipping pipeline with support for progress reporting and cancellation."""

    def __init__(
        self,
        on_progress: Callable[[PipelineProgress], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
        on_clip_done: Callable[[dict], None] | None = None,
        cancel_token: threading.Event | None = None,
    ) -> None:
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_clip_done = on_clip_done
        self.cancel_token = cancel_token

    def _log(self, level: str, message: str) -> None:
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

        if self.on_log:
            self.on_log(level, message)

    def _notify(self, progress: PipelineProgress) -> None:
        if self.on_progress:
            self.on_progress(progress)

    def _check_cancelled(self) -> bool:
        if self.cancel_token and self.cancel_token.is_set():
            self._log("warning", "Processamento cancelado pelo usuário.")
            self._notify(
                PipelineProgress(
                    step="cancelled",
                    step_index=0,
                    percentage=0,
                    message="Processamento cancelado.",
                )
            )
            return True
        return False

    @staticmethod
    def is_valid_youtube_url(url: str) -> bool:
        return bool(re.match(r"^(https?:\/\/)?(www\.youtube\.com|youtu\.be)\/.+$", url.strip()))

    @staticmethod
    def _build_ytdlp_opts(base_options: dict | None = None) -> dict:
        """Construct robust yt-dlp options bypassing YouTube bot detection and 429 errors."""
        options = {
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        }
        cookie_path = os.environ.get("YOUTUBE_COOKIES_PATH") or os.environ.get("COOKIES_FILE")
        if cookie_path and os.path.exists(cookie_path):
            options["cookiefile"] = cookie_path
        elif os.path.exists("cookies.txt"):
            options["cookiefile"] = "cookies.txt"

        browser_cookie = os.environ.get("YOUTUBE_COOKIES_BROWSER")
        if browser_cookie:
            options["cookiesfrombrowser"] = (browser_cookie,)

        if base_options:
            options.update(base_options)
        return options

    @staticmethod
    def get_video_info(video_url: str) -> dict:
        """Fetch video metadata quickly without downloading."""
        ydl_opts = PipelineEngine._build_ytdlp_opts({
            "skip_download": True,
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                "id": info.get("id"),
                "title": info.get("title", "Untitled"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "view_count": info.get("view_count", 0),
                "description": (info.get("description") or "")[:800],
            }

    def _download_full_video(self, video_url: str, output_dir: str) -> tuple[str, str]:
        expected_file_path = os.path.join(output_dir, "video.mp4")
        if os.path.exists(expected_file_path):
            w, h = get_video_resolution(expected_file_path)
            if h >= 720:
                self._log("info", f"Vídeo já existe em {expected_file_path} ({w}x{h}). Pulando download.")
                return expected_file_path, os.path.basename(output_dir)
            else:
                self._log(
                    "warning",
                    f"Vídeo existente em {expected_file_path} possui baixa resolução ({w}x{h} < 720p). "
                    f"Descartando para baixar em Full HD 1080p..."
                )
                try:
                    os.remove(expected_file_path)
                except Exception as e:
                    self._log("warning", f"Não foi possível remover vídeo antigo: {e}")

        self._log("info", f"Baixando vídeo completo em Full HD (até 1080p) em: {output_dir}")

        last_pct = [-10.0]
        def progress_hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                if total > 0:
                    pct = (downloaded / total) * 100
                    if pct - last_pct[0] >= 10.0 or pct >= 99.5:
                        last_pct[0] = pct
                        speed = d.get("speed") or 0
                        speed_mb = speed / (1024 * 1024) if speed else 0
                        eta = d.get("eta") or 0
                        self._log("info", f"Download do vídeo: {pct:.1f}% ({speed_mb:.1f} MB/s, ETA: {eta}s)")

        ydl_opts = self._build_ytdlp_opts({
            "outtmpl": f"{output_dir}/video.%(ext)s",
            "format": "bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/best[height<=1080]/best",
            "format_sort": ["res:1080", "res", "fps"],
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            base, _ = os.path.splitext(file_path)
            mp4_path = base + ".mp4"
            final_path = mp4_path if os.path.exists(mp4_path) else file_path
            w, h = get_video_resolution(final_path)
            self._log("info", f"Vídeo completo baixado com sucesso! Resolução: {w}x{h}")
            return final_path, info_dict.get("title", "Untitled")

    def run(self, options: PipelineOptions) -> dict:
        """Executes the full pipeline sequentially."""
        video_url = options.video_url.strip()
        if not self.is_valid_youtube_url(video_url):
            msg = f"URL do YouTube inválida: {video_url}"
            self._log("error", msg)
            raise ValueError(msg)

        if options.is_long_clip:
            options.render_subtitles = False

        # ── Step 1: Video Info & Metadata ─────────────────────────────────────
        self._notify(
            PipelineProgress(
                step="metadata",
                step_index=1,
                percentage=5.0,
                message="Obtendo informações do vídeo...",
            )
        )
        self._log("info", f"Iniciando pipeline para: {video_url}")

        if self._check_cancelled():
            return {"status": "cancelled"}

        info = self.get_video_info(video_url)
        video_title = info["title"]
        channel_name = info.get("uploader", "")
        video_description = info.get("description", "")
        slug = slugify(video_title)
        output_dir = os.path.join(options.output_base_dir, slug)
        clips_dir = os.path.join(output_dir, "clips")
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(clips_dir, exist_ok=True)

        meta_path = os.path.join(output_dir, "project_meta.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as meta_file:
                json.dump(
                    {
                        "video_url": video_url,
                        "video_title": video_title,
                        "channel_name": channel_name,
                        "video_description": video_description,
                        "is_long_clip": options.is_long_clip,
                    },
                    meta_file,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception:
            pass

        self._log("info", f"Vídeo identificado: '{video_title}'")
        if channel_name:
            self._log("info", f"Canal / Produtor: '{channel_name}'")
        self._log("info", f"Diretório do projeto: {output_dir}")

        if self._check_cancelled():
            return {"status": "cancelled"}

        # ── Step 2: YouTube Heatmap ───────────────────────────────────────────
        heatmap: list[dict] = []
        if options.use_heatmap:
            self._notify(
                PipelineProgress(
                    step="heatmap",
                    step_index=2,
                    percentage=15.0,
                    message="Coletando heatmap do YouTube (trechos mais vistos)...",
                )
            )
            self._log("info", "Buscando dados de 'mais reproduzidos' do YouTube...")
            try:
                heatmap = get_youtube_heatmap(video_url)
                if heatmap:
                    self._log("info", f"Heatmap carregado com {len(heatmap)} pontos.")
                else:
                    self._log("warning", "Heatmap indisponível para este vídeo. Usando heurísticas de texto.")
            except Exception as e:
                self._log("warning", f"Falha ao obter heatmap: {e}. Prosseguindo sem heatmap.")
                heatmap = []

        if self._check_cancelled():
            return {"status": "cancelled"}

        # ── Step 3: Video Download or Metadata Prep ───────────────────────────
        self._notify(
            PipelineProgress(
                step="download",
                step_index=3,
                percentage=25.0,
                message="Preparando fontes de áudio e vídeo...",
            )
        )

        video_path = None
        if options.only_timestamps:
            self._log("info", "Modo Apenas Timestamps ativo: download do vídeo completo ignorado.")
        elif options.transcription_mode in (MODE_WHISPER, MODE_YT_FULL, MODE_ASSEMBLYAI):
            video_path, _ = self._download_full_video(video_url, output_dir)
        else:
            self._log("info", "Download do vídeo adiado para o corte (otimização de pipeline).")

        if self._check_cancelled():
            return {"status": "cancelled"}

        # ── Step 4: Transcription ─────────────────────────────────────────────
        self._notify(
            PipelineProgress(
                step="transcribe",
                step_index=4,
                percentage=40.0,
                message="Transcrevendo conteúdo do vídeo...",
            )
        )

        segments_json_path = os.path.join(output_dir, "segments.json")
        clips_plan_filename = "long_clips.json" if options.is_long_clip else "clips.json"
        clips_json_path = os.path.join(output_dir, clips_plan_filename)

        if os.path.exists(segments_json_path) and os.path.getsize(segments_json_path) > 10:
            self._log("info", f"Transcrição prévia encontrada em {segments_json_path}. Reutilizando transcrição existente...")
            with open(segments_json_path, "r", encoding="utf-8") as file:
                segments_data = json.load(file)
            self._log("info", f"Transcrição carregada ({len(segments_data)} trechos obtidos).")
        elif options.transcription_mode == MODE_ASSEMBLYAI:
            if not video_path:
                video_path, _ = self._download_full_video(video_url, output_dir)
            audio_path = os.path.join(output_dir, "audio.mp3")
            if not os.path.exists(audio_path):
                self._log("info", "Extraindo áudio do vídeo para MP3...")
                video_to_mp3(video_path, audio_path)
            self._log("info", "Transcrevendo áudio com AssemblyAI Cloud API...")
            try:
                segments_data = transcribe_audio_assemblyai(audio_path)
            except Exception as exc:
                self._log("warning", f"Transcrição com AssemblyAI falhou ({exc}). Alternando para Whisper local...")
                segments_data = transcribe_audio(audio_path)
            with open(segments_json_path, "w", encoding="utf-8") as file:
                json.dump(segments_data, file, indent=4)
            self._log("info", f"Transcrição salva ({len(segments_data)} trechos obtidos com AssemblyAI).")
        elif options.transcription_mode == MODE_WHISPER:
            if not video_path:
                video_path, _ = self._download_full_video(video_url, output_dir)
            audio_path = os.path.join(output_dir, "audio.mp3")
            if not os.path.exists(audio_path):
                self._log("info", "Extraindo áudio do vídeo para MP3...")
                video_to_mp3(video_path, audio_path)
            self._log("info", "Transcrevendo áudio com Whisper local...")
            segments_data = transcribe_audio(audio_path)
            with open(segments_json_path, "w", encoding="utf-8") as file:
                json.dump(segments_data, file, indent=4)
            self._log("info", f"Transcrição salva ({len(segments_data)} trechos obtidos).")
        else:
            self._log("info", "Buscando transcrição oficial das legendas do YouTube...")
            try:
                segments_data = get_youtube_transcription(video_url)
            except Exception as exc:
                self._log("warning", f"Legendas do YouTube indisponíveis ({exc}). Alternando automaticamente para Whisper local...")
                if not video_path:
                    video_path, _ = self._download_full_video(video_url, output_dir)
                audio_path = os.path.join(output_dir, "audio.mp3")
                if not os.path.exists(audio_path):
                    self._log("info", "Extraindo áudio do vídeo para MP3...")
                    video_to_mp3(video_path, audio_path)
                self._log("info", "Transcrevendo áudio com Whisper local...")
                segments_data = transcribe_audio(audio_path)
            with open(segments_json_path, "w", encoding="utf-8") as file:
                json.dump(segments_data, file, indent=4)
            self._log("info", f"Transcrição salva ({len(segments_data)} trechos obtidos).")

        if self._check_cancelled():
            return {"status": "cancelled"}

        # ── Step 5: Clip Selection (AI vs Heuristics) ─────────────────────────
        segments = [Segment(**segment_dict) for segment_dict in segments_data]
        clips: list[list[Segment]] = []
        is_ai_mode = options.clipping_strategy == STRATEGY_AI
        gemini_key = get_gemini_api_key()

        if os.path.exists(clips_json_path) and os.path.getsize(clips_json_path) > 10 and options.custom_start_time is None:
            try:
                with open(clips_json_path, "r", encoding="utf-8") as clips_file:
                    raw_clips = json.load(clips_file)
                    loaded_clips = [[Segment(**item) for item in group] for group in raw_clips if group]

                if loaded_clips:
                    first_duration = loaded_clips[0][-1].end - loaded_clips[0][0].start
                    if options.is_long_clip and first_duration < 120.0:
                        self._log(
                            "warning",
                            f"O arquivo {clips_plan_filename} contém clipes curtos ({first_duration:.1f}s), incompatíveis com o modo de Cortes Longos. Descartando e planejando novos cortes longos...",
                        )
                        clips = []
                    elif (not options.is_long_clip) and first_duration > 150.0:
                        self._log(
                            "warning",
                            f"O arquivo {clips_plan_filename} contém clipes longos ({first_duration:.1f}s), incompatíveis com o modo Shorts. Descartando e planejando novos shorts...",
                        )
                        clips = []
                    else:
                        clips = loaded_clips
                        self._log(
                            "info",
                            f"Planejamento prévio compatível encontrado em {clips_json_path}. Reutilizando {len(clips)} cortes...",
                        )
            except Exception as e:
                self._log("warning", f"Erro ao carregar {clips_plan_filename} existente ({e}). Recalculando cortes...")
                clips = []

        if not clips and options.is_long_clip:
            # Plan long clips (custom interval or AI thematic blocks up to 20 min)
            if options.custom_start_time is not None and options.custom_end_time is not None:
                clip_custom_start = max(0.0, float(options.custom_start_time))
                clip_custom_end = max(clip_custom_start + 1.0, float(options.custom_end_time))
                matching = [
                    seg
                    for seg in segments
                    if seg.end > clip_custom_start and seg.start < clip_custom_end
                ]
                if not matching:
                    matching = [
                        Segment(
                            start=clip_custom_start,
                            end=clip_custom_end,
                            text="Corte Personalizado",
                            norm="",
                            score=8.5,
                        )
                    ]
                setattr(
                    matching[0],
                    "ai_metadata",
                    {
                        "title": f"Corte - {video_title[:50]}",
                        "hook": "Intervalo selecionado pelo usuário",
                        "reason": "Trecho personalizado selecionado no estúdio",
                        "viral_score": 9.0,
                    },
                )
                clips = [matching]
                self._log(
                    "info",
                    f"Usando intervalo customizado de corte longo: {_seconds_to_hms(clip_custom_start)} -> {_seconds_to_hms(clip_custom_end)}",
                )
            else:
                self._notify(
                    PipelineProgress(
                        step="heuristics",
                        step_index=5,
                        percentage=55.0,
                        message="IA (Gemini) analisando transcrição e selecionando temas longos (até 20 min)...",
                    )
                )
                self._log(
                    "info",
                    f"Buscando cortes longos de {options.min_clip_duration/60:.0f} a {options.max_clip_duration/60:.0f} minutos com IA...",
                )
                if gemini_key:
                    try:
                        clips, _ = ai_create_long_clips(
                            segments=segments,
                            video_title=video_title,
                            min_duration=options.min_clip_duration,
                            max_duration=options.max_clip_duration,
                            max_clips=options.max_clips,
                            api_key=gemini_key,
                            model=options.gemini_model,
                            channel_name=channel_name,
                            video_description=video_description,
                        )
                        self._log("info", f"IA (Gemini) selecionou {len(clips)} cortes longos temáticos!")
                    except Exception as exc:
                        self._log(
                            "warning",
                            f"Erro na seleção por IA Gemini: {exc}. Agrupando segmentos sequencialmente...",
                        )
                        clips = []

                if not clips:
                    self._log("info", "Agrupando segmentos em blocos longos sequenciais...")
                    block_target = min(options.max_clip_duration, max(options.min_clip_duration, 600.0))
                    clips = []
                    curr_block: list[Segment] = []
                    for single_segment in segments:
                        curr_block.append(single_segment)
                        if (curr_block[-1].end - curr_block[0].start) >= block_target:
                            clips.append(curr_block)
                            curr_block = []
                            if len(clips) >= options.max_clips:
                                break
                    if curr_block and len(clips) < options.max_clips:
                        clips.append(curr_block)
        elif is_ai_mode:
            if not gemini_key:
                self._log(
                    "warning",
                    "GEMINI_API_KEY não configurada no .env. Alternando automaticamente para o método de Heurísticas."
                )
                is_ai_mode = False
            else:
                self._notify(
                    PipelineProgress(
                        step="heuristics",
                        step_index=5,
                        percentage=55.0,
                        message="IA (Gemini) analisando transcrição e selecionando momentos virais...",
                    )
                )
                self._log("info", "Enviando transcrição para o Google Gemini selecionar os melhores cortes virais...")
                try:
                    clips, _ = ai_create_clips(
                        segments=segments,
                        video_title=video_title,
                        min_duration=20.0,
                        max_duration=85.0,
                        max_clips=options.max_clips,
                        api_key=gemini_key,
                        model=options.gemini_model,
                        channel_name=channel_name,
                        video_description=video_description,
                    )
                    self._log("info", f"IA (Gemini) selecionou e planejou {len(clips)} cortes com sucesso!")
                except Exception as selection_error:
                    self._log("warning", f"Erro na seleção por IA Gemini: {selection_error}. Alternando para Heurísticas...")
                    clips = []
                    is_ai_mode = False

        if (not is_ai_mode or not clips) and not options.is_long_clip:
            self._notify(
                PipelineProgress(
                    step="heuristics",
                    step_index=5,
                    percentage=55.0,
                    message="Aplicando heurísticas e pontuando momentos mais engajantes...",
                )
            )
            self._log("info", "Aplicando heurísticas virais nos segmentos...")
            for segment in segments:
                apply_heuristics(segment, segments, heatmap=heatmap or None)

            # Create clips grouping via heuristics
            self._log("info", "Agrupando segmentos em clipes ideais...")
            clips = create_clips(segments, max_clips=options.max_clips)

        with open(segments_json_path, "w", encoding="utf-8") as segments_file:
            json.dump([vars(segment_obj) for segment_obj in segments], segments_file, indent=4)

        with open(clips_json_path, "w", encoding="utf-8") as clips_file:
            json.dump(
                [[vars(segment_item) for segment_item in clip_group] for clip_group in clips],
                clips_file,
                indent=4,
            )

        total_clips = len(clips)
        self._log("info", f"{total_clips} cortes identificados e planejados!")

        if total_clips == 0:
            self._log("warning", "Nenhum clipe foi gerado com as configurações atuais.")
            self._notify(
                PipelineProgress(
                    step="done",
                    step_index=6,
                    percentage=100.0,
                    message="Finalizado: nenhum clipe atendeu aos critérios.",
                    total_clips=0,
                )
            )
            
            return {"status": "done", "clips": [], "output_dir": output_dir, "slug": slug}

        if self._check_cancelled():
            return {"status": "cancelled"}

        # ── Step 6: Cut, Crop (Face Tracking), Subtitles & Metadata ───────────
        generated_clips = []
        base_pct = 60.0
        pct_per_clip = (95.0 - base_pct) / total_clips

        # ── Step 6: Cut, Crop, Subtitles & Metadata (or Timestamps Only) ──────
        generated_clips = []
        base_pct = 60.0
        pct_per_clip = (95.0 - base_pct) / total_clips

        for i, clip in enumerate(clips):
            if self._check_cancelled():
                return {"status": "cancelled"}

            start = clip[0].start
            end = clip[-1].end
            duration = end - start
            start_hms = _seconds_to_hms(start)
            end_hms = _seconds_to_hms(end)
            clip_name = f"clip_{i:02d}"
            output_video = os.path.join(clips_dir, f"{clip_name}.mp4")
            details_path = os.path.join(clips_dir, f"{clip_name}_details.json")

            current_pct = base_pct + (i * pct_per_clip)
            action_desc = "Gerando metadados" if options.only_timestamps else "Processando clipe"
            self._notify(
                PipelineProgress(
                    step="cutting",
                    step_index=6,
                    percentage=round(current_pct, 1),
                    message=f"{action_desc} {i+1} de {total_clips} ({duration:.1f}s)...",
                    current_clip=i + 1,
                    total_clips=total_clips,
                )
            )
            self._log("info", f"[{i+1}/{total_clips}] Analisando clipe {clip_name} ({start_hms} até {end_hms} - {duration:.1f}s)...")

            # Generate AI details (Title, Description, Tags) via Gemini
            video_details = {}

            if os.path.exists(details_path):
                try:
                    with open(details_path, "r", encoding="utf-8") as f:
                        video_details = json.load(f)
                except Exception:
                    video_details = {}

                if video_details and is_fallback_details(video_details):
                    self._log("info", f"Detalhes de {clip_name} vieram de um fallback; tentando gerar novamente com o Gemini...")
                    video_details = {}

            if not video_details:
                ai_meta = getattr(clip[0], "ai_metadata", None)

                if ai_meta and ai_meta.get("title") and title_problem(ai_meta["title"], video_title) is None:
                    hook_text = ai_meta.get("hook", "").strip()
                    reason_text = ai_meta.get("reason", "").strip()
                    clean_title = ai_meta.get("title", f"Corte {i+1}")

                    desc_lines = []

                    if channel_name:
                        desc_lines.append(f"Trecho de {channel_name} no episódio \"{video_title}\".")
                    if reason_text:
                        desc_lines.append(reason_text)
                    if hook_text:
                        desc_lines.append(f"\n\"{hook_text}\"")
                    
                    desc_lines.append("\nO que você pensa sobre esse assunto? Comente sua opinião!")

                    tags = ["shorts", "podcast", "cortes"]

                    if channel_name:
                        tags.append(slugify(channel_name).replace("-", ""))
                        
                    for word in clean_title.lower().replace("?", "").replace("!", "").replace(",", "").split():
                        if len(word) > 4 and word not in ("sobre", "porque", "quando", "como", "fazer", "muito", "nunca"):
                            tags.append(word)

                    tags = list(dict.fromkeys(tags))[:8]

                    video_details = {
                        "title": clean_title,
                        "description": "\n".join(desc_lines),
                        "tags": tags,
                        "viral_score": ai_meta.get("viral_score", 8.5),
                        "hook": hook_text,
                    }
                    self._log("info", f"Usando título contextualizado gerado pelo Gemini para {clip_name}...")
                    with open(details_path, "w", encoding="utf-8") as f:
                        json.dump(video_details, f, indent=4, ensure_ascii=False)
                else:
                    self._log("info", f"Gerando título contextualizado, descrição e tags com Gemini para {clip_name}...")
                    try:
                        video_details = generate_video_details(
                            long_video_title=video_title,
                            segments=clip,
                            channel_name=channel_name,
                            video_description=video_description,
                        )
                        with open(details_path, "w", encoding="utf-8") as f:
                            json.dump(video_details, f, indent=4, ensure_ascii=False)
                    except Exception as e:
                        self._log("warning", f"Erro ao gerar detalhes com Gemini para {clip_name}: {e}")
                        video_details = build_fallback_details(clip, video_title, channel_name)
                        self._log("info", f"Título provisório de {clip_name} montado a partir da fala: \"{video_details['title']}\"")
                        with open(details_path, "w", encoding="utf-8") as f:
                            json.dump(video_details, f, indent=4, ensure_ascii=False)

            if not options.only_timestamps:
                if os.path.exists(output_video) and os.path.getsize(output_video) > 10000:
                    w, h = get_video_resolution(output_video)
                    if h >= 720:
                        self._log("info", f"✅ Clipe {clip_name} já renderizado anteriormente com sucesso ({os.path.basename(output_video)}, {w}x{h}). Pulando renderização...")
                    else:
                        self._log("warning", f"Clipe existente {clip_name} possui baixa resolução ({w}x{h} < 720p). Re-renderizando em alta resolução...")
                        try:
                            os.remove(output_video)
                        except Exception:
                            pass
                
                if not os.path.exists(output_video) or os.path.getsize(output_video) <= 10000:
                    # Always download full video temporarily if not on disk (much faster than downloading section by section)
                    if not video_path or not os.path.exists(video_path):
                        self._notify(
                            PipelineProgress(
                                step="download",
                                step_index=3,
                                percentage=58.0,
                                message="Baixando vídeo completo temporariamente...",
                            )
                        )
                        video_path, _ = self._download_full_video(video_url, output_dir)

                    clip_source = video_path
                    cut_start = start
                    cut_end = end
                    adjusted_segments = clip

                    # Whisper re-transcription for high quality subtitles (not needed for AssemblyAI which already has millisecond precision)
                    whisper_subtitle_segments = None
                    # Remotion captions need Whisper word timestamps, so they force the re-transcription in every mode.
                    needs_words = options.caption_style == "remotion"
                    if options.render_subtitles and (needs_words or (options.use_whisper_subtitles and options.transcription_mode != MODE_ASSEMBLYAI)):
                        temp_audio = os.path.join(clips_dir, f"{clip_name}_temp.mp3")
                        try:
                            # clip_source is the full video, so transcribe only this clip's audio (same concatenated
                            # timeline cut_clip renders); otherwise the subtitle times are absolute and never show up.
                            extract_clip_audio(clip_source, [(seg.start, seg.end) for seg in clip], temp_audio)

                            self._log("info", f"Re-transcrevendo clipe {i:02d} com Whisper para legendas sincronizadas...")
                            whisper_subtitle_segments = transcribe_clip(temp_audio) or None
                        except Exception as e:
                            self._log("warning", f"Re-transcrição Whisper falhou para {clip_name}: {e}. Usando legendas padrão.")
                            whisper_subtitle_segments = None
                        finally:
                            if os.path.exists(temp_audio):
                                os.remove(temp_audio)

                    if self._check_cancelled():
                        return {"status": "cancelled"}

                    if options.is_long_clip:
                        silence_info = "com remoção de silêncios" if options.remove_silence else "sem corte de silêncio"

                        # Resolve overlay image: explicit option or default from env
                        overlay_to_use = (options.long_clip_overlay or "").strip().strip('"').strip("'")
                        if not overlay_to_use:
                            env_default = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
                            if env_default and os.path.exists(env_default):
                                overlay_to_use = env_default

                        overlay_info = f" + overlay '{os.path.basename(overlay_to_use)}'" if overlay_to_use and os.path.exists(overlay_to_use) else ""
                        self._log("info", f"Renderizando corte horizontal 16:9 {clip_name} ({silence_info}{overlay_info})...")
                        cut_horizontal_clip_with_silence_removal(
                            input_video=clip_source,
                            output_video=output_video,
                            start=cut_start,
                            end=cut_end,
                            remove_silence=options.remove_silence,
                            noise_threshold_db=options.silence_threshold_db,
                            min_silence_duration=options.min_silence_duration,
                            silence_padding=options.silence_padding,
                            overlay_image_path=overlay_to_use if overlay_to_use and os.path.exists(overlay_to_use) else None,
                            on_log=self._log,
                        )
                    else:
                        if options.render_subtitles:
                            self._log("info", f"Renderizando corte {clip_name} com corte vertical e legendas dinâmicas...")
                        else:
                            self._log("info", f"Renderizando corte {clip_name} com corte vertical (sem legendas renderizadas)...")

                        cut_clip(
                            input_video=clip_source,
                            output_video=output_video,
                            start=cut_start,
                            end=cut_end,
                            segments=adjusted_segments,
                            subtitle_segments_override=whisper_subtitle_segments,
                            apply_vignette=options.apply_vignette,
                            vignette_angle=options.vignette_angle,
                            render_subtitles=options.render_subtitles,
                            caption_style=options.caption_style,
                            enable_split_screen=options.enable_split_screen,
                            split_screen_chance=options.split_screen_chance,
                        )
            else:
                self._log("info", f"⏱️ [{i+1}/{total_clips}] Timestamps: {start_hms} -> {end_hms} ({duration:.1f}s) | \"{video_details['title']}\"")

            # Calculate average score of clip segments
            avg_score = sum(segment_item.score for segment_item in clip) / len(clip) if clip else 0.0

            clip_item = {
                "name": clip_name,
                "video_file": f"{clip_name}.mp4" if not options.only_timestamps else None,
                "video_path": output_video if not options.only_timestamps else None,
                "details_path": details_path,
                "start": start,
                "end": end,
                "start_formatted": start_hms,
                "end_formatted": end_hms,
                "duration": round(duration, 2),
                "score": round(avg_score, 2),
                "details": video_details,
                "rendered": not options.only_timestamps,
            }
            generated_clips.append(clip_item)

            if self.on_clip_done:
                self.on_clip_done(clip_item)

            status_msg = "Timestamps registrados" if options.only_timestamps else "Clipe finalizado"
            self._log("info", f"{status_msg}: {clip_name} com sucesso!")

        # ── Export consolidated timestamps file ───────────────────────────────
        timestamps_summary_path = os.path.join(output_dir, "timestamps.json")
        timestamps_txt_path = os.path.join(output_dir, "timestamps.txt")
        try:
            with open(timestamps_summary_path, "w", encoding="utf-8") as summary_file:
                json.dump(generated_clips, summary_file, indent=4, ensure_ascii=False)

            with open(timestamps_txt_path, "w", encoding="utf-8") as text_file:
                text_file.write(f"CORTES SELECIONADOS - {video_title}\n")
                if channel_name:
                    text_file.write(f"Canal/Podcast: {channel_name}\n")
                text_file.write(f"Total de Cortes: {len(generated_clips)}\n")
                text_file.write("=" * 60 + "\n\n")
                for clip_entry in generated_clips:
                    clip_details = clip_entry.get("details", {})
                    text_file.write(
                        f"[{clip_entry['name'].upper()}] {clip_entry['start_formatted']} -> {clip_entry['end_formatted']} ({clip_entry['duration']:.1f}s)\n"
                    )
                    text_file.write(f"Título: {clip_details.get('title', '')}\n")
                    text_file.write(
                        f"Descrição: {clip_details.get('description', '').replace(chr(10), ' ')}\n"
                    )
                    text_file.write(f"Tags: {', '.join(clip_details.get('tags', []))}\n")
                    text_file.write("-" * 60 + "\n\n")
            self._log("info", f"Arquivo consolidado de timestamps salvo em: {timestamps_txt_path}")
        except Exception as export_error:
            self._log(
                "warning",
                f"Não foi possível salvar arquivo consolidado de timestamps: {export_error}",
            )

        # ── Cleanup temporary original video ──────────────────────────────────
        if options.delete_original_video and video_path and os.path.exists(video_path):
            self._log(
                "info",
                "Removendo vídeo original completo temporário para liberar espaço em disco...",
            )
            try:
                os.remove(video_path)
                self._log("info", "Vídeo original temporário removido com sucesso!")
            except Exception as remove_error:
                self._log("warning", f"Não foi possível remover vídeo original temporário: {remove_error}")

        # ── Pipeline Complete ─────────────────────────────────────────────────
        self._notify(
            PipelineProgress(
                step="done",
                step_index=6,
                percentage=100.0,
                message=f"Processamento concluído com sucesso! {len(generated_clips)} clipes gerados.",
                current_clip=total_clips,
                total_clips=total_clips,
                data={
                    "slug": slug,
                    "output_dir": output_dir,
                    "clips_count": len(generated_clips),
                },
            )
        )
        self._log("info", f"🎉 Pipeline finalizado com sucesso! Pasta: {output_dir}")

        return {
            "status": "done",
            "slug": slug,
            "output_dir": output_dir,
            "clips": generated_clips,
        }

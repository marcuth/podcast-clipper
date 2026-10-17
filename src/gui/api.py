import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Ensure src root is in sys.path
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from src.core.pipeline import (
    MODE_WHISPER,
    MODE_YT_FULL,
    MODE_YT_PARTIAL,
    STRATEGY_AI,
    STRATEGY_HEURISTICS,
    PipelineEngine,
    PipelineOptions,
    PipelineProgress,
    _seconds_to_hms,
)
from src.services.gemini_service import get_gemini_api_key
from src.services.youtube_service import YouTubeService
from src.utils import (
    apply_overlay_to_video,
    cut_clip,
    cut_horizontal_clip_with_silence_removal,
    generate_thumbnail_for_clip,
)

logger = logging.getLogger(__name__)


class ClipperApi:
    """Native Python API exposed directly to JavaScript via pywebview (window.pywebview.api).

    All methods called from JS return a Promise in JavaScript (similar to Electron IPC).
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = workspace_root
        self.output_base = os.path.join(workspace_root, "output")
        self._window = None

        # Execution state
        self._pipeline_thread: threading.Thread | None = None
        self._cancel_token = threading.Event()
        self._is_running = False
        self._current_progress: dict[str, Any] = {
            "step": "idle",
            "step_index": 0,
            "percentage": 0.0,
            "message": "Pronto para iniciar.",
            "current_clip": 0,
            "total_clips": 0,
            "data": {},
        }
        self._recent_logs: list[dict[str, str]] = []
        self._max_logs = 300

    def set_window(self, window: Any) -> None:
        self._window = window

    def _emit_to_js(self, event_name: str, payload: Any) -> None:
        """Evaluate JS callback on the client side, pushing real-time events."""
        if not self._window:
            return
        try:
            payload_json = json.dumps(payload, ensure_ascii=False)
            script = f"window.__clipperBridge && window.__clipperBridge.emit({json.dumps(event_name)}, {payload_json});"
            self._window.evaluate_js(script)
        except Exception as exc:
            logger.debug(f"Failed to push JS event '{event_name}': {exc}")

    # ── Video info & validation ───────────────────────────────────────────────

    def get_video_info(self, url: str) -> dict[str, Any]:
        """Fetch YouTube video info (title, thumbnail, duration, author) without downloading."""
        url = (url or "").strip()
        if not PipelineEngine.is_valid_youtube_url(url):
            return {
                "success": False,
                "error": "URL inválida. Insira um link válido do YouTube (ex: youtube.com/watch?v=... ou youtu.be/...)",
            }

        try:
            info = PipelineEngine.get_video_info(url)
            return {"success": True, "data": info}
        except Exception as exc:
            logger.error(f"Error extracting video info: {exc}")
            return {"success": False, "error": f"Erro ao obter informações do vídeo: {str(exc)}"}

    # ── Pipeline execution ───────────────────────────────────────────────────

    def start_pipeline(self, options_dict: dict[str, Any]) -> dict[str, Any]:
        """Start the clipper pipeline in a background thread."""
        if self._is_running:
            return {"success": False, "error": "Um processo já está em execução."}

        url = options_dict.get("url", "").strip()

        if not PipelineEngine.is_valid_youtube_url(url):
            return {"success": False, "error": "URL do YouTube inválida."}

        mode = options_dict.get("transcription_mode", MODE_YT_PARTIAL)
        if mode not in (MODE_WHISPER, MODE_YT_FULL, MODE_YT_PARTIAL):
            mode = MODE_YT_PARTIAL

        render_subtitles = bool(options_dict.get("render_subtitles", True))
        use_whisper_subs = bool(options_dict.get("use_whisper_subtitles", True))
        use_heatmap = bool(options_dict.get("use_heatmap", True))
        apply_vignette = bool(options_dict.get("apply_vignette", True))
        vignette_angle = str(options_dict.get("vignette_angle", "PI/4"))
        enable_split_screen = bool(options_dict.get("enable_split_screen", True))
        split_screen_chance = float(options_dict.get("split_screen_chance", 0.5))
        only_timestamps = bool(options_dict.get("only_timestamps", False))
        clipping_strategy = str(options_dict.get("clipping_strategy", STRATEGY_AI))

        if clipping_strategy not in (STRATEGY_AI, STRATEGY_HEURISTICS):
            clipping_strategy = STRATEGY_AI

        is_long_clip = bool(options_dict.get("is_long_clip", False))
        remove_silence = bool(options_dict.get("remove_silence", True))
        silence_threshold_db = float(options_dict.get("silence_threshold_db", -30.0))
        min_silence_duration = float(options_dict.get("min_silence_duration", 0.6))
        silence_padding = float(options_dict.get("silence_padding", 0.15))
        min_clip_duration = float(options_dict.get("min_clip_duration", 180.0))
        max_clip_duration = float(options_dict.get("max_clip_duration", 1200.0))
        default_max_clips = 3 if is_long_clip else 8
        max_clips = int(options_dict.get("max_clips", default_max_clips))
        custom_start = options_dict.get("custom_start_time")
        custom_end = options_dict.get("custom_end_time")
        custom_start_time = float(custom_start) if custom_start is not None and str(custom_start).strip() != "" else None
        custom_end_time = float(custom_end) if custom_end is not None and str(custom_end).strip() != "" else None
        delete_original_video = bool(options_dict.get("delete_original_video", True))
        long_clip_overlay = options_dict.get("long_clip_overlay")

        if isinstance(long_clip_overlay, str):
            long_clip_overlay = long_clip_overlay.strip()
            if not long_clip_overlay:
                long_clip_overlay = None

        pipeline_options = PipelineOptions(
            video_url=url,
            transcription_mode=mode,
            render_subtitles=False if is_long_clip else render_subtitles,
            use_whisper_subtitles=use_whisper_subs,
            use_heatmap=use_heatmap,
            output_base_dir=self.output_base,
            apply_vignette=apply_vignette,
            vignette_angle=vignette_angle,
            enable_split_screen=enable_split_screen,
            split_screen_chance=split_screen_chance,
            only_timestamps=only_timestamps,
            clipping_strategy=clipping_strategy,
            is_long_clip=is_long_clip,
            remove_silence=remove_silence,
            silence_threshold_db=silence_threshold_db,
            min_silence_duration=min_silence_duration,
            silence_padding=silence_padding,
            min_clip_duration=min_clip_duration,
            max_clip_duration=max_clip_duration,
            max_clips=max_clips,
            custom_start_time=custom_start_time,
            custom_end_time=custom_end_time,
            delete_original_video=delete_original_video,
            long_clip_overlay=long_clip_overlay,
        )

        self._cancel_token.clear()
        self._is_running = True
        self._recent_logs.clear()
        self._current_progress = {
            "step": "init",
            "step_index": 1,
            "percentage": 0.0,
            "message": "Inicializando pipeline...",
            "current_clip": 0,
            "total_clips": 0,
            "data": {},
        }

        def on_progress(p: PipelineProgress) -> None:
            data = {
                "step": p.step,
                "step_index": p.step_index,
                "percentage": p.percentage,
                "message": p.message,
                "current_clip": p.current_clip,
                "total_clips": p.total_clips,
                "data": p.data,
            }
            self._current_progress = data
            self._emit_to_js("progress", data)

        def on_log(level: str, message: str) -> None:
            log_item = {"level": level, "message": message}
            self._recent_logs.append(log_item)

            if len(self._recent_logs) > self._max_logs:
                self._recent_logs.pop(0)
                
            self._emit_to_js("log", log_item)

        def on_clip_done(clip_data: dict[str, Any]) -> None:
            self._emit_to_js("clip_done", clip_data)

        def worker() -> None:
            engine = PipelineEngine(
                on_progress=on_progress,
                on_log=on_log,
                on_clip_done=on_clip_done,
                cancel_token=self._cancel_token,
            )
            try:
                result = engine.run(pipeline_options)
                self._emit_to_js("pipeline_finished", {"success": True, "result": result})
            except Exception as exc:
                logger.error(f"Pipeline error: {exc}", exc_info=True)
                err_msg = str(exc)
                on_log("error", f"Erro crítico no processamento: {err_msg}")
                self._current_progress = {
                    "step": "error",
                    "step_index": 0,
                    "percentage": 0.0,
                    "message": f"Erro: {err_msg}",
                    "current_clip": 0,
                    "total_clips": 0,
                    "data": {},
                }
                self._emit_to_js("progress", self._current_progress)
                self._emit_to_js("pipeline_finished", {"success": False, "error": err_msg})
            finally:
                self._is_running = False

        self._pipeline_thread = threading.Thread(target=worker, daemon=True)
        self._pipeline_thread.start()

        return {"success": True, "message": "Processamento iniciado com sucesso."}

    def cancel_pipeline(self) -> dict[str, Any]:
        """Cancel the ongoing pipeline run."""
        if not self._is_running:
            return {"success": False, "message": "Nenhum processo ativo para cancelar."}

        self._cancel_token.set()
        return {"success": True, "message": "Solicitação de cancelamento enviada."}

    def get_status(self) -> dict[str, Any]:
        """Query the current state, progress and recent logs (useful for initial sync or polling)."""
        return {
            "is_running": self._is_running,
            "progress": self._current_progress,
            "logs": self._recent_logs[-50:],
        }

    # ── Projects & Clips management ──────────────────────────────────────────

    def get_projects(self) -> list[dict[str, Any]]:
        """List all generated project folders inside output/."""
        if not os.path.exists(self.output_base):
            return []

        projects = []
        for entry in os.listdir(self.output_base):
            project_dir = os.path.join(self.output_base, entry)
            if not os.path.isdir(project_dir):
                continue

            clips_dir = os.path.join(project_dir, "clips")
            video_count = 0
            metadata_count = 0
            if os.path.exists(clips_dir):
                video_count = len(
                    [
                        file_name
                        for file_name in os.listdir(clips_dir)
                        if file_name.endswith(".mp4") and not file_name.endswith("_raw.mp4")
                    ]
                )
                metadata_count = len(
                    [
                        file_name
                        for file_name in os.listdir(clips_dir)
                        if file_name.endswith("_details.json")
                    ]
                )

            clips_count = max(video_count, metadata_count)

            # Detect if it's a timestamps-only project
            has_timestamps = os.path.exists(os.path.join(project_dir, "timestamps.json"))
            is_timestamps_only = has_timestamps and video_count == 0 and metadata_count > 0

            # Try to fetch title from first clip details or format slug
            title = entry.replace("-", " ").title()
            first_details = os.path.join(clips_dir, "clip_00_details.json") if os.path.exists(clips_dir) else ""
            if first_details and os.path.exists(first_details):
                try:
                    with open(first_details, "r", encoding="utf-8") as details_file:
                        details_data = json.load(details_file)
                        if details_data.get("title"):
                            title = details_data["title"]
                except Exception:
                    pass

            mtime = os.path.getmtime(project_dir)
            projects.append(
                {
                    "slug": entry,
                    "name": title,
                    "clips_count": clips_count,
                    "modified_at": mtime,
                    "path": project_dir,
                    "is_timestamps_only": is_timestamps_only,
                }
            )

        projects.sort(key=lambda item: item["modified_at"], reverse=True)
        return projects

    def get_project_clips(self, slug: str) -> list[dict[str, Any]]:
        """List all clips belonging to a project with their metadata.

        Supports both rendered clips (with .mp4 files) and timestamp-only clips
        (with _details.json but no video).
        """
        project_dir = os.path.join(self.output_base, slug)
        clips_dir = os.path.join(project_dir, "clips")
        if not os.path.exists(clips_dir):
            return []

        clips_plan_file = os.path.join(
            project_dir,
            "long_clips.json" if os.path.exists(os.path.join(project_dir, "long_clips.json")) else "clips.json"
        )
        clips_plan = []
        if os.path.exists(clips_plan_file):
            try:
                with open(clips_plan_file, "r", encoding="utf-8") as plan_handle:
                    clips_plan = json.load(plan_handle)
            except Exception:
                clips_plan = []

        # Load timestamps.json for timestamp data (start, end, duration, etc.)
        timestamps_file = os.path.join(project_dir, "timestamps.json")
        timestamps_data: list[dict[str, Any]] = []
        if os.path.exists(timestamps_file):
            try:
                with open(timestamps_file, "r", encoding="utf-8") as timestamps_handle:
                    timestamps_data = json.load(timestamps_handle)
            except Exception:
                timestamps_data = []
        timestamps_by_name: dict[str, dict[str, Any]] = {
            item["name"]: item for item in timestamps_data if "name" in item
        }

        # Discover all unique clip names from both .mp4 and _details.json
        clip_files = sorted(
            [
                file_name
                for file_name in os.listdir(clips_dir)
                if file_name.endswith(".mp4") and not file_name.endswith("_raw.mp4")
            ]
        )
        video_clip_names = {file_name[:-4] for file_name in clip_files}  # e.g. {"clip_00", "clip_01"}

        detail_files = sorted(
            [
                file_name
                for file_name in os.listdir(clips_dir)
                if file_name.endswith("_details.json")
            ]
        )
        detail_clip_names = {file_name.replace("_details.json", "") for file_name in detail_files}

        # Merge: all clips that have either a video or metadata
        all_clip_names = sorted(video_clip_names | detail_clip_names)

        results = []
        for clip_index, clip_name in enumerate(all_clip_names):
            has_video = clip_name in video_clip_names
            video_filename = f"{clip_name}.mp4" if has_video else None
            video_path = os.path.join(clips_dir, f"{clip_name}.mp4") if has_video else None
            details_file = os.path.join(clips_dir, f"{clip_name}_details.json")

            details: dict[str, Any] = {
                "title": f"Corte {clip_index + 1}",
                "description": "",
                "tags": [],
            }
            if os.path.exists(details_file):
                try:
                    with open(details_file, "r", encoding="utf-8") as details_handle:
                        details = json.load(details_handle)
                except Exception:
                    pass

            # Get score, duration, and timestamps from plan or timestamps.json
            score = 0.0
            duration = 0.0
            start_time = 0.0
            end_time = 0.0
            start_formatted = ""
            end_formatted = ""

            ts_entry = timestamps_by_name.get(clip_name)
            
            if ts_entry:
                start_time = ts_entry.get("start", 0.0)
                end_time = ts_entry.get("end", 0.0)
                duration = ts_entry.get("duration", end_time - start_time)
                score = ts_entry.get("score", 0.0)
                start_formatted = ts_entry.get("start_formatted", "")
                end_formatted = ts_entry.get("end_formatted", "")
            elif clip_index < len(clips_plan):
                clip_segs = clips_plan[clip_index]
                if clip_segs:
                    start_time = clip_segs[0].get("start", 0.0)
                    end_time = clip_segs[-1].get("end", 0.0)
                    duration = end_time - start_time
                    scores = [segment_item.get("score", 0.0) for segment_item in clip_segs]
                    score = sum(scores) / len(scores) if scores else 0.0

            # Also try viral_score from details (AI-generated)
            if score == 0.0 and details.get("viral_score"):
                score = float(details["viral_score"])

            mtime = int(os.path.getmtime(video_path)) if video_path and os.path.exists(video_path) else int(time.time())
            thumb_filename = f"{clip_name}_thumb.jpg"
            thumb_path = os.path.join(clips_dir, thumb_filename)
            has_thumb = os.path.exists(thumb_path)
            mtime_thumb = int(os.path.getmtime(thumb_path)) if has_thumb else 0
            thumb_url = f"/media/{slug}/clips/{thumb_filename}?v={mtime_thumb}" if has_thumb else None

            results.append(
                {
                    "name": clip_name,
                    "video_file": video_filename,
                    "video_url": f"/media/{slug}/clips/{video_filename}?v={mtime}" if video_filename else None,
                    "video_path": video_path,
                    "thumbnail_file": thumb_filename if has_thumb else None,
                    "thumbnail_url": thumb_url,
                    "thumbnail_path": thumb_path if has_thumb else None,
                    "details_path": details_file,
                    "score": round(score, 2),
                    "duration": round(duration, 1),
                    "start": round(start_time, 2),
                    "end": round(end_time, 2),
                    "start_formatted": start_formatted,
                    "end_formatted": end_formatted,
                    "title": details.get("title", f"Corte {clip_index + 1}"),
                    "description": details.get("description", ""),
                    "tags": details.get("tags", []),
                    "hook": details.get("hook", ""),
                    "rendered": has_video,
                }
            )

        return results

    def update_clip_details(self, slug: str, clip_name: str, details: dict[str, Any]) -> dict[str, Any]:
        """Save user-edited metadata for a specific clip."""
        details_file = os.path.join(self.output_base, slug, "clips", f"{clip_name}_details.json")

        try:
            with open(details_file, "w", encoding="utf-8") as details_handle:
                json.dump(details, details_handle, indent=4, ensure_ascii=False)
            return {"success": True, "message": "Metadados atualizados com sucesso."}

        except Exception as exc:
            logger.error(f"Error saving clip details: {exc}")
            return {"success": False, "error": str(exc)}

    # ── OS native utilities ──────────────────────────────────────────────────

    def open_folder(self, target_path: str) -> bool:
        """Open a folder in Windows File Explorer."""
        try:
            full_path = os.path.abspath(target_path)
            if not os.path.exists(full_path):
                full_path = os.path.dirname(full_path)
            if os.path.exists(full_path):
                os.startfile(full_path)
                return True
        except Exception as exc:
            logger.error(f"Failed to open folder '{target_path}': {exc}")

        return False

    def open_video(self, video_path: str) -> bool:
        """Open a video in the user's default system video player."""
        try:
            full_path = os.path.abspath(video_path)
            if os.path.exists(full_path):
                os.startfile(full_path)
                return True
        except Exception as exc:
            logger.error(f"Failed to open video '{video_path}': {exc}")
        return False

    # ── System diagnostics ───────────────────────────────────────────────────

    def get_system_info(self) -> dict[str, Any]:
        """Return diagnostic system info (Gemini API, Python version, hardware acceleration)."""
        gemini_key = get_gemini_api_key()
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        has_face_model = os.path.exists(os.path.join(self.workspace_root, "models", "blaze_face_short_range.tflite"))

        gemini_preview = ""
        if gemini_key:
            gemini_preview = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else "***"

        default_overlay = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
        has_default_overlay = bool(default_overlay and os.path.exists(default_overlay))

        return {
            "python_version": sys.version.split()[0],
            "os": "Windows 10",
            "gemini_configured": bool(gemini_key),
            "gemini_key_preview": gemini_preview,
            "gemini_model": gemini_model,
            "face_model_available": has_face_model,
            "workspace_dir": self.workspace_root,
            "output_dir": self.output_base,
            "default_long_clip_overlay": default_overlay,
            "has_default_overlay": has_default_overlay,
        }

    def save_gemini_api_key(self, api_key: str) -> dict[str, Any]:
        """Save GEMINI_API_KEY to .env file and active environment."""
        clean_key = (api_key or "").strip()
        if not clean_key:
            return {"success": False, "error": "Chave de API não pode ser vazia."}

        env_path = os.path.join(self.workspace_root, ".env")
        try:
            env_lines = []
            key_found = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as env_read_handle:
                    env_lines = env_read_handle.readlines()

            updated_lines = []
            for current_line in env_lines:
                if current_line.strip().startswith("GEMINI_API_KEY"):
                    updated_lines.append(f'GEMINI_API_KEY = "{clean_key}"\n')
                    key_found = True
                else:
                    updated_lines.append(current_line)

            if not key_found:
                updated_lines.append(f'\nGEMINI_API_KEY = "{clean_key}"\n')

            with open(env_path, "w", encoding="utf-8") as env_write_handle:
                env_write_handle.writelines(updated_lines)

            os.environ["GEMINI_API_KEY"] = clean_key
            logger.info("GEMINI_API_KEY salva com sucesso no .env!")
            return {"success": True, "message": "Chave Gemini salva com sucesso."}
        except Exception as exc:
            logger.error(f"Erro ao salvar chave Gemini no .env: {exc}")
            return {"success": False, "error": str(exc)}

    def save_gemini_model(self, model_name: str) -> dict[str, Any]:
        """Save GEMINI_MODEL to .env file and active environment."""
        clean_model = (model_name or "").strip()
        if not clean_model:
            return {"success": False, "error": "Nome do modelo não pode ser vazio."}

        env_path = os.path.join(self.workspace_root, ".env")
        try:
            env_lines = []
            model_found = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as env_read_handle:
                    env_lines = env_read_handle.readlines()

            updated_lines = []
            for current_line in env_lines:
                if current_line.strip().startswith("GEMINI_MODEL"):
                    updated_lines.append(f'GEMINI_MODEL = "{clean_model}"\n')
                    model_found = True
                else:
                    updated_lines.append(current_line)

            if not model_found:
                updated_lines.append(f'\nGEMINI_MODEL = "{clean_model}"\n')

            with open(env_path, "w", encoding="utf-8") as env_write_handle:
                env_write_handle.writelines(updated_lines)

            os.environ["GEMINI_MODEL"] = clean_model
            logger.info(f"GEMINI_MODEL '{clean_model}' salvo com sucesso no .env!")
            return {"success": True, "message": f"Modelo Gemini '{clean_model}' salvo com sucesso."}
        except Exception as exc:
            logger.error(f"Erro ao salvar GEMINI_MODEL no .env: {exc}")
            return {"success": False, "error": str(exc)}

    def select_overlay_file(self) -> dict[str, Any]:
        """Open native OS file picker to select an image overlay file."""
        if not self._window:
            return {"success": False, "error": "Janela nativa não disponível"}

        try:
            import webview
            file_types = ("Arquivos de Imagem (*.png;*.jpg;*.jpeg;*.webp)", "Todos os arquivos (*.*)")
            dialog_flag = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else getattr(webview, "OPEN_DIALOG", 10)
            dialog_result = self._window.create_file_dialog(
                dialog_flag,
                allow_multiple=False,
                file_types=file_types,
            )
            if dialog_result and len(dialog_result) > 0:
                selected_path = dialog_result[0]
                return {"success": True, "file_path": selected_path}
            return {"success": False, "cancelled": True}
        except Exception as exc:
            logger.error(f"Erro ao abrir seletor de arquivo de overlay: {exc}")
            return {"success": False, "error": str(exc)}

    def save_default_long_clip_overlay(self, overlay_path: str) -> dict[str, Any]:
        """Save DEFAULT_LONG_CLIP_OVERLAY to .env file and active environment."""
        clean_path = (overlay_path or "").strip().strip('"').strip("'")
        env_path = os.path.join(self.workspace_root, ".env")
        try:
            env_lines = []
            overlay_found = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as env_read_handle:
                    env_lines = env_read_handle.readlines()

            updated_lines = []
            for current_line in env_lines:
                if current_line.strip().startswith("DEFAULT_LONG_CLIP_OVERLAY"):
                    updated_lines.append(f'DEFAULT_LONG_CLIP_OVERLAY = "{clean_path}"\n')
                    overlay_found = True
                else:
                    updated_lines.append(current_line)

            if not overlay_found:
                updated_lines.append(f'\nDEFAULT_LONG_CLIP_OVERLAY = "{clean_path}"\n')

            with open(env_path, "w", encoding="utf-8") as env_write_handle:
                env_write_handle.writelines(updated_lines)

            os.environ["DEFAULT_LONG_CLIP_OVERLAY"] = clean_path
            logger.info(f"DEFAULT_LONG_CLIP_OVERLAY '{clean_path}' salvo com sucesso no .env!")
            return {"success": True, "message": "Overlay padrão salvo com sucesso no .env."}
        except Exception as exc:
            logger.error(f"Erro ao salvar DEFAULT_LONG_CLIP_OVERLAY no .env: {exc}")
            return {"success": False, "error": str(exc)}

    # ── YouTube integration ──────────────────────────────────────────────────

    def get_youtube_status(self) -> dict[str, Any]:
        """Check if YouTube API credentials (client_secret.json and credentials.storage) are configured."""
        try:
            youtube_service = YouTubeService()
            auth_info = youtube_service.get_auth_status()
            return {"success": True, "data": auth_info}
        except Exception as check_error:
            logger.error(f"Erro ao verificar status do YouTube: {check_error}")
            return {"success": False, "error": str(check_error)}

    def upload_clip_to_youtube(
        self,
        slug: str,
        clip_name: str,
        privacy: str = "public",
        category: str = "Entertainment",
        schedule_time: str | None = None,
    ) -> dict[str, Any]:
        """Upload a generated clip to YouTube via simple-youtube-api."""
        clips_directory = os.path.join(self.output_base, slug, "clips")
        video_file_path = os.path.join(clips_directory, f"{clip_name}.mp4")

        if not os.path.exists(video_file_path):
            return {
                "success": False,
                "error": f"Vídeo do corte não encontrado: {video_file_path}",
            }

        details_file_path = os.path.join(clips_directory, f"{clip_name}_details.json")
        clip_details: dict[str, Any] = {}
        if os.path.exists(details_file_path):
            try:
                with open(details_file_path, "r", encoding="utf-8") as details_file:
                    clip_details = json.load(details_file)
            except Exception as details_error:
                logger.warning(f"Não foi possível ler metadados do corte: {details_error}")

        if not clip_details.get("title"):
            clip_details["title"] = clip_name.replace("_", " ").title()

        youtube_service = YouTubeService()
        if not youtube_service.is_configured():
            return {
                "success": False,
                "error": "Arquivo 'client_secret.json' não encontrado na raiz do projeto. "
                         "Baixe as credenciais OAuth do Google Cloud Console para habilitar uploads no YouTube.",
            }

        upload_result = youtube_service.upload_clip(
            video_path=video_file_path,
            details=clip_details,
            privacy_status=privacy,
            category=category,
            publish_at=schedule_time,
        )

        return upload_result

    def save_youtube_client_secret(self, client_secret_json: str) -> dict[str, Any]:
        """Save YOUTUBE_CLIENT_SECRET to .env file and write client_secret.json."""
        raw_json = (client_secret_json or "").strip()
        if not raw_json:
            return {"success": False, "error": "O JSON do client_secret não pode ser vazio."}

        try:
            # Strip quotes if wrapped
            if (raw_json.startswith("'") and raw_json.endswith("'")) or (
                raw_json.startswith('"') and raw_json.endswith('"')
            ):
                raw_json = raw_json[1:-1].strip()
            parsed = json.loads(raw_json)
        except Exception as err:
            return {"success": False, "error": f"JSON inválido: {err}"}

        env_path = os.path.join(self.workspace_root, ".env")
        try:
            minified_json = json.dumps(parsed, ensure_ascii=False)
            env_lines = []
            secret_found = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    env_lines = f.readlines()

            updated_lines = []
            for line in env_lines:
                if line.strip().startswith("YOUTUBE_CLIENT_SECRET"):
                    updated_lines.append(f"YOUTUBE_CLIENT_SECRET = '{minified_json}'\n")
                    secret_found = True
                else:
                    updated_lines.append(line)

            if not secret_found:
                updated_lines.append(f"\nYOUTUBE_CLIENT_SECRET = '{minified_json}'\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)

            os.environ["YOUTUBE_CLIENT_SECRET"] = minified_json

            # Ensure client_secret.json is written
            youtube_service = YouTubeService()
            youtube_service._ensure_client_secrets_file()

            logger.info("YOUTUBE_CLIENT_SECRET salvo com sucesso no .env!")
            return {
                "success": True,
                "message": "Credencial YOUTUBE_CLIENT_SECRET salva com sucesso no .env e sincronizada!",
            }
        except Exception as exc:
            logger.error(f"Erro ao salvar YOUTUBE_CLIENT_SECRET no .env: {exc}")
            return {"success": False, "error": str(exc)}

    def apply_clip_overlay(
        self,
        slug: str,
        clip_name: str,
        overlay_path: str,
    ) -> dict[str, Any]:
        """Apply an overlay image directly to an already rendered clip."""
        clean_overlay = (overlay_path or "").strip().strip('"').strip("'")
        if not clean_overlay or not os.path.exists(clean_overlay):
            return {"success": False, "error": f"Arquivo de overlay não encontrado: '{clean_overlay}'"}

        clip_path = os.path.join(self.output_base, slug, "clips", f"{clip_name}.mp4")
        if not os.path.exists(clip_path):
            return {
                "success": False,
                "error": f"Vídeo do corte '{clip_name}' não existe ainda para aplicar overlay.",
            }

        try:
            self._emit_to_js(
                "log",
                {"level": "info", "message": f"Aplicando overlay '{os.path.basename(clean_overlay)}' em {clip_name}..."},
            )
            success = apply_overlay_to_video(
                input_video=clip_path,
                overlay_image_path=clean_overlay,
                on_log=lambda lvl, msg: self._emit_to_js("log", {"level": lvl, "message": msg}),
            )
            if success:
                self._emit_to_js(
                    "log",
                    {"level": "info", "message": f"✅ Overlay aplicado com sucesso em {clip_name}!"},
                )
                return {
                    "success": True,
                    "message": f"Overlay aplicado com sucesso em '{clip_name}'!",
                    "video_url": f"/media/{slug}/clips/{clip_name}.mp4?t={int(time.time())}",
                }
            return {"success": False, "error": "Falha ao aplicar overlay com FFmpeg."}
        except Exception as exc:
            logger.error(f"Erro ao aplicar overlay em {clip_name}: {exc}")
            return {"success": False, "error": str(exc)}

    def rerender_clip(
        self,
        slug: str,
        clip_name: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Re-render a specific clip with customizable parameters (bounds, overlay, silence removal)."""
        options = options or {}
        project_dir = os.path.join(self.output_base, slug)
        clips_dir = os.path.join(project_dir, "clips")

        if not os.path.exists(project_dir):
            return {"success": False, "error": f"Projeto '{slug}' não encontrado."}

        # 1. Discover timestamps and details
        start_time = options.get("start")
        end_time = options.get("end")

        timestamps_file = os.path.join(project_dir, "timestamps.json")
        if start_time is None or end_time is None:
            if os.path.exists(timestamps_file):
                try:
                    with open(timestamps_file, "r", encoding="utf-8") as f:
                        ts_list = json.load(f)
                        for item in ts_list:
                            if item.get("name") == clip_name:
                                start_time = float(item["start"])
                                end_time = float(item["end"])
                                break
                except Exception:
                    pass

        if start_time is None or end_time is None:
            for plan_name in ["long_clips.json", "clips.json"]:
                clips_plan_file = os.path.join(project_dir, plan_name)
                if os.path.exists(clips_plan_file):
                    try:
                        with open(clips_plan_file, "r", encoding="utf-8") as f:
                            plan_list = json.load(f)
                            clip_idx = int(clip_name.replace("clip_", ""))
                            if 0 <= clip_idx < len(plan_list):
                                clip_segs = plan_list[clip_idx]
                                start_time = float(clip_segs[0]["start"])
                                end_time = float(clip_segs[-1]["end"])
                                break
                    except Exception:
                        pass

        if start_time is None or end_time is None:
            return {
                "success": False,
                "error": f"Não foi possível determinar os tempos de início e fim para '{clip_name}'.",
            }

        start_time = float(start_time)
        end_time = float(end_time)

        # 2. Source video discovery
        video_path = os.path.join(project_dir, "video.mp4")
        if not os.path.exists(video_path):
            meta_file = os.path.join(project_dir, "project_meta.json")
            video_url = options.get("video_url")
            if not video_url and os.path.exists(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        video_url = meta.get("video_url")
                except Exception:
                    pass

            if not video_url:
                return {
                    "success": False,
                    "error": (
                        f"Vídeo original não encontrado em '{video_path}' e URL do YouTube desconhecida. "
                        "Informe a URL do vídeo para baixar e re-renderizar."
                    ),
                }

            try:
                engine = PipelineEngine()
                self._emit_to_js(
                    "log",
                    {"level": "info", "message": f"Baixando vídeo original para re-renderizar {clip_name}..."},
                )
                video_path, _ = engine._download_full_video(video_url, project_dir)
            except Exception as dl_err:
                return {"success": False, "error": f"Erro ao baixar vídeo original: {dl_err}"}

        # 3. Destination paths
        output_video = os.path.join(clips_dir, f"{clip_name}.mp4")
        temp_target = os.path.join(clips_dir, f"{clip_name}_rerender.mp4")

        # 4. Parameters
        is_long = bool(options.get("is_long_clip", True))
        remove_silence = bool(options.get("remove_silence", True))
        silence_threshold = float(options.get("silence_threshold_db", -30))
        min_silence = float(options.get("min_silence_duration", 0.6))
        silence_padding = float(options.get("silence_padding", 0.15))

        overlay_to_use = (options.get("overlay_image_path") or "").strip().strip('"').strip("'")
        if not overlay_to_use:
            env_overlay = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
            if env_overlay and os.path.exists(env_overlay):
                overlay_to_use = env_overlay

        try:
            overlay_info = f" + overlay '{os.path.basename(overlay_to_use)}'" if overlay_to_use and os.path.exists(overlay_to_use) else ""
            self._emit_to_js(
                "log",
                {
                    "level": "info",
                    "message": f"Iniciando re-renderização de {clip_name} ({start_time:.1f}s -> {end_time:.1f}s{overlay_info})...",
                },
            )

            if is_long:
                result = cut_horizontal_clip_with_silence_removal(
                    input_video=video_path,
                    output_video=temp_target,
                    start=start_time,
                    end=end_time,
                    remove_silence=remove_silence,
                    noise_threshold_db=silence_threshold,
                    min_silence_duration=min_silence,
                    silence_padding=silence_padding,
                    overlay_image_path=overlay_to_use if overlay_to_use and os.path.exists(overlay_to_use) else None,
                    on_log=lambda lvl, msg: self._emit_to_js("log", {"level": lvl, "message": msg}),
                )
                if not result.get("success", False):
                    if os.path.exists(temp_target):
                        os.remove(temp_target)
                    return {"success": False, "error": result.get("error", "Erro ao processar corte.")}
            else:
                cut_clip(
                    input_video=video_path,
                    output_video=temp_target,
                    start=start_time,
                    end=end_time,
                    render_subtitles=options.get("render_subtitles", True),
                )

            # Atomically replace output file
            if os.path.exists(output_video):
                try:
                    os.remove(output_video)
                except Exception:
                    pass
            os.replace(temp_target, output_video)

            # Update timestamps.json with the new bounds and duration
            if os.path.exists(timestamps_file):
                try:
                    with open(timestamps_file, "r", encoding="utf-8") as tf:
                        all_ts = json.load(tf)
                    updated = False
                    for item in all_ts:
                        if item.get("name") == clip_name:
                            item["start"] = start_time
                            item["end"] = end_time
                            item["duration"] = round(end_time - start_time, 2)
                            item["start_formatted"] = _seconds_to_hms(start_time)
                            item["end_formatted"] = _seconds_to_hms(end_time)
                            item["rendered"] = True
                            updated = True
                            break
                    if updated:
                        with open(timestamps_file, "w", encoding="utf-8") as tf:
                            json.dump(all_ts, tf, indent=4, ensure_ascii=False)
                except Exception as update_err:
                    logger.warning(f"Não foi possível atualizar timestamps.json: {update_err}")

            self._emit_to_js(
                "log",
                {"level": "info", "message": f"✅ {clip_name} re-renderizado com sucesso!"},
            )
            return {
                "success": True,
                "message": f"Vídeo '{clip_name}' re-renderizado com sucesso!",
                "video_url": f"/media/{slug}/clips/{clip_name}.mp4?t={int(time.time())}",
            }
        except Exception as exc:
            logger.error(f"Erro ao re-renderizar clipe {clip_name}: {exc}", exc_info=True)
            if os.path.exists(temp_target):
                try:
                    os.remove(temp_target)
                except Exception:
                    pass
            return {"success": False, "error": str(exc)}

    def generate_clip_thumbnail(
        self,
        slug: str,
        clip_name: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate high-CTR YouTube thumbnail using face detection and Gemini viral hook strategy."""
        options = options or {}
        project_dir = os.path.join(self.output_base, slug)
        clips_dir = os.path.join(project_dir, "clips")

        if not os.path.exists(project_dir):
            return {"success": False, "error": f"Projeto '{slug}' não encontrado."}

        # Prefer full video if available (contains 16:9 widescreen context with all speakers)
        clip_video_path = os.path.join(clips_dir, f"{clip_name}.mp4")
        full_video_path = os.path.join(project_dir, "video.mp4")

        video_to_use = full_video_path if os.path.exists(full_video_path) else clip_video_path
        if not os.path.exists(video_to_use):
            return {
                "success": False,
                "error": f"Vídeo não encontrado para extrair thumbnail em '{video_to_use}'.",
            }

        start_time = 0.0
        end_time = 0.0
        clip_title = f"Corte - {slug}"
        clip_context = ""

        timestamps_file = os.path.join(project_dir, "timestamps.json")
        if os.path.exists(timestamps_file):
            try:
                with open(timestamps_file, "r", encoding="utf-8") as tf:
                    ts_list = json.load(tf)
                for item in ts_list:
                    if item.get("name") == clip_name:
                        start_time = float(item.get("start", 0.0))
                        end_time = float(item.get("end", 0.0))
                        item_details = item.get("details", {})
                        clip_title = item_details.get("title", clip_title)
                        clip_context = item_details.get("description", "")
                        break
            except Exception:
                pass

        details_file = os.path.join(clips_dir, f"{clip_name}_details.json")
        if os.path.exists(details_file):
            try:
                with open(details_file, "r", encoding="utf-8") as df:
                    d_data = json.load(df)
                clip_title = d_data.get("title", clip_title)
                clip_context = d_data.get("description", clip_context)
            except Exception:
                pass

        if video_to_use == clip_video_path:
            start_time = 0.0
            end_time = 0.0

        output_thumb = os.path.join(clips_dir, f"{clip_name}_thumb.jpg")
        overlay_to_use = options.get("overlay_image_path")
        if not overlay_to_use:
            load_dotenv(override=True)
            env_overlay = os.environ.get("DEFAULT_LONG_CLIP_OVERLAY", "").strip().strip('"').strip("'")
            if env_overlay and os.path.exists(env_overlay):
                overlay_to_use = env_overlay

        try:
            self._emit_to_js(
                "log",
                {"level": "info", "message": f"Iniciando criação de Thumbnail inteligente para {clip_name}..."},
            )
            result = generate_thumbnail_for_clip(
                video_path=video_to_use,
                output_thumb_path=output_thumb,
                clip_title=clip_title,
                start_time=start_time,
                end_time=end_time,
                clip_context=clip_context,
                overlay_image_path=overlay_to_use,
                on_log=lambda lvl, msg: self._emit_to_js("log", {"level": lvl, "message": msg}),
            )
            if not result.get("success", False):
                return result

            # Update timestamps.json
            if os.path.exists(timestamps_file):
                try:
                    with open(timestamps_file, "r", encoding="utf-8") as tf:
                        ts_list = json.load(tf)
                    for item in ts_list:
                        if item.get("name") == clip_name:
                            item["thumbnail_path"] = output_thumb
                            break
                    with open(timestamps_file, "w", encoding="utf-8") as tf:
                        json.dump(ts_list, tf, indent=4, ensure_ascii=False)
                except Exception:
                    pass

            mtime_thumb = int(os.path.getmtime(output_thumb))
            thumb_url = f"/media/{slug}/clips/{clip_name}_thumb.jpg?v={mtime_thumb}"

            self._emit_to_js(
                "log",
                {"level": "info", "message": f"✅ Thumbnail criada: '{result.get('hook_text')}' ({clip_name})!"},
            )

            return {
                "success": True,
                "message": f"Thumbnail gerada com sucesso: '{result.get('hook_text')}'!",
                "thumbnail_url": thumb_url,
                "thumbnail_path": output_thumb,
                "hook_text": result.get("hook_text"),
                "badge_text": result.get("badge_text"),
                "color": result.get("color"),
            }
        except Exception as exc:
            logger.error(f"Erro ao gerar thumbnail para {clip_name}: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}



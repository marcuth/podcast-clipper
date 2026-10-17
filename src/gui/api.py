import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

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
)
from src.services.gemini_service import get_gemini_api_key

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
        max_clips = int(options_dict.get("max_clips", 3))
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

        clips_plan_file = os.path.join(project_dir, "clips.json")
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

            results.append(
                {
                    "name": clip_name,
                    "video_file": video_filename,
                    "video_url": f"/media/{slug}/clips/{video_filename}" if video_filename else None,
                    "video_path": video_path,
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
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
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
            dialog_result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
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


import logging
import os
from typing import Any, Callable

import cv2
import numpy as np

from utils.detect_face_center import detect_faces

logger = logging.getLogger(__name__)


def sample_best_thumbnail_frame(
    video_path: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
    num_samples: int = 24,
    on_log: Callable[[str, str], None] | None = None,
) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    """Sample video frames to find the best shot showcasing primary speakers clearly.

    Scores candidate frames based on:
    - Number of prominent faces (bonus for 2 speakers visible)
    - Face bounding box area / closeness
    - Image sharpness (Laplacian variance)
    - Center positioning
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    if not os.path.exists(video_path):
        _log("error", f"Vídeo não encontrado para extração de thumbnail: {video_path}")
        return None, []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        _log("error", f"Não foi possível abrir o vídeo: {video_path}")
        return None, []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_frames / fps

    eff_start = max(0.0, start_time)
    eff_end = end_time if end_time > eff_start + 1.0 else video_duration
    eff_end = min(eff_end, video_duration)
    duration = max(1.0, eff_end - eff_start)

    _log("info", f"Buscando melhor frame para thumbnail entre {eff_start:.1f}s e {eff_end:.1f}s ({num_samples} amostras)...")

    sample_timestamps = [
        eff_start + (duration * (0.05 + 0.9 * i / max(1, num_samples - 1)))
        for i in range(num_samples)
    ]

    best_frame: np.ndarray | None = None
    best_faces: list[dict[str, Any]] = []
    best_score = -1.0

    for ts in sample_timestamps:
        frame_idx = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        h, w, _ = frame.shape
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        if sharpness < 25.0:
            continue

        try:
            faces = detect_faces(frame, min_confidence=0.40)
        except Exception:
            faces = []

        num_faces = len(faces)
        total_face_area = sum(f.get("area", 0) for f in faces)
        area_ratio = total_face_area / max(1, w * h)

        frame_score = 0.0
        if num_faces >= 2:
            frame_score += 120.0
        elif num_faces == 1:
            frame_score += 50.0

        frame_score += min(60.0, area_ratio * 400.0)
        frame_score += min(30.0, sharpness / 15.0)

        if frame_score > best_score:
            best_score = frame_score
            best_frame = frame.copy()
            best_faces = faces

    cap.release()

    if best_frame is None and total_frames > 0:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames / 2))
        ret, fallback_frame = cap.read()
        cap.release()
        if ret and fallback_frame is not None:
            best_frame = fallback_frame

    face_count = len(best_faces)
    face_desc = f"{face_count} interlocutores detectados" if face_count > 1 else f"{face_count} interlocutor detectado"
    _log("info", f"Melhor frame selecionado com sucesso ({face_desc}, score: {best_score:.1f})!")

    return best_frame, best_faces

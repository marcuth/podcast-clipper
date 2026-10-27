import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base_options = python.BaseOptions(model_asset_path="models/blaze_face_short_range.tflite")
options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.35)
detector = vision.FaceDetector.create_from_options(options)

_MIN_FACE_FRACTION = 0.025  # of frame height; anything smaller is noise or a far-away crowd face
_NMS_IOU = 0.35


def _run_detector(rgb: np.ndarray, offset_x: int, offset_y: int, min_confidence: float) -> list[dict]:
    result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    faces = []

    for det in result.detections or []:
        score = det.categories[0].score if det.categories else 0.0
        if score < min_confidence:
            continue

        bbox = det.bounding_box
        x = bbox.origin_x + offset_x
        y = bbox.origin_y + offset_y
        faces.append({
            "cx": int(x + bbox.width / 2),
            "cy": int(y + bbox.height / 2),
            "x": x,
            "y": y,
            "w": bbox.width,
            "h": bbox.height,
            "score": score,
            "area": bbox.width * bbox.height,
        })

    return faces


def _iou(a: dict, b: dict) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["area"] + b["area"] - inter
    return inter / union if union > 0 else 0.0


def _nms(faces: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for face in sorted(faces, key=lambda f: f["score"] * f["area"] ** 0.5, reverse=True):
        # A face cut by a tile border overlaps a larger detection of the same face
        if all(_iou(face, k) < _NMS_IOU and not _contains(k, face) for k in kept):
            kept.append(face)
    return kept


def _contains(outer: dict, inner: dict) -> bool:
    return (
        outer["x"] <= inner["cx"] <= outer["x"] + outer["w"]
        and outer["y"] <= inner["cy"] <= outer["y"] + outer["h"]
    )


def detect_all_faces(frame: np.ndarray, min_confidence: float = 0.45) -> list[dict]:
    """
    Detects every face in a BGR frame (as read by OpenCV), largest first.

    The short-range BlazeFace model sees a 128px downscale of its input, so faces of people
    sitting far from the camera vanish on a full 16:9 frame. Besides the full frame we also run
    it on overlapping square tiles, which roughly doubles the resolution it sees.
    """
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape

    faces = _run_detector(rgb, 0, 0, min_confidence)

    if w > h:
        tile = h
        step = max(1, (w - tile) // 2)
        for tile_x in range(0, w - tile + 1, step):
            faces += _run_detector(rgb[:, tile_x:tile_x + tile], tile_x, 0, min_confidence)

    min_size = h * _MIN_FACE_FRACTION
    faces = [f for f in _nms(faces) if f["h"] >= min_size and f["w"] >= min_size * 0.6]
    faces.sort(key=lambda f: f["area"], reverse=True)
    return faces


def detect_faces(frame: np.ndarray, min_confidence: float = 0.45) -> list[dict]:
    """
    Returns up to 2 prominent faces from a BGR frame.
    Each item is a dict with: 'cx', 'cy', 'x', 'y', 'w', 'h', 'score', 'area'.
    If 2 faces are returned, they are sorted left-to-right by cx.
    """
    candidates = detect_all_faces(frame, min_confidence)

    if len(candidates) <= 1:
        return candidates

    w = frame.shape[1]
    c1, c2 = candidates[0], candidates[1]

    # The second face must be comparable to the first (background people are much smaller)
    if c2["h"] >= 0.6 * c1["h"] and abs(c1["cx"] - c2["cx"]) >= int(w * 0.10):
        return sorted([c1, c2], key=lambda c: c["cx"])

    return [c1]


def detect_face_center(frame: np.ndarray) -> tuple[int, int] | None:
    faces = detect_faces(frame)
    if not faces:
        return None
    return faces[0]["cx"], faces[0]["cy"]

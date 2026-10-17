import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base_options = python.BaseOptions(model_asset_path="models/blaze_face_short_range.tflite")
options = vision.FaceDetectorOptions(base_options=base_options)
detector = vision.FaceDetector.create_from_options(options)

def detect_faces(frame, min_confidence: float = 0.45) -> list[dict]:
    """
    Detects faces in the frame and returns up to 2 prominent faces.
    Each item is a dict with: 'cx', 'cy', 'x', 'y', 'w', 'h', 'score', 'area'.
    If 2 faces are returned, they are sorted left-to-right by cx.
    """
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
    detection_result = detector.detect(mp_image)
    
    if not detection_result.detections:
        return []

    h, w, _ = frame.shape
    candidates = []

    for det in detection_result.detections:
        score = det.categories[0].score if det.categories else 0.0
        if score < min_confidence:
            continue

        bbox = det.bounding_box
        area = bbox.width * bbox.height

        # Filter out tiny noise (smaller than 25x25)
        if bbox.width < 25 or bbox.height < 25:
            continue

        cx = int(bbox.origin_x + bbox.width / 2)
        cy = int(bbox.origin_y + bbox.height / 2)

        candidates.append({
            "cx": cx,
            "cy": cy,
            "x": bbox.origin_x,
            "y": bbox.origin_y,
            "w": bbox.width,
            "h": bbox.height,
            "score": score,
            "area": area,
        })

    if not candidates:
        return []

    if len(candidates) == 1:
        return candidates

    # Sort candidates by area descending
    candidates.sort(key=lambda c: c["area"], reverse=True)

    c1 = candidates[0]
    c2 = candidates[1]

    # The second face must be reasonably large compared to the first (at least 20% of area)
    # and they must have horizontal separation (at least 10% of frame width)
    if c2["area"] >= 0.20 * c1["area"] and abs(c1["cx"] - c2["cx"]) >= int(w * 0.10):
        two_faces = [c1, c2]
        two_faces.sort(key=lambda c: c["cx"])
        return two_faces

    return [c1]


def detect_face_center(frame):
    faces = detect_faces(frame)
    if not faces:
        return None
    return faces[0]["cx"], faces[0]["cy"]

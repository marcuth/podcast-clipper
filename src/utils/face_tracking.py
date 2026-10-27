"""
Plans the vertical framing of a clip from face tracks.

The video is sampled a few times per second and split into shots (camera cuts). Inside each
shot, detections are linked into tracks, one per person. Tracks are filtered so that people
in the background (small or barely visible faces) are never framed, and each remaining
person gets a speaking score from mouth-region motion. The camera follows the active speaker
with hysteresis, and split-screen pairs the two people who talk the most in the shot, which
also works for wide debate shots with many participants (e.g. 30x1 formats).
"""

import bisect
import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from utils.detect_face_center import detect_all_faces

logger = logging.getLogger(__name__)

_SHOT_CUT_CORRELATION = 0.55  # HSV histogram correlation below this between samples = camera cut
_SHOT_CUT_PIXEL_DIFF = 28.0  # mean gray-level change of a 160x90 thumbnail that also means a cut
_TRACK_MAX_GAP_SECONDS = 1.2
_MAIN_MIN_PRESENCE = 0.30  # fraction of the shot a person must be visible to count as participant
_MAIN_MIN_RELATIVE_SIZE = 0.55  # vs the largest participant; smaller faces are background people
_SPEAKER_MIN_RELATIVE_SIZE = 0.35  # ...but someone clearly talking is kept down to this size
_SPEAKING_WINDOW_SECONDS = 1.2
_MIN_SPEAKING_SIGNAL = 1.0  # mouth motion (gray levels) below this is sensor noise, nobody is talking
_MOUTH_FRAME_STRIDE = 2  # measure mouth motion on every 2nd frame between detections (~15 fps)
_MAX_UPPER_MOTION = 20.0
_SWITCH_MARGIN = 1.3  # a new speaker must score this much higher than the current one...
_SWITCH_SUSTAIN_SECONDS = 1.0  # ...for this long...
_MIN_HOLD_SECONDS = 2.0  # ...and the current one must have been on screen at least this long
_DEADZONE_FRACTION = 0.03  # of frame width; ignore smaller target moves to keep the frame still
_SMOOTHING = 0.25
_SNAP_DEADZONES = 5  # moves larger than this many deadzones are cuts, not motion
_FACE_TARGET_FRACTION = 0.16  # zoom in until the face is this tall relative to the crop...
_MIN_CROP_FRACTION = 0.70  # ...but never crop below this fraction of the source height
_MIN_SPLIT_SHOT_SECONDS = 1.5
_SPLIT_PANEL_RATIO = (9 / 16) / 0.5  # width/height of each half of a 9:16 split-screen


@dataclass
class _Track:
    id: int
    samples: dict[int, dict] = field(default_factory=dict)  # sample index -> face
    activity: dict[int, float] = field(default_factory=dict)
    panel: tuple[float, float] = (0.0, 0.0)  # horizontal extent of the camera panel the person is in

    @property
    def last_index(self) -> int:
        return max(self.samples)

    def median(self, key: str) -> float:
        return float(np.median([face[key] for face in self.samples.values()]))


@dataclass
class _Shot:
    start: int  # sample indices, end exclusive
    end: int
    tracks: list[_Track] = field(default_factory=list)


@dataclass
class SingleFrame:
    cx: float
    cy: float
    crop_h: float
    bounds: tuple[float, float]  # the crop must stay inside this horizontal range (camera panel)


@dataclass
class SplitFrame:
    top: tuple[float, float]
    bottom: tuple[float, float]
    box_h: float
    top_bounds: tuple[float, float]
    bottom_bounds: tuple[float, float]


class FramingPlan:
    """Per-sample framing decisions, queried by source-video time."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.times: list[float] = []
        self.shot_ids: list[int] = []
        self.single: list[SingleFrame] = []
        self.split: list[SplitFrame | None] = []
        self.jumps: set[int] = set()  # samples where the frame cuts instead of gliding

    @property
    def split_ratio(self) -> float:
        if not self.split:
            return 0.0
        return sum(1 for item in self.split if item is not None) / len(self.split)

    def _bracket(self, t: float) -> tuple[int, int, float]:
        i = max(0, bisect.bisect_right(self.times, t) - 1)
        j = i + 1
        if j >= len(self.times) or self.shot_ids[j] != self.shot_ids[i] or j in self.jumps:
            return i, i, 0.0
        span = self.times[j] - self.times[i]
        ratio = (t - self.times[i]) / span if span > 0 else 0.0
        return i, j, min(1.0, max(0.0, ratio))

    def single_at(self, t: float) -> SingleFrame:
        if not self.times:
            return SingleFrame(self.width / 2, self.height / 2, self.height, (0.0, float(self.width)))
        i, j, r = self._bracket(t)
        a, b = self.single[i], self.single[j]
        return SingleFrame(_lerp(a.cx, b.cx, r), _lerp(a.cy, b.cy, r), _lerp(a.crop_h, b.crop_h, r), a.bounds)

    def split_at(self, t: float) -> SplitFrame | None:
        if not self.times:
            return None
        i, j, r = self._bracket(t)
        a, b = self.split[i], self.split[j]
        if a is None:
            return None
        if b is None:
            return a
        return SplitFrame(
            (_lerp(a.top[0], b.top[0], r), _lerp(a.top[1], b.top[1], r)),
            (_lerp(a.bottom[0], b.bottom[0], r), _lerp(a.bottom[1], b.bottom[1], r)),
            _lerp(a.box_h, b.box_h, r),
            a.top_bounds,
            a.bottom_bounds,
        )


def _lerp(a: float, b: float, r: float) -> float:
    return a + (b - a) * r


# ── Sampling ─────────────────────────────────────────────────────────────


def _patch(gray: np.ndarray, face: dict, upper: bool) -> np.ndarray | None:
    x0 = int(max(0, face["x"]))
    x1 = int(min(gray.shape[1], face["x"] + face["w"]))
    mid = int(face["y"] + face["h"] * 0.55)
    y0, y1 = (int(max(0, face["y"])), mid) if upper else (mid, int(min(gray.shape[0], face["y"] + face["h"] * 1.05)))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    patch = cv2.resize(gray[y0:y1, x0:x1], (24, 12), interpolation=cv2.INTER_AREA).astype(np.float32)
    return patch - patch.mean()  # ignore global brightness changes


def _find_dividers(gray_small: np.ndarray) -> list[float]:
    """
    Vertical seams of side-by-side camera layouts, as fractions of the frame width.
    A seam is a column where the image changes abruptly along most of the frame height.
    """
    h, w = gray_small.shape
    jumps = np.abs(np.diff(gray_small.astype(np.int16), axis=1)) > 28
    strength = jumps.mean(axis=0)
    dividers: list[float] = []
    for x in np.argsort(strength)[::-1][:3]:
        if strength[x] < 0.55 or not 0.2 * w < x < 0.8 * w:
            continue
        if all(abs((x + 1) / w - d) > 0.05 for d in dividers):
            dividers.append((x + 1) / w)
    return dividers


def _sample(video_path: str, start: float, end: float, sample_fps: int) -> tuple[list[float], list[list[dict]], list[dict], int, int]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [], [], [], 0, 0

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start_f = max(0, int(start * video_fps))
    end_f = min(total_frames, int(end * video_fps)) if total_frames > 0 else int(end * video_fps)
    step = max(1, int(round(video_fps / sample_fps)))

    times: list[float] = []
    faces_per_sample: list[list[dict]] = []
    frame_info: list[dict] = []

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    current_f = start_f

    while current_f < end_f:
        ret, frame = cap.read()
        if not ret:
            break

        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detect_all_faces(frame)

        times.append(current_f / video_fps)
        faces_per_sample.append(faces)
        frame_info.append({
            "hist": hist,
            "thumb": cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32),
            "dividers": _find_dividers(cv2.resize(gray, (480, 270), interpolation=cv2.INTER_AREA)),
        })

        # Speech moves the lips several times a second, too fast for the detection rate, so
        # mouth motion is measured on the frames in between, at the boxes just detected.
        lowers = [_patch(gray, face, upper=False) for face in faces]
        uppers = [_patch(gray, face, upper=True) for face in faces]
        motion: list[list[float]] = [[] for _ in faces]

        for k in range(1, step):
            if not cap.grab():
                break
            if k % _MOUTH_FRAME_STRIDE or not faces:
                continue
            ok, between = cap.retrieve()
            if not ok:
                break
            between_gray = cv2.cvtColor(between, cv2.COLOR_BGR2GRAY)
            for n, face in enumerate(faces):
                lower = _patch(between_gray, face, upper=False)
                upper = _patch(between_gray, face, upper=True)
                lower_motion = _motion(lower, lowers[n])
                upper_motion = _motion(upper, uppers[n])
                # A big change in the upper face is a head turn or a camera cut, not speech
                if lower_motion is not None and upper_motion is not None and upper_motion < _MAX_UPPER_MOTION:
                    # Head movement shakes both halves of the face; talking mostly the lower one
                    motion[n].append(max(0.0, lower_motion - 0.8 * upper_motion))
                lowers[n], uppers[n] = lower, upper

        for face, values in zip(faces, motion):
            face["activity"] = float(np.mean(values)) if values else None

        current_f += step

    cap.release()
    return times, faces_per_sample, frame_info, width, height


# ── Analysis ─────────────────────────────────────────────────────────────


def _is_cut(a: dict, b: dict) -> bool:
    # Color histograms miss cuts between shots of the same set (e.g. white studio walls),
    # so a large change in the image layout also counts.
    if cv2.compareHist(a["hist"], b["hist"], cv2.HISTCMP_CORREL) < _SHOT_CUT_CORRELATION:
        return True
    if float(np.mean(np.abs(a["thumb"] - b["thumb"]))) > _SHOT_CUT_PIXEL_DIFF:
        return True
    return len(a["dividers"]) != len(b["dividers"])


def _split_shots(frame_info: list[dict]) -> list[_Shot]:
    shots: list[_Shot] = []
    shot_start = 0
    for i in range(1, len(frame_info)):
        if _is_cut(frame_info[i - 1], frame_info[i]):
            shots.append(_Shot(shot_start, i))
            shot_start = i
    if frame_info:
        shots.append(_Shot(shot_start, len(frame_info)))
    return shots


def _shot_panels(shot: _Shot, frame_info: list[dict], width: int) -> list[tuple[float, float]]:
    """Horizontal extents of the camera panels inside the shot (one panel = whole frame)."""
    counts: dict[float, int] = {}
    for i in range(shot.start, shot.end):
        for divider in frame_info[i]["dividers"]:
            key = round(divider * 50) / 50
            counts[key] = counts.get(key, 0) + 1
    length = shot.end - shot.start
    seams = sorted(key * width for key, count in counts.items() if count >= 0.6 * length)
    edges = [0.0] + seams + [float(width)]
    return list(zip(edges, edges[1:]))


def _motion(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    if a is None or b is None:
        return None
    return float(np.mean(np.abs(a - b)))


def _build_tracks(shot: _Shot, times: list[float], faces_per_sample: list[list[dict]]) -> None:
    tracks: list[_Track] = []

    for i in range(shot.start, shot.end):
        unmatched = list(range(len(faces_per_sample[i])))
        live = [track for track in tracks if times[i] - times[track.last_index] <= _TRACK_MAX_GAP_SECONDS]

        pairs = []
        for track in live:
            last = track.samples[track.last_index]
            for face_index in unmatched:
                face = faces_per_sample[i][face_index]
                size_ratio = face["h"] / last["h"]
                if not 0.6 <= size_ratio <= 1.65:
                    continue
                distance = np.hypot(face["cx"] - last["cx"], face["cy"] - last["cy"]) / max(face["h"], last["h"])
                if distance < 1.2:
                    pairs.append((distance, track, face_index))

        used_tracks: set[int] = set()
        for _, track, face_index in sorted(pairs, key=lambda p: p[0]):
            if track.id in used_tracks or face_index not in unmatched:
                continue
            used_tracks.add(track.id)
            unmatched.remove(face_index)
            track.samples[i] = faces_per_sample[i][face_index]

        for face_index in unmatched:
            tracks.append(_Track(id=len(tracks), samples={i: faces_per_sample[i][face_index]}))

    for track in tracks:
        track.activity = {
            index: face["activity"] for index, face in track.samples.items() if face.get("activity") is not None
        }

    shot.tracks = tracks


def _merge_fragments(shot: _Shot, panels: list[tuple[float, float]]) -> None:
    """
    Joins tracks of the same person that were broken apart, typically when one panel of a
    side-by-side layout cuts to another angle while the rest of the frame stays the same.
    Fragments are joined when they never overlap in time, sit in the same panel and have
    similar face sizes; in a single-camera frame they must also be close to each other.
    """
    multi_panel = len(panels) > 1
    tracks = sorted(shot.tracks, key=lambda t: len(t.samples), reverse=True)
    merged: list[_Track] = []

    for track in tracks:
        target = None
        for candidate in merged:
            if candidate.panel != track.panel or set(candidate.samples) & set(track.samples):
                continue
            size_ratio = track.median("h") / candidate.median("h")
            if not 0.6 <= size_ratio <= 1.65:
                continue
            distance = abs(track.median("cx") - candidate.median("cx")) / candidate.median("h")
            if multi_panel or distance < 1.5:
                target = candidate
                break
        if target is None:
            merged.append(track)
        else:
            target.samples.update(track.samples)
            target.activity.update(track.activity)

    shot.tracks = sorted(merged, key=lambda t: t.id)


def _panel_of(cx: float, panels: list[tuple[float, float]]) -> tuple[float, float]:
    for panel in panels:
        if panel[0] <= cx < panel[1]:
            return panel
    return panels[-1]


def _participants(shot: _Shot, panels: list[tuple[float, float]]) -> list[_Track]:
    """People taking part in the conversation; background faces are dropped per camera panel."""
    length = shot.end - shot.start
    visible = [track for track in shot.tracks if len(track.samples) / length >= _MAIN_MIN_PRESENCE]
    if not visible:
        # Short or unstable shot: keep the most persistent big face, never a fleeting one
        visible = sorted(shot.tracks, key=lambda t: len(t.samples) * t.median("h"), reverse=True)[:1]

    talk = {track.id: _mean_activity(track) for track in visible}
    loudest = max(talk.values(), default=0.0)

    participants: list[_Track] = []
    for panel in panels:
        in_panel = [track for track in visible if track.panel == panel]
        if not in_panel:
            continue
        largest = max(track.median("h") for track in in_panel)
        # A face clearly smaller than the biggest one is someone in the background, unless
        # they are the one talking (audience members often sit closer to the camera)
        kept = [
            track for track in in_panel
            if track.median("h") >= _MAIN_MIN_RELATIVE_SIZE * largest
            or (
                track.median("h") >= _SPEAKER_MIN_RELATIVE_SIZE * largest
                and loudest > _MIN_SPEAKING_SIGNAL
                and talk[track.id] >= 0.6 * loudest
            )
        ]

        # People cut by the panel edge are usually bystanders or the back of someone's head
        margin = (panel[1] - panel[0]) * 0.03
        centered = [track for track in kept if panel[0] + margin < track.median("cx") < panel[1] - margin]
        participants += centered or kept

    return participants


def _base_weight(track: _Track, largest_h: float) -> float:
    """How likely the person is a main participant: big face, near the middle of its camera panel."""
    panel_x0, panel_x1 = track.panel
    relative_x = (track.median("cx") - panel_x0) / max(1.0, panel_x1 - panel_x0)
    centrality = 1.0 - min(1.0, abs(relative_x - 0.5) * 2)
    return (track.median("h") / largest_h) ** 1.5 * (0.8 + 0.4 * centrality)


def _speaking_factor(speaking: float, loudest: float) -> float:
    # Mouth motion is a noisy cue (profile shots, hands near the face, people chewing), so it
    # only tips the balance between participants instead of overriding who is clearly framed
    if loudest <= _MIN_SPEAKING_SIGNAL:
        return 1.0
    return 0.75 + 0.5 * speaking / loudest


def _mean_activity(track: _Track) -> float:
    return float(np.mean(list(track.activity.values()))) if track.activity else 0.0


def _speaking(track: _Track, i: int, times: list[float]) -> float:
    values = [
        value for index, value in track.activity.items()
        if abs(times[index] - times[i]) <= _SPEAKING_WINDOW_SECONDS
    ]
    return float(np.mean(values)) if values else 0.0


def _position(track: _Track, i: int, shot: _Shot) -> dict | None:
    """Face of the track at sample i, holding the nearest earlier (or later) sighting."""
    if i in track.samples:
        return track.samples[i]
    earlier = [index for index in track.samples if shot.start <= index < i]
    if earlier:
        return track.samples[max(earlier)]
    later = [index for index in track.samples if index > i]
    return track.samples[min(later)] if later else None


def _choose_focus(shot: _Shot, participants: list[_Track], times: list[float]) -> list[_Track | None]:
    if not participants:
        return [None] * (shot.end - shot.start)
    if len(participants) == 1:
        return [participants[0]] * (shot.end - shot.start)

    largest = max(track.median("h") for track in participants)
    base = {track.id: _base_weight(track, largest) for track in participants}
    presence = {track.id: len(track.samples) / (shot.end - shot.start) for track in participants}

    talk = {track.id: _mean_activity(track) for track in participants}
    loudest_overall = max(talk.values())
    focus = max(
        participants,
        key=lambda t: base[t.id] * presence[t.id] * _speaking_factor(talk[t.id], loudest_overall),
    )
    focus_since = times[shot.start]
    challenger: _Track | None = None
    challenger_since = 0.0
    result: list[_Track | None] = []

    for i in range(shot.start, shot.end):
        speaking = {track.id: _speaking(track, i, times) for track in participants}
        loudest = max(speaking.values())
        scores = {
            track.id: base[track.id]
            * _speaking_factor(speaking[track.id], loudest)
            * (1.0 if i in track.samples else 0.4)
            for track in participants
        }
        best = max(participants, key=lambda t: scores[t.id])

        if best.id != focus.id and scores[best.id] > scores[focus.id] * _SWITCH_MARGIN:
            if challenger is None or challenger.id != best.id:
                challenger, challenger_since = best, times[i]
            sustained = times[i] - challenger_since >= _SWITCH_SUSTAIN_SECONDS
            focus_lost = i not in focus.samples and times[i] - times[_last_seen(focus, i)] > _TRACK_MAX_GAP_SECONDS
            if (sustained and times[i] - focus_since >= _MIN_HOLD_SECONDS) or focus_lost:
                focus, focus_since, challenger = best, times[i], None
        else:
            challenger = None

        result.append(focus)

    return result


def _last_seen(track: _Track, i: int) -> int:
    earlier = [index for index in track.samples if index <= i]
    return max(earlier) if earlier else min(track.samples)


def _choose_split_pair(shot: _Shot, participants: list[_Track], times: list[float], width: int) -> tuple[_Track, _Track] | None:
    length = shot.end - shot.start
    if times[shot.end - 1] - times[shot.start] < _MIN_SPLIT_SHOT_SECONDS:
        return None

    candidates = [track for track in participants if len(track.samples) / length >= 0.5]
    if len(candidates) < 2:
        return None

    largest = max(track.median("h") for track in candidates)
    talk = {track.id: _mean_activity(track) for track in candidates}
    loudest = max(talk.values())
    weight = {
        track.id: _base_weight(track, largest) * _speaking_factor(talk[track.id], loudest)
        for track in candidates
    }

    pairs = []
    for a_index, a in enumerate(candidates):
        for b in candidates[a_index + 1:]:
            together = len(set(a.samples) & set(b.samples)) / length
            sizes = sorted([a.median("h"), b.median("h")])
            separated = abs(a.median("cx") - b.median("cx")) >= width * 0.10
            if together >= 0.5 and sizes[0] >= 0.6 * sizes[1] and separated:
                # In a side-by-side layout each panel is usually one side of the conversation
                cross_panel = a.panel != b.panel
                pairs.append((cross_panel, weight[a.id] + weight[b.id], a, b))

    if not pairs:
        return None
    _, _, a, b = max(pairs, key=lambda p: (p[0], p[1]))
    return (a, b) if a.median("cx") <= b.median("cx") else (b, a)


def _smooth(targets: list[tuple[float, float]], deadzone: float) -> list[tuple[float, float]]:
    smoothed: list[tuple[float, float]] = []
    for target in targets:
        if not smoothed:
            smoothed.append(target)
            continue
        last = smoothed[-1]
        if abs(target[0] - last[0]) < deadzone and abs(target[1] - last[1]) < deadzone:
            smoothed.append(last)
        elif abs(target[0] - last[0]) > deadzone * _SNAP_DEADZONES:
            # The person jumped across the frame (a panel cut to another angle): cut, don't pan
            smoothed.append(target)
        else:
            smoothed.append((
                last[0] + (target[0] - last[0]) * _SMOOTHING,
                last[1] + (target[1] - last[1]) * _SMOOTHING,
            ))
    return smoothed


def analyze_framing(video_path: str, start: float, end: float, sample_fps: int = 5) -> FramingPlan:
    """Samples *video_path* between *start* and *end* and plans single and split framing."""
    times, faces_per_sample, frame_info, width, height = _sample(video_path, start, end, sample_fps)
    plan = FramingPlan(width, height)
    if not times:
        return plan

    shots = _split_shots(frame_info)
    deadzone = width * _DEADZONE_FRACTION
    full_frame = (0.0, float(width))
    split_shots = 0

    for shot_id, shot in enumerate(shots):
        _build_tracks(shot, times, faces_per_sample)
        panels = _shot_panels(shot, frame_info, width)
        for track in shot.tracks:
            track.panel = _panel_of(track.median("cx"), panels)
        _merge_fragments(shot, panels)

        participants = _participants(shot, panels)
        focus = _choose_focus(shot, participants, times)
        pair = _choose_split_pair(shot, participants, times, width)
        split_shots += pair is not None

        logger.debug(
            f"[Enquadramento] plano {shot_id} ({times[shot.start]:.1f}s-{times[shot.end - 1]:.1f}s), "
            f"{len(panels)} câmera(s): "
            + ", ".join(
                f"#{t.id} x={t.median('cx'):.0f} h={t.median('h'):.0f} "
                f"presença={len(t.samples) / (shot.end - shot.start):.0%} "
                f"fala={np.mean(list(t.activity.values())) if t.activity else 0:.1f}"
                f"{' *' if t in participants else ''}"
                for t in shot.tracks if len(t.samples) > 2
            )
        )

        # Zoom level is fixed per (shot, person) so the frame never "breathes"
        crop_heights: dict[int, float] = {}
        for track in participants:
            wanted = track.median("h") / _FACE_TARGET_FRACTION
            fits_panel = (track.panel[1] - track.panel[0]) * 16 / 9
            crop_heights[track.id] = float(min(np.clip(wanted, height * _MIN_CROP_FRACTION, height), fits_panel))

        single_targets: list[tuple[float, float]] = []
        crops: list[float] = []
        bounds: list[tuple[float, float]] = []
        segment_starts = [shot.start]
        previous_focus = focus[0] if focus else None

        for offset, i in enumerate(range(shot.start, shot.end)):
            track = focus[offset]
            face = _position(track, i, shot) if track else None
            if track is not None and previous_focus is not None and track.id != previous_focus.id:
                segment_starts.append(i)
            previous_focus = track
            if face is None:
                single_targets.append((width / 2, height / 2))
                crops.append(float(height))
                bounds.append(full_frame)
            else:
                single_targets.append((face["cx"], face["cy"]))
                crops.append(crop_heights.get(track.id, float(height)))
                bounds.append(track.panel)

        # Smooth each focus segment on its own: a change of speaker is a hard cut
        segment_bounds = segment_starts + [shot.end]
        for seg_start, seg_end in zip(segment_bounds, segment_bounds[1:]):
            local = single_targets[seg_start - shot.start:seg_end - shot.start]
            for offset, (cx, cy) in enumerate(_smooth(local, deadzone)):
                k = seg_start + offset - shot.start
                plan.single.append(SingleFrame(cx, cy, crops[k], bounds[k]))
            plan.jumps.add(seg_start)

        if pair is None:
            plan.split.extend([None] * (shot.end - shot.start))
        else:
            left, right = pair
            narrowest = min(left.panel[1] - left.panel[0], right.panel[1] - right.panel[0])
            box_h = float(np.clip(max(left.median("h"), right.median("h")) * 3.2, height * 0.35, height * 0.9))
            box_h = min(box_h, narrowest / _SPLIT_PANEL_RATIO)
            lefts = _smooth([(f["cx"], f["cy"]) for f in (_position(left, i, shot) for i in range(shot.start, shot.end))], deadzone)
            rights = _smooth([(f["cx"], f["cy"]) for f in (_position(right, i, shot) for i in range(shot.start, shot.end))], deadzone)
            plan.split.extend(SplitFrame(l, r, box_h, left.panel, right.panel) for l, r in zip(lefts, rights))

        plan.times.extend(times[shot.start:shot.end])
        plan.shot_ids.extend([shot_id] * (shot.end - shot.start))

    logger.info(
        f"[Enquadramento] {len(shots)} plano(s) de câmera, {split_shots} com dupla para split-screen "
        f"({plan.split_ratio:.0%} do corte)."
    )
    return plan

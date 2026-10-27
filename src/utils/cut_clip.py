from moviepy import VideoFileClip, VideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from typing import Callable, Optional
import json
import random
import cv2
import os
import logging
import numpy as np

from utils.face_tracking import analyze_framing
from utils.generate_subtitles import generate_subtitles
from utils.render_remotion_captions import render_remotion_captions, overlay_captions
from domain.segment import Segment

logger = logging.getLogger(__name__)


def _crop_box(
    cx: float, cy: float, box_w: int, box_h: int, bounds: tuple[float, float], H: int, face_y: float
) -> tuple[int, int]:
    """
    Top-left corner of a box_w x box_h crop that puts the face at *face_y* of its height,
    kept inside *bounds* (the camera panel) so it never shows a side-by-side layout's seam.
    """
    x0, x1 = int(round(bounds[0])), int(round(bounds[1]))
    x = int(max(x0, min(cx - box_w / 2, x1 - box_w)))
    y = int(max(0, min(cy - box_h * face_y, H - box_h)))
    return x, y


def _split_ranges(is_split: Callable[[float], bool], duration: float, step: float = 0.1) -> list[tuple[float, float]]:
    """Time ranges (in output-clip seconds) where the split-screen layout is shown."""
    ranges: list[tuple[float, float]] = []
    range_start: float | None = None
    steps = int(duration / step) + 1

    for index in range(steps):
        time_pos = min(duration, index * step)
        if is_split(time_pos):
            if range_start is None:
                range_start = time_pos
        elif range_start is not None:
            ranges.append((range_start, time_pos))
            range_start = None

    if range_start is not None:
        ranges.append((range_start, duration))
    return ranges


def split_ranges_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + "_split.json"


def save_split_ranges(video_path: str, ranges: list[tuple[float, float]]) -> None:
    """Keeps the split-screen ranges next to the clip, so captions applied later can follow them."""
    path = split_ranges_path(video_path)
    if ranges:
        with open(path, "w", encoding="utf-8") as file:
            json.dump([list(item) for item in ranges], file)
    elif os.path.exists(path):
        os.remove(path)


def load_split_ranges(video_path: str) -> list[tuple[float, float]]:
    path = split_ranges_path(video_path)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as file:
            return [(float(start), float(end)) for start, end in json.load(file)]
    except (OSError, ValueError, TypeError) as exc:
        logger.warning(f"Não foi possível ler {path}: {exc}")
        return []

def cut_clip(
    input_video: str,
    output_video: str,
    start: float,
    end: float,
    segments: Optional[list[Segment]] = None,
    subtitle_segments_override: Optional[list[dict]] = None,
    apply_vignette: bool = True,
    vignette_angle: str = "PI/4",
    render_subtitles: bool = True,
    enable_split_screen: bool = True,
    split_screen_chance: float = 0.5,
    caption_style: str = "remotion",
) -> None:
    """
    Cut and crop a clip from *input_video*.

    Args:
        input_video: Path to the source video file.
        output_video: Destination path for the output clip.
        start: Start time in seconds within the source video.
        end: End time in seconds within the source video.
        segments: Segments used for concatenation (non-contiguous cuts) and,
            when *subtitle_segments_override* is None, for subtitle timing.
        subtitle_segments_override: When provided (e.g. from a Whisper
            re-transcription of the extracted clip), these segments are used
            **instead of** *segments* for subtitle generation.  They must
            already be relative to t=0 of the output clip.
        apply_vignette: Whether to apply a vignette effect (darkened borders).
        vignette_angle: Lens angle for the vignette effect (default 'PI/4').
        render_subtitles: Whether to burn subtitles directly into the video output.
        enable_split_screen: Whether to enable vertical split-screen when 2 people are detected.
        split_screen_chance: Probability (0.0 to 1.0) of applying split-screen on 2-person clips.
        caption_style: "remotion" overlays animated word-by-word
            captions (needs word timestamps in *subtitle_segments_override*) and falls back
            to "ass" if the Remotion render fails.
    """
    plan = analyze_framing(input_video, start, end, sample_fps=5)
    two_face_ratio = plan.split_ratio

    will_split = False

    if enable_split_screen and two_face_ratio >= 0.20:
        will_split = random.random() < split_screen_chance

        if will_split:
            logger.info(
                f"[Split-Screen] Ativado para este corte! (2 pessoas em {two_face_ratio:.0%} dos frames, chance={split_screen_chance:.0%})"
            )
        else:
            logger.info(
                f"[Split-Screen] 2 pessoas presentes ({two_face_ratio:.0%}), mas sorteio de chance não disparou ({split_screen_chance:.0%}). Usando enquadramento único."
            )

    subtitle_segments = segments
    subtitle_offset = start

    if segments:
        source_clip = VideoFileClip(input_video)
        clips_to_concat = []
        time_mapping = []
        adjusted_segments = []

        current_time = 0.0
        sorted_segments = sorted(segments, key=lambda segment: segment.start)

        for segment in sorted_segments:
            safe_end = min(segment.end, source_clip.duration)
            sub = source_clip.subclipped(segment.start, safe_end)
            clips_to_concat.append(sub)

            segment_duration = safe_end - segment.start

            time_mapping.append(
                {
                    "start": current_time,
                    "end": current_time + segment_duration,
                    "orig_start": segment.start,
                }
            )

            adjusted_segments.append(
                Segment(
                    start=current_time,
                    end=current_time + segment_duration,
                    text=segment.text,
                    norm=segment.norm,
                    score=segment.score,
                )
            )

            current_time += segment_duration

        clip = concatenate_videoclips(clips_to_concat)
        subtitle_segments = adjusted_segments
        subtitle_offset = 0.0

        if subtitle_segments_override is not None:
            subtitle_segments = [
                Segment(start=item["start"], end=item["end"], text=item["text"])
                for item in subtitle_segments_override
            ]

            subtitle_offset = 0.0

        def map_to_orig_t(time_sec: float) -> float:
            for mapping_entry in time_mapping:
                if mapping_entry["start"] <= time_sec <= mapping_entry["end"] + 0.1:
                    delta_time = min(
                        time_sec - mapping_entry["start"],
                        mapping_entry["end"] - mapping_entry["start"],
                    )   

                    return mapping_entry["orig_start"] + delta_time

            return start + time_sec

    else:
        clip = VideoFileClip(input_video).subclipped(start, end)

        if subtitle_segments_override is not None:
            subtitle_segments = [
                Segment(start=item["start"], end=item["end"], text=item["text"])
                for item in subtitle_segments_override
            ]

            subtitle_offset = 0.0

        def map_to_orig_t(time_sec: float) -> float:
            return start + time_sec

    W, H = clip.size

    TARGET_RATIO = 9 / 16
    CROP_W = int(H * TARGET_RATIO)
    CROP_H = H

    if CROP_W % 2 != 0:
        CROP_W -= 1

    HALF_H = CROP_H // 2

    # The plan was measured on the source file; rescale in case moviepy reports another size
    scale_x = W / plan.width if plan.width else 1.0
    scale_y = H / plan.height if plan.height else 1.0

    def make_frame(time_pos: float):
        img = clip.get_frame(time_pos)
        orig_t = map_to_orig_t(time_pos)
        split = plan.split_at(orig_t) if will_split else None

        if split is not None:
            target_ratio_half = CROP_W / HALF_H
            top_bounds = (split.top_bounds[0] * scale_x, split.top_bounds[1] * scale_x)
            bottom_bounds = (split.bottom_bounds[0] * scale_x, split.bottom_bounds[1] * scale_x)
            max_w = int(min(top_bounds[1] - top_bounds[0], bottom_bounds[1] - bottom_bounds[0]))
            box_h = int(min(H, split.box_h * scale_y))
            box_w = int(box_h * target_ratio_half)
            if box_w > max_w:
                box_w = max_w
                box_h = int(box_w / target_ratio_half)

            # Top block: left person, bottom block: right person
            x1, y1 = _crop_box(split.top[0] * scale_x, split.top[1] * scale_y, box_w, box_h, top_bounds, H, 0.40)
            x2, y2 = _crop_box(
                split.bottom[0] * scale_x, split.bottom[1] * scale_y, box_w, box_h, bottom_bounds, H, 0.40
            )
            crop1 = img[y1:y1 + box_h, x1:x1 + box_w]
            crop2 = img[y2:y2 + box_h, x2:x2 + box_w]

            divider_h = 4
            half1_h = HALF_H - divider_h // 2
            half2_h = CROP_H - half1_h - divider_h

            top_block = cv2.resize(crop1, (CROP_W, half1_h), interpolation=cv2.INTER_LINEAR)
            bottom_block = cv2.resize(crop2, (CROP_W, half2_h), interpolation=cv2.INTER_LINEAR)
            divider = np.full((divider_h, CROP_W, 3), (20, 24, 35), dtype=np.uint8)

            return np.vstack([top_block, divider, bottom_block])

        # Single person crop, zoomed in when the speaker is far from the camera
        frame = plan.single_at(orig_t)
        bounds = (frame.bounds[0] * scale_x, frame.bounds[1] * scale_x)
        box_h = int(min(H, frame.crop_h * scale_y, (bounds[1] - bounds[0]) / TARGET_RATIO))

        if box_h >= H - 2:
            x1, _ = _crop_box(frame.cx * scale_x, 0, CROP_W, CROP_H, bounds, H, 0.0)
            return img[0:CROP_H, x1:x1 + CROP_W]

        box_w = int(box_h * TARGET_RATIO)
        x1, y1 = _crop_box(frame.cx * scale_x, frame.cy * scale_y, box_w, box_h, bounds, H, 0.35)
        crop = img[y1:y1 + box_h, x1:x1 + box_w]
        return cv2.resize(crop, (CROP_W, CROP_H), interpolation=cv2.INTER_CUBIC)

    final_clip = VideoClip(frame_function=make_frame, duration=clip.duration)

    # Captions move to the vertical center (over the divider) while the split-screen is on,
    # so they never cover either face
    split_ranges = _split_ranges(
        lambda time_pos: will_split and plan.split_at(map_to_orig_t(time_pos)) is not None,
        clip.duration,
    )
    save_split_ranges(output_video, split_ranges)

    # Add background music
    bg_music_dir = os.path.join("assets", "audios", "musics")
    final_audio = clip.audio

    if os.path.exists(bg_music_dir):
        music_files = [file_name for file_name in os.listdir(bg_music_dir) if file_name.endswith(".mp3")]
        
        if music_files:
            try:
                selected_music = random.choice(music_files)
                music_path = os.path.join(bg_music_dir, selected_music)
                
                bg_music = AudioFileClip(music_path)
                
                # Pick a random start point to add variety
                if bg_music.duration > clip.duration:
                    max_start = bg_music.duration - clip.duration
                    start_time = random.uniform(0, max_start)
                    bg_music = bg_music.subclipped(start_time, start_time + clip.duration)

                else:
                    # If music is shorter, just use what we have (or loop, but simple is robust)
                    bg_music = bg_music.subclipped(0, min(bg_music.duration, clip.duration))
                
                # Set volume very low
                bg_music = bg_music.with_volume_scaled(0.1)
                
                if clip.audio:
                    final_audio = CompositeAudioClip([clip.audio, bg_music])

                else:
                    final_audio = bg_music

            except Exception as e:
                print(f"Could not add background music: {e}")

    final_clip: VideoClip = final_clip.with_audio(final_audio)

    ffmpeg_params = ["-crf", "18"]
    video_filters: list[str] = [
        "scale=1080:1920:flags=lanczos",
    ]

    if apply_vignette:
        video_filters.append(f"vignette={vignette_angle}:aspect=9/16")
    
    overlay_path: Optional[str] = None

    if render_subtitles and caption_style == "remotion" and subtitle_segments_override:
        overlay_path = render_remotion_captions(
            subtitle_segments_override,
            clip.duration,
            output_video.replace(".mp4", "_captions.webm"),
            center_ranges=split_ranges,
        )

        if overlay_path is None:
            logger.warning("Legendas Remotion indisponíveis; usando legendas ASS.")

    if subtitle_segments:
        ass_filename = output_video.replace(".mp4", ".ass")
        ass_content = generate_subtitles(subtitle_segments, subtitle_offset, center_ranges=split_ranges)
        
        with open(ass_filename, "w", encoding="utf-8") as f:
            f.write(ass_content)
            
        ass_path = os.path.abspath(ass_filename).replace("\\", "/")

        if ":" in ass_path:
             ass_path = ass_path.replace(":", "\\:")
             
        if render_subtitles and overlay_path is None:
            video_filters.append(f"subtitles='{ass_path}'")

    if video_filters:
        ffmpeg_params.extend(["-vf", ",".join(video_filters)])

    ffmpeg_params.extend([
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.0",
        "-movflags", "+faststart",
    ])

    final_clip.write_videofile(
        output_video,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        fps=24,
        threads=4,
        ffmpeg_params=ffmpeg_params
    )
    
    clip.close()
    final_clip.close()

    if overlay_path is not None:
        captioned_video = output_video.replace(".mp4", "_captioned.mp4")

        if overlay_captions(output_video, overlay_path, captioned_video):
            os.replace(captioned_video, output_video)
        else:
            logger.warning("Overlay de legendas Remotion falhou; clipe mantido sem legendas.")

            if os.path.exists(captioned_video):
                os.remove(captioned_video)

        os.remove(overlay_path)

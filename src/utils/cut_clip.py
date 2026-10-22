from moviepy import VideoFileClip, VideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from typing import Optional
import random
import cv2
import os
import logging
import numpy as np

from utils.detect_face_center import detect_face_center, detect_faces
from utils.generate_subtitles import generate_subtitles
from utils.render_remotion_captions import render_remotion_captions, overlay_captions
from domain.segment import Segment

logger = logging.getLogger(__name__)

def sample_frames(video_path, start, end, fps=3):
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        return []

    fps_video = cap.get(cv2.CAP_PROP_FPS)
    start_frame = int(start * fps_video)
    end_frame = int(end * fps_video)
    
    step = int(fps_video / fps)
    timeline = []
    
    current_frame = start_frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
    
    while current_frame <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
            
        t = current_frame / fps_video
        pos = detect_face_center(frame)
        
        if pos:
            timeline.append((t, pos))
            
        current_frame += step

        if step > 1:
            for _ in range(step - 1):
                cap.read() 
        else:
           pass

    cap.release()
    return timeline

def sample_frames_fast(video_path: str, start: float, end: float, sample_fps: int = 4):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        return []

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    start_f = max(0, int(start * video_fps))
    end_f = min(total_frames, int(end * video_fps))
    
    step = max(1, int(video_fps / sample_fps))
    
    timeline = []
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    
    current_f = start_f
    while current_f < end_f:
        ret, frame = cap.read()
        if not ret:
            break
            
        t = current_f / video_fps
        faces = detect_faces(frame)

        if faces:
            timeline.append((t, faces))
            
        # Skip frames
        if step > 1:
            for _ in range(step - 1):
                if not cap.grab():
                    break
        current_f += step

    cap.release()
    return timeline

def smooth_positions(points: list[tuple[float, tuple[int, int]]], alpha: float = 0.2, max_gap: float = 1.0, spatial_threshold: int = 100):
    if not points:
        return []
        
    smoothed = []
    last_pos = points[0][1]
    last_t = points[0][0]
    
    for t, p in points:
        dist_sq = (p[0] - last_pos[0])**2 + (p[1] - last_pos[1])**2
        
        if (t - last_t) > max_gap or dist_sq > (spatial_threshold ** 2):
            last_pos = p
        else:
            new_x = int(alpha * p[0] + (1 - alpha) * last_pos[0])
            new_y = int(alpha * p[1] + (1 - alpha) * last_pos[1])
            last_pos = (new_x, new_y)
            
        smoothed.append((t, last_pos))
        last_t = t
        
    return smoothed

def get_position_at_time(target_time: float, trajectory: list[tuple[float, tuple[int, int]]]):
    if not trajectory:
        return None

    for index in range(len(trajectory) - 1):
        time_start, pos_start = trajectory[index]
        time_end, pos_end = trajectory[index + 1]

        if time_start <= target_time <= time_end:
            delta_time = time_end - time_start

            if delta_time > 1.0:
                return pos_start

            ratio = (target_time - time_start) / (time_end - time_start) if (time_end - time_start) > 0 else 0

            delta_x = abs(pos_end[0] - pos_start[0])
            if delta_x > 50:
                return pos_start if ratio < 0.5 else pos_end

            pos_x = int(pos_start[0] + (pos_end[0] - pos_start[0]) * ratio)
            pos_y = int(pos_start[1] + (pos_end[1] - pos_start[1]) * ratio)
            return (pos_x, pos_y)

    return trajectory[-1][1] if target_time > trajectory[-1][0] else trajectory[0][1]

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
    caption_style: str = "ass",
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
        caption_style: "ass" burns ASS subtitles; "remotion" overlays animated word-by-word
            captions (needs word timestamps in *subtitle_segments_override*) and falls back
            to "ass" if the Remotion render fails.
    """
    timeline = sample_frames_fast(input_video, start, end, sample_fps=5)

    single_points = []
    left_points = []
    right_points = []
    two_faces_count = 0
    total_face_samples = len(timeline)

    for t, faces in timeline:
        single_points.append((t, (faces[0]["cx"], faces[0]["cy"])))

        if len(faces) >= 2:
            two_faces_count += 1
            left_points.append((t, (faces[0]["cx"], faces[0]["cy"])))
            right_points.append((t, (faces[1]["cx"], faces[1]["cy"])))

    two_face_ratio = (two_faces_count / total_face_samples) if total_face_samples > 0 else 0.0

    smoothed_single = smooth_positions(single_points, alpha=0.1)
    smoothed_left = smooth_positions(left_points, alpha=0.1) if left_points else []
    smoothed_right = smooth_positions(right_points, alpha=0.1) if right_points else []

    will_split = False

    if enable_split_screen and two_face_ratio >= 0.20 and smoothed_left and smoothed_right:
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

    def should_split_at_time(orig_t: float) -> bool:
        if not will_split:
            return False

        window_samples = [
            face_item
            for sample_time, face_item in timeline
            if abs(sample_time - orig_t) <= 0.8
        ]

        if not window_samples:
            return True

        two_count = sum(1 for face_item in window_samples if len(face_item) >= 2)

        return (two_count / len(window_samples)) >= 0.35

    def make_frame(time_pos: float):
        img = clip.get_frame(time_pos)
        orig_t = map_to_orig_t(time_pos)

        if should_split_at_time(orig_t):
            pos_left = get_position_at_time(orig_t, smoothed_left)
            pos_right = get_position_at_time(orig_t, smoothed_right)

            cx1, cy1 = pos_left if pos_left else (int(W * 0.30), int(H * 0.40))
            cx2, cy2 = pos_right if pos_right else (int(W * 0.70), int(H * 0.40))

            target_ratio_half = CROP_W / HALF_H
            dx = max(int(W * 0.25), abs(cx2 - cx1))
            box_h = min(H, max(int(H * 0.65), int(dx * 0.85 / target_ratio_half)))
            box_w = int(box_h * target_ratio_half)
            if box_w > W:
                box_w = W
                box_h = int(box_w / target_ratio_half)

            # Top block: Person 1 (left)
            x1_start = max(0, min(int(cx1 - box_w / 2), W - box_w))
            x1_end = x1_start + box_w
            y1_start = max(0, min(int(cy1 - box_h * 0.35), H - box_h))
            y1_end = y1_start + box_h
            crop1 = img[y1_start:y1_end, x1_start:x1_end]

            # Bottom block: Person 2 (right)
            x2_start = max(0, min(int(cx2 - box_w / 2), W - box_w))
            x2_end = x2_start + box_w
            y2_start = max(0, min(int(cy2 - box_h * 0.35), H - box_h))
            y2_end = y2_start + box_h
            crop2 = img[y2_start:y2_end, x2_start:x2_end]

            divider_h = 4
            half1_h = HALF_H - divider_h // 2
            half2_h = CROP_H - half1_h - divider_h

            top_block = cv2.resize(crop1, (CROP_W, half1_h), interpolation=cv2.INTER_LINEAR)
            bottom_block = cv2.resize(crop2, (CROP_W, half2_h), interpolation=cv2.INTER_LINEAR)
            divider = np.full((divider_h, CROP_W, 3), (20, 24, 35), dtype=np.uint8)

            return np.vstack([top_block, divider, bottom_block])

        # Single person crop
        center = get_position_at_time(orig_t, smoothed_single)
        cx = center[0] if center else int(W / 2)

        x1 = int(cx - CROP_W / 2)
        x1 = max(0, min(x1, W - CROP_W))
        x2 = x1 + CROP_W

        return img[0:CROP_H, x1:x2]

    final_clip = VideoClip(frame_function=make_frame, duration=clip.duration)
    
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
        )

        if overlay_path is None:
            logger.warning("Legendas Remotion indisponíveis; usando legendas ASS.")

    if subtitle_segments:
        ass_filename = output_video.replace(".mp4", ".ass")
        ass_content = generate_subtitles(subtitle_segments, subtitle_offset)
        
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

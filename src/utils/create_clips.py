from domain.segment import Segment

CLIP_GAP = 1.5
MIN_DURATION = 15
MAX_DURATION = 60

MAX_CLIPS = 10


def create_clips(segments: list[Segment], max_clips: int = MAX_CLIPS) -> list[list[Segment]]:
    clips: list[list[Segment]] = []
    current_clip: list[Segment] = []

    valid_segments = [segment for segment in segments if segment.score > -50]
    segments_sorted = sorted(valid_segments, key=lambda segment: segment.start)

    for segment in segments_sorted:
        if not current_clip:
            current_clip.append(segment)
            continue

        if segment.start - current_clip[-1].end <= CLIP_GAP:
            current_clip.append(segment)
        else:
            clips.append(current_clip)
            current_clip = [segment]

    if current_clip:
        clips.append(current_clip)

    final_clips = []

    for clip in clips:
        duration = clip[-1].end - clip[0].start

        if duration < MIN_DURATION:
            continue

        if duration <= MAX_DURATION:
            final_clips.append(clip)
        else:
            sub_clips = find_best_subclips(clip, max_subclips=3)
            final_clips.extend(sub_clips)

    # Sort all clips by total score descending
    final_clips.sort(
        key=lambda candidate_clip: sum(segment.score for segment in candidate_clip),
        reverse=True,
    )

    # Keep only the top max_clips
    final_clips = final_clips[:max_clips]

    # Re-sort primarily by start time for chronological order
    final_clips.sort(key=lambda candidate_clip: candidate_clip[0].start)

    return final_clips


def find_best_subclips(clip: list[Segment], max_subclips: int = 3) -> list[list[Segment]]:
    candidates = []
    total_segments_count = len(clip)

    for start_index in range(total_segments_count):
        for end_index in range(start_index, total_segments_count):
            subclip_duration = clip[end_index].end - clip[start_index].start

            if subclip_duration < MIN_DURATION:
                continue
            if subclip_duration > MAX_DURATION:
                break

            total_score = sum(segment.score for segment in clip[start_index : end_index + 1])
            candidates.append((total_score, start_index, end_index))

    candidates.sort(key=lambda candidate_tuple: candidate_tuple[0], reverse=True)

    selected_intervals: list[tuple[int, int]] = []
    results: list[list[Segment]] = []

    for score, start_idx, end_idx in candidates:
        if len(results) >= max_subclips:
            break

        is_overlapping = False

        for selected_start, selected_end in selected_intervals:
            if not (end_idx < selected_start or start_idx > selected_end):
                is_overlapping = True
                break

        if not is_overlapping:
            selected_intervals.append((start_idx, end_idx))
            results.append(clip[start_idx : end_idx + 1])

    results.sort(key=lambda candidate_clip: candidate_clip[0].start)

    return results

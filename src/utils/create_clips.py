from domain.segment import Segment

CLIP_GAP = 1.5
MIN_DURATION = 15
MAX_DURATION = 60

MAX_CLIPS = 10

def create_clips(segments: list[Segment]) -> list[list[Segment]]:
    clips: list[list[Segment]] = []
    current: list[Segment] = []

    valid_segments = [s for s in segments if s.score > -50]
    segments_sorted = sorted(valid_segments, key=lambda s: s.start)

    for s in segments_sorted:
        if not current:
            current.append(s)
            continue

        if s.start - current[-1].end <= CLIP_GAP:
            current.append(s)
        else:
            clips.append(current)
            current = [s]

    if current:
        clips.append(current)

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
    final_clips.sort(key=lambda c: sum(s.score for s in c), reverse=True)
    
    # Keep only the top MAX_CLIPS
    final_clips = final_clips[:MAX_CLIPS]

    # Re-sort primarily by start time for chronological order
    final_clips.sort(key=lambda c: c[0].start)

    return final_clips

def find_best_subclips(clip: list[Segment], max_subclips: int = 3) -> list[list[Segment]]:
    candidates = []
    n = len(clip)
    
    for i in range(n):
        for j in range(i, n):
            dur = clip[j].end - clip[i].start
            
            if dur < MIN_DURATION:
                continue
            if dur > MAX_DURATION:
                break
                
            score = sum(s.score for s in clip[i:j+1])
            candidates.append((score, i, j))
    
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    selected_intervals: list[tuple[int, int]] = []
    results: list[list[Segment]] = []
    
    for score, start_i, end_i in candidates:
        if len(results) >= max_subclips:
            break

        is_overlapping = False

        for s, e in selected_intervals:
            if not (end_i < s or start_i > e):
                is_overlapping = True
                break
        
        if not is_overlapping:
            selected_intervals.append((start_i, end_i))
            results.append(clip[start_i:end_i+1])
            
    results.sort(key=lambda c: c[0].start)

    return results

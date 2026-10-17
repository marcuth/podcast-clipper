from heuristics.score_contrast import score_contrast
from heuristics.score_length import score_length
from heuristics.score_pause import score_pause
from heuristics.score_question import score_question
from heuristics.score_triggers import score_triggers
from heuristics.score_cta import score_cta
from heuristics.score_personal import score_personal
from heuristics.score_time import score_time
from heuristics.score_heatmap import score_heatmap
from domain import Segment

def apply_heuristics(segment: Segment, segments: list[Segment], heatmap: list[dict] | None = None) -> Segment:
    score_triggers(segment)
    score_contrast(segment)
    score_question(segment)
    score_length(segment)
    score_personal(segment)
    score_pause(segment, segments[segments.index(segment) - 1] if segments.index(segment) > 0 else None)
    score_cta(segment)
    score_time(segment, segments[len(segments) - 1])
    if heatmap:
        score_heatmap(segment, heatmap)
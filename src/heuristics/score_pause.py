from domain import Segment

def score_pause(curr: Segment, prev: Segment | None) -> None:
    if prev and (curr.start - prev.end) > 0.4:
        curr.score += 0.2
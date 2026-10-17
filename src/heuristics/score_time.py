from domain import Segment

def score_time(segment: Segment, last_segment: Segment) -> None:
    if segment.start == last_segment.start:
        segment.score -= 100.0
        
    elif segment.start < 60:
        segment.score -= 100.0

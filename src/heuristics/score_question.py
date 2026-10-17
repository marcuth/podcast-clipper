from domain import Segment

def score_question(segment: Segment) -> None:
    if segment.text.strip().endswith("?"):
        segment.score += 0.4
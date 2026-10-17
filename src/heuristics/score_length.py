from domain import Segment

def score_length(segment: Segment) -> None:
    word_count = len(segment.text.split())

    if 8 <= word_count <= 20:
        segment.score += 0.3
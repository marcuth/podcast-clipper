import re

from domain import Segment

CONTRAST = re.compile(r"(antes.*agora)|(todo mundo.*mas)|(parecia.*mas)")

def score_contrast(segment: Segment) -> None:
    if CONTRAST.search(segment.norm):
        segment.score += 0.7
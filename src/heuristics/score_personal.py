import re

from domain import Segment

PERSONAL_REGEX = re.compile(
    r"\b(eu|meu|minha|a gente|nós|fiquei|pensei|achei|senti|falei)\b",
    re.IGNORECASE
)

def score_personal(segment: Segment) -> None:
    if PERSONAL_REGEX.search(segment.norm):
        segment.score += 0.5

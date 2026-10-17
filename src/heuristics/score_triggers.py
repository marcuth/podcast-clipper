import re

from domain import Segment

TRIGGERS_REGEX = re.compile(
    r"(presta atenção|olha só|o ponto é|o problema é|"
    r"ninguém fala sobre|o maior erro|o segredo é|"
    r"o que ninguém te conta|isso muda tudo|isso é importante|"
    r"você sabia|a verdade é|muita gente|inacreditável|"
    r"surpreendente|dica de ouro|conselho|essa história)",
    re.IGNORECASE
)

def score_triggers(segment: Segment) -> None:
    if TRIGGERS_REGEX.search(segment.norm):
        segment.score += 1.0
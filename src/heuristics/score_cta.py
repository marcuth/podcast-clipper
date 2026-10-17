import re

from domain import Segment

CTA_REGEX = re.compile(
    r"(inscrev(a|e)-?se|inscreve|aqui nos comentários|deixa o like|dar o like|curte o vídeo|"
    r"ativa o sininho|segue a gente|compartilha esse vídeo|"
    r"comenta (aqui embaixo|aí)|link na (descrição|bio)|"
    r"assista(m)? os outros|vídeo aqui na tela|"
    r"tchau|até o próximo|valeu pessoal|"
    r"não esquece de|se você gostou|"
    r"espero que vocês tenham gostado|"
    r"tela final|hype)",
    re.IGNORECASE
)

def score_cta(segment: Segment) -> None:
    if CTA_REGEX.search(segment.norm):
        segment.score -= 100.0

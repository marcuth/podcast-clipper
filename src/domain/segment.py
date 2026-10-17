from typing import Optional

class Segment:
    def __init__(self, start: float, end: float, text: str, norm: Optional[str] = None, score: Optional[float] = None) -> None:
        self.start = start
        self.end = end
        self.text = text
        if norm is not None:
            self.norm = norm
        else:
            from utils.normalize_text import normalize_text
            self.norm = normalize_text(text)
        self.score = score or 0.0

    def __repr__(self) -> str:
        return f"Segment({self.start}, {self.end}, {self.text})"

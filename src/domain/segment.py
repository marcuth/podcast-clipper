from typing import Optional

class Segment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        norm: Optional[str] = None,
        score: Optional[float] = None,
        ai_metadata: Optional[dict] = None,
        **extra,
    ) -> None:
        self.start = float(start)
        self.end = float(end)
        self.text = text
        if norm is not None:
            self.norm = norm
        else:
            from utils.normalize_text import normalize_text
            self.norm = normalize_text(text)
        self.score = float(score) if score is not None else 0.0
        self.ai_metadata = ai_metadata
        for key, value in extra.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"Segment({self.start}, {self.end}, {self.text})"

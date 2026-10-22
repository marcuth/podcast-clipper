# AGENTS.md — auto-podcast-clipper

## Project Overview

YouTube podcast clipper: downloads videos, transcribes (Whisper or YouTube captions), scores segments via heuristics, assembles clips with face-tracking crop and subtitles, generates metadata via Groq LLM.

Python 3.11, managed by Poetry. Entry point: `src/main.py`.

## Build / Run / Test Commands

- **Run the pipeline**: `poetry run start`
- **Run a Python script directly**: `poetry run python src/main.py`
- **Install dependencies**: `poetry install`
- **Add a dependency**: `poetry add <package>`
- **Add a dev dependency**: `poetry add --group dev <package>`
- **Lint** (no config committed; if ruff is installed): `poetry run ruff check .`
- **Format** (no config committed; if ruff is installed): `poetry run ruff format .`
- **Type check** (no config committed; if pyright is installed): `poetry run pyright`
- **Testing**: no test framework exists yet. No `tests/` directory. If pytest is added later: `poetry run pytest` or `poetry run pytest tests/test_foo.py::test_bar -v`.

## Project Structure

```
src/
├── main.py                         # entry point — interactive CLI pipeline
├── scheduler.py                    # YouTube upload scheduler
├── domain/
│   ├── __init__.py
│   └── segment.py                  # Segment dataclass
├── heuristics/
│   ├── __init__.py                 # re-exports apply_heuristics
│   ├── appy_heuristics.py          # orchestrator (note: missing 'l')
│   ├── score_contrast.py
│   ├── score_cta.py
│   ├── score_heatmap.py
│   ├── score_length.py
│   ├── score_pause.py
│   ├── score_personal.py
│   ├── score_question.py
│   ├── score_time.py
│   └── score_triggers.py
├── services/
│   ├── __init__.py                 # re-exports generate_video_details, YouTubeService
│   ├── groq_service.py             # LLM metadata generation
│   └── youtube_service.py          # YouTube API upload
└── utils/
    ├── __init__.py                 # facade — re-exports all utility functions
    ├── create_clips.py
    ├── cut_clip.py                 # face-tracking crop + subtitle burn-in
    ├── detect_face_center.py
    ├── download_clip_segments.py
    ├── generate_subtitles.py
    ├── get_youtube_heatmap.py
    ├── get_youtube_transcription.py
    ├── normalize_text.py
    ├── slugify.py
    ├── transcribe_audio.py
    ├── transcribe_clip.py
    └── video_to_mp3.py
```

## Code Style Guidelines

### Imports

Group in order: standard library → third-party → local. Separate groups with a blank line.

```python
import logging
import os
import re

import cv2
import yt_dlp
from moviepy import VideoFileClip

from domain import Segment
from utils import normalize_text
```

Use relative imports inside `__init__.py` files; use absolute package-relative imports elsewhere:

```python
# In __init__.py:
from .video_to_mp3 import video_to_mp3

# In consumer modules:
from utils import video_to_mp3, transcribe_audio
from domain import Segment
from heuristics import apply_heuristics
from services import generate_video_details
```

When importing from a sub-package within the same package, use the full dotted path:
```python
from domain.segment import Segment
from utils.detect_face_center import detect_face_center
```

### Formatting

- No formatter config is committed. Follow the existing style:
  - Indent with 4 spaces
  - Max line length is informal (~100 chars)
  - Single blank line between top-level definitions
  - Use `# ─────────────────────` or `# ── Section title ──` for section separators
- If adding a formatter, prefer `ruff format`.

### Type Annotations

Annotate all function signatures (parameters and return types). Use Python 3.10+ style unions (`X | None` instead of `Optional[X]`).

```python
def transcribe_audio(audio_path: str) -> list[dict]: ...
def cut_clip(input_video: str, start: float, end: float, segments: list[Segment] | None = None) -> None: ...
```

Use `Optional` only when it appears in existing files alongside X | None style (the codebase uses both; prefer `X | None` for new code).

Use `TypedDict` for structured dicts:
```python
from typing import TypedDict

VideoDetails = TypedDict("VideoDetails", {"title": str, "description": str, "tags": list[str]})
```

### Naming Conventions

| Element       | Style              | Example                            |
|---------------|--------------------|------------------------------------|
| Functions     | `snake_case`       | `transcribe_audio()`, `cut_clip()` |
| Classes       | `PascalCase`       | `Segment`, `YouTubeService`        |
| Variables     | `snake_case`       | `video_path`, `segments_data`      |
| Constants     | `UPPER_SNAKE_CASE` | `CONTRAST`, `CLIP_GAP`, `MAX_CLIPS`|
| Private       | `_leading_underscore` | `_seconds_to_hms()`, `_MODE_WHISPER` |
| Logger        | `logger`           | `logger = logging.getLogger(__name__)` |

### Error Handling

- No custom exception classes. Use built-in types: `ValueError`, `RuntimeError`, `raise`.
- Prefer specific exception handling over bare `except:`.
- Use try/except with logging for non-fatal failures (e.g., heatmap fetch fallback, background music).
- Use defensive `os.path.exists()` checks before file operations.
- For retry logic on user input, use recursive calls (see `get_youtube_video_url()`).

```python
try:
    heatmap = _fetch_via_ytdlp(video_url)
except Exception as exc:
    logger.warning(f"yt-dlp heatmap extraction failed: {exc}")
    heatmap = []
```

### Logging

Always create a module-level logger:
```python
logger = logging.getLogger(__name__)
```

Use `logging.basicConfig(...)` only once at the entry point (`main.py`). Use `logger.info()`, `logger.warning()`, `logger.error()` throughout.

### Documentation

- Module-level docstrings for non-trivial modules (see `get_youtube_heatmap.py`).
- Function docstrings with Args/Returns sections for complex public functions (see `cut_clip()`).
- Keep docstrings concise; avoid redundant docs for obvious parameters.
- Comments are sparse; use them to explain *why*, not *what*.

### Heuristic Pattern

Each heuristic function takes a `Segment`, mutates `.score` in-place, and returns `None`:
```python
def score_question(segment: Segment) -> None:
    if segment.text.strip().endswith("?"):
        segment.score += 0.4
```

The orchestrator (`apply_heuristics`) calls them in sequence. To add a new heuristic: create `score_<name>.py`, import and call it in `appy_heuristics.py`.

### Domain Model

```python
class Segment:
    start: float
    end: float
    text: str
    norm: str        # lowercase-normalized text
    score: float     # computed by heuristics
```

## Git Conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Messages should be descriptive sentences.
- Use merge commits for feature branches.

## Tips for Agentic Coding

- Before editing, understand the heuristic scoring pipeline — most business logic lives there.
- The heuristics directory has a typo (`appy_heuristics.py`). Don't rename it unless asked.
- `utils/__init__.py` is a facade; add new utility re-exports there.
- The pipeline uses side-effect-based scoring (mutates `segment.score`), not functional returns.
- Face detection uses MediaPipe (`blaze_face_short_range.tflite` model in `models/`).
- Background music is loaded from `assets/audios/musics/` (random selection).
- Video output goes to `output/<slug>/clips/`.
- Optional Remotion captions (`caption_style="remotion"`): the `remotion/` project renders a transparent WebM overlay from Whisper word timestamps (`transcribe_clip` → `words`), composited by `utils/render_remotion_captions.py`. Needs Node; `npm install` runs automatically on first use. Any failure falls back to the ASS subtitles. Preview with `cd remotion && npm run studio`.

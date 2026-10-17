from domain.segment import Segment

# ──────────────────────────────────────────────────────────────────────────────
# Pop-in animation constants (milliseconds, relative to each dialogue line start)
# ──────────────────────────────────────────────────────────────────────────────

_POP_GROW_MS  = 100   # time to reach peak scale (overshoot)
_POP_PEAK_SCL = 120   # peak scale % (creates the elastic bounce feel)
_POP_SETTLE_MS = 180  # time to settle back to 100 %


def generate_subtitles(segments: list[Segment], offset: float = 0.0) -> str:
    header = generate_header()
    events = generate_events(segments, offset)
    return f"{header}\n{events}"


def generate_header() -> str:
    return """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CapCut,Poppins,115,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,0,2,10,10,650,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def _pop_tag() -> str:
    """
    Returns an ASS inline tag string that animates the text scale from 0 → peak → 100 %,
    producing a spring/bounce pop-in on each new subtitle chunk.

    Tag breakdown:
      \\fscx0\\fscy0               – start invisible (scale 0)
      \\t(0,T1,\\fscxP\\fscyP)     – grow to peak scale P% over T1 ms
      \\t(T1,T2,\\fscx100\\fscy100) – settle back to 100% between T1 and T2 ms
    """
    p  = _POP_PEAK_SCL
    t1 = _POP_GROW_MS
    t2 = _POP_SETTLE_MS
    return (
        f"{{\\fscx0\\fscy0"
        f"\\t(0,{t1},\\fscx{p}\\fscy{p})"
        f"\\t({t1},{t2},\\fscx100\\fscy100)}}"
    )


def generate_events(segments: list[Segment], offset: float) -> str:
    events = ""
    pop = _pop_tag()

    for seg in segments:
        if not seg.text:
            continue

        seg_start_rel = seg.start - offset
        seg_duration  = seg.end - seg.start

        chunks     = chunk_text(seg.text)
        word_count = count_words(seg.text)

        if word_count == 0:
            continue

        time_per_word = seg_duration / word_count
        current_time  = seg_start_rel

        for chunk in chunks:
            chunk_text_str = " ".join(chunk)
            chunk_len      = len(chunk)
            chunk_duration = chunk_len * time_per_word

            start_str    = format_ass_time(current_time)
            end_str      = format_ass_time(current_time + chunk_duration)
            text_content = chunk_text_str.upper()

            events += f"\nDialogue: 0,{start_str},{end_str},CapCut,,0,0,0,,{pop}{text_content}"

            current_time += chunk_duration

    return events


def chunk_text(text: str) -> list[list[str]]:
    clean_text = text.replace("\n", " ").replace("\r", " ").strip()
    words = clean_text.split()

    chunks = []
    current_chunk = []

    for word in words:
        current_chunk.append(word)
        current_length = len(" ".join(current_chunk))

        if len(current_chunk) >= 2 or current_length > 12:
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def count_words(text: str) -> int:
    clean_text = text.replace("\n", " ").replace("\r", " ").strip()
    return len(clean_text.split())


def format_ass_time(seconds: float) -> str:
    seconds = max(0, seconds)

    hrs  = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms   = int((seconds - int(seconds)) * 100)

    return f"{hrs}:{mins:02d}:{secs:02d}.{ms:02d}"

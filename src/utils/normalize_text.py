def normalize_text(text: str) -> str:
    return (
        text.lower()
        .replace("’", "'")
        .replace("…", "...")
        .strip()
    )
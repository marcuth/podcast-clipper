"""
Title rules shared by the Gemini prompts, plus validation and a transcript-based fallback.

Gemini occasionally returns a title that is unusable (the episode title cut mid-word,
"Corte 1 - ...", empty). Those are rejected here so the caller can retry or fall back
to a title built from what is actually said in the clip.
"""

import difflib
import re
import unicodedata

from domain import Segment

MAX_SHORT_TITLE_LENGTH = 60
MAX_LONG_TITLE_LENGTH = 75

_LENGTH_TOLERANCE = 15
_MIN_TITLE_LENGTH = 12
_MIN_TITLE_WORDS = 3
_SIMILARITY_THRESHOLD = 0.8

_QUOTES = " \"'“”‘’«»"
_TRAILING_PUNCTUATION = " .;:,-–—"
_DANGLING_WORDS = frozenset(
    "e de da do das dos com que para por em a o as os um uma no na nos nas ou mas se ao à".split()
)

_NUMBERING_PREFIX = re.compile(
    r"^\s*(?:(?:corte|clipe?|short|trecho|parte)\s*#?\d+\s*[-–—:.]\s*|#\d+\s*[-–—:.]?\s*)",
    re.IGNORECASE,
)
_GENERIC_TITLE_PATTERNS = (
    "o segredo",
    "voce nao vai acreditar",
    "a verdade sobre",
    "isso muda tudo",
    "isso mudou tudo",
    "veja isso",
    "veja o que aconteceu",
    "dica incrivel",
    "dica imperdivel",
    "nao faca isso",
    "voce precisa ver",
)
_GENERIC_PREFIX = re.compile(r"^\s*(?:corte|clipe?|short|trecho|parte)\b", re.IGNORECASE)
_LEADING_FILLERS = re.compile(
    r"^(?:>>\s*)?(?:(?:então|né|assim|tipo|bom|olha|veja|cara|mano|ah|eh|é|e|aí|pois|bem)\b[\s,]*)+",
    re.IGNORECASE,
)

TITLE_RULES_PROMPT = """REGRAS ABSOLUTAS PARA O TÍTULO (violar qualquer uma invalida a resposta):
1. NUNCA comece com "Corte", "Clipe", "Trecho", "Parte" ou "Short", e NUNCA use numeração ("Corte 1 - ...", "#3", "Parte 2:").
2. NUNCA copie, resuma ou abrevie o título do episódio e NUNCA inclua o nome do canal ou do programa no título. Essas informações pertencem à descrição e às tags.
3. O título deve ser uma frase COMPLETA e autossuficiente, que faça sentido sem nenhum contexto. NUNCA termine no meio de uma palavra ou de uma frase.
   Exemplo INVÁLIDO: "Ao vivo com Renan Santos e Dr. Feli" (é o título do episódio, cortado no meio de uma palavra).
4. Extraia a ideia central, a afirmação ou o conflito que é DITO no trecho e cite o assunto concreto: pessoa, número, situação ou analogia.
5. Escreva em português do Brasil, em caixa de frase normal (nunca tudo em maiúsculas), sem emojis, sem aspas ao redor e sem ponto final.
6. Respeite o limite de caracteres reescrevendo a frase para caber. NUNCA corte a frase no limite."""


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).split())


def truncate_at_word(text: str, limit: int) -> str:
    """Cut *text* to at most *limit* characters without splitting a word."""
    if len(text) <= limit:
        return text

    cut = text[:limit]

    if text[limit] != " " and " " in cut:
        cut = cut.rsplit(" ", 1)[0]

    return cut.rstrip(_TRAILING_PUNCTUATION)


def clean_title(title: str, max_length: int = MAX_SHORT_TITLE_LENGTH) -> str:
    """Strip quotes, numbering prefixes and trailing punctuation; trim to *max_length* at a word boundary."""
    text = " ".join(str(title or "").split()).strip(_QUOTES)
    text = _NUMBERING_PREFIX.sub("", text).strip(_QUOTES).rstrip(_TRAILING_PUNCTUATION)

    return truncate_at_word(text, max_length)


def title_problem(
    title: str,
    episode_title: str = "",
    max_length: int = MAX_SHORT_TITLE_LENGTH,
) -> str | None:
    """Return why *title* is unacceptable, or ``None`` when it is fine."""
    text = " ".join(str(title or "").split())

    if len(text) < _MIN_TITLE_LENGTH or len(text.split()) < _MIN_TITLE_WORDS:
        return "é curto demais para ser um título"

    if _GENERIC_PREFIX.match(text):
        return 'começa com "Corte"/"Clipe"/"Trecho"/"Parte" ou numeração'

    if len(text) > max_length + _LENGTH_TOLERANCE:
        return f"passa muito do limite de {max_length} caracteres"

    if text.split()[-1].lower().strip(".,;:!?") in _DANGLING_WORDS:
        return "termina no meio da frase"

    normalized_title = _normalize(text)
    normalized_episode = _normalize(episode_title)

    if any(normalized_title.startswith(pattern) for pattern in _GENERIC_TITLE_PATTERNS):
        return "é genérico, sem o assunto concreto da fala"

    if normalized_episode:
        prefix_similarity = difflib.SequenceMatcher(
            None, normalized_title, normalized_episode[: len(normalized_title)]
        ).ratio()

        if (
            normalized_title in normalized_episode
            or normalized_episode in normalized_title
            or prefix_similarity > _SIMILARITY_THRESHOLD
        ):
            return "copia ou abrevia o título do episódio"

    return None


def is_fallback_details(details: dict) -> bool:
    """True for details produced by a fallback (including the legacy 'Corte N - ...' placeholder)."""
    if details.get("fallback") is True:
        return True

    return str(details.get("title", "")).startswith("Corte ") and "Trecho imperdível de" in str(
        details.get("description", "")
    )


def _candidate_sentences(text: str) -> list[tuple[str, bool]]:
    """Spoken sentences without fillers, each flagged when it was a question."""
    sentences: list[tuple[str, bool]] = []

    for raw_sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = _LEADING_FILLERS.sub("", raw_sentence.replace(">>", " ")).strip(_QUOTES + " ")
        is_question = sentence.endswith("?")
        sentence = sentence.rstrip(_TRAILING_PUNCTUATION + "!?")

        if sentence:
            sentences.append((sentence[0].upper() + sentence[1:], is_question))

    return sentences


def build_fallback_details(
    segments: list[Segment],
    episode_title: str,
    channel_name: str = "",
) -> dict:
    """
    Build title/description/tags from the clip's own transcript when Gemini is unavailable.

    The title is a sentence that is actually spoken in the clip, never the (truncated) episode
    title. The result is flagged with ``fallback=True`` so it can be regenerated later.
    """
    transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    valid_titles: list[tuple[str, bool]] = []

    for sentence, is_question in _candidate_sentences(transcript):
        words = sentence.split()

        if len(words) < _MIN_TITLE_WORDS:
            continue

        candidate = clean_title(" ".join(words[:12]))

        if title_problem(candidate, episode_title) is None:
            valid_titles.append((candidate, is_question))

    # A spoken question makes a better title than the first statement.
    title = next((text for text, is_question in valid_titles if is_question), "")
    title = title or (valid_titles[0][0] if valid_titles else "")

    if not title:
        title = clean_title(" ".join(transcript.split()[:8])) or clean_title(episode_title) or "Trecho do episódio"

    source = f'Trecho de {channel_name} no episódio "{episode_title}".' if channel_name else f'Trecho do episódio "{episode_title}".'
    excerpt = truncate_at_word(" ".join(transcript.split()), 220)
    description = source + (f'\n\n"{excerpt}"' if excerpt else "") + "\n\nO que você pensa sobre esse assunto? Comente sua opinião!"

    tags = ["shorts", "podcast", "cortes"]
    channel_tag = re.sub(r"[^a-z0-9]", "", _normalize(channel_name))

    if channel_tag:
        tags.append(channel_tag)

    return {"title": title, "description": description, "tags": tags, "fallback": True}

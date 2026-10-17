"""Transcription helper using AssemblyAI Cloud API with word-level accuracy."""

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_assemblyai_api_key() -> str:
    """Retrieve AssemblyAI API key from environment."""
    key = os.environ.get("ASSEMBLY_AI_API_KEY", "").strip().strip('"').strip("'")
    return key


def transcribe_audio_assemblyai(
    audio_path: str,
    language: str | None = None,
    api_key: str | None = None,
    max_sentence_duration: float = 8.5,
    max_sentence_words: int = 22,
) -> list[dict[str, Any]]:
    """Transcribe an audio or video file using AssemblyAI Universal models.

    Args:
        audio_path: Path to the audio or video file.
        language: Language code (e.g. 'pt', 'en'). If None, automatic language detection is used.
        api_key: Optional explicit API key. Defaults to ASSEMBLY_AI_API_KEY env var.
        max_sentence_duration: Max duration in seconds before splitting a long sentence.
        max_sentence_words: Max words before splitting a long sentence.

    Returns:
        List of dicts with 'start' (float seconds), 'end' (float seconds), 'text' (str).
    """
    import assemblyai as aai

    active_key = (api_key or get_assemblyai_api_key()).strip()
    if not active_key:
        raise ValueError(
            "Chave de API da AssemblyAI não configurada. "
            "Defina ASSEMBLY_AI_API_KEY no arquivo .env ou na aba Diagnóstico."
        )

    timeout_seconds = int(os.environ.get("ASSEMBLY_AI_HTTP_TIMEOUT_SECONDS", "900"))
    aai.settings.api_key = active_key
    aai.settings.http_timeout = timeout_seconds

    # Build transcription configuration
    config_params: dict[str, Any] = {
        "speaker_labels": True,
        "punctuate": True,
        "format_text": True,
        "speech_models": ["universal-3-pro", "universal-2"],
    }

    if language and language.strip() and language.strip().lower() != "auto":
        config_params["language_code"] = language.strip().lower()
    else:
        config_params["language_detection"] = True

    config = aai.TranscriptionConfig(**config_params)
    transcriber = aai.Transcriber()

    file_size_mb = 0.0
    if os.path.exists(audio_path):
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    logger.info(
        f"Iniciando transcrição com AssemblyAI Cloud: {audio_path} ({file_size_mb:.2f} MB)..."
    )

    start_time = time.time()
    transcript = transcriber.transcribe(
        audio_path,
        config=config,
        poll_timeout=float(timeout_seconds),
    )

    elapsed = time.time() - start_time
    logger.info(f"AssemblyAI respondeu em {elapsed:.1f}s com status: {transcript.status}")

    if transcript.status == aai.TranscriptStatus.error:
        error_msg = f"AssemblyAI transcription error: {transcript.error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    segments_data: list[dict[str, Any]] = []

    # 1. First priority: Sentence-level segmentation
    try:
        sentences = transcript.get_sentences()
    except Exception as exc:
        logger.warning(f"Não foi possível obter sentenças diretas da AssemblyAI: {exc}")
        sentences = []

    if sentences:
        logger.info(f"AssemblyAI retornou {len(sentences)} sentenças estruturadas.")
        for sentence in sentences:
            s_start = sentence.start / 1000.0
            s_end = sentence.end / 1000.0
            s_text = sentence.text.strip()
            if not s_text:
                continue

            sentence_duration = s_end - s_start
            sentence_words = getattr(sentence, "words", []) or []

            # Split sentences that are too long into smaller chunks for better clipping & subtitle pacing
            if (sentence_duration > max_sentence_duration or len(sentence_words) > max_sentence_words) and len(sentence_words) > 6:
                sub_chunks = _split_sentence_words(sentence_words, max_sentence_duration, max_sentence_words)
                for chunk in sub_chunks:
                    segments_data.append(chunk)
            else:
                segments_data.append({
                    "start": round(s_start, 3),
                    "end": round(s_end, 3),
                    "text": s_text,
                })

    # 2. Fallback: Utterances
    elif getattr(transcript, "utterances", None):
        logger.info(f"Usando {len(transcript.utterances)} falas (utterances) da AssemblyAI.")
        for utt in transcript.utterances:
            u_start = utt.start / 1000.0
            u_end = utt.end / 1000.0
            u_text = utt.text.strip()
            if not u_text:
                continue

            utt_words = getattr(utt, "words", []) or []
            if (u_end - u_start > max_sentence_duration or len(utt_words) > max_sentence_words) and len(utt_words) > 6:
                sub_chunks = _split_sentence_words(utt_words, max_sentence_duration, max_sentence_words)
                for chunk in sub_chunks:
                    segments_data.append(chunk)
            else:
                segments_data.append({
                    "start": round(u_start, 3),
                    "end": round(u_end, 3),
                    "text": u_text,
                })

    # 3. Fallback: Raw words grouping
    elif getattr(transcript, "words", None):
        logger.info(f"Agrupando {len(transcript.words)} palavras individuais da AssemblyAI.")
        segments_data = _group_raw_words(transcript.words, max_words=14, max_duration=6.5)

    else:
        # Ultimate fallback: single segment with entire text
        full_text = getattr(transcript, "text", "").strip()
        if full_text:
            segments_data.append({
                "start": 0.0,
                "end": round(float(getattr(transcript, "audio_duration", 10.0)), 3),
                "text": full_text,
            })

    # Clean and sanitize sequential ordering
    segments_data.sort(key=lambda item: item["start"])
    sanitized_segments: list[dict[str, Any]] = []

    for idx, current in enumerate(segments_data):
        if idx < len(segments_data) - 1:
            next_start = segments_data[idx + 1]["start"]
            if current["end"] > next_start:
                current["end"] = next_start

        if current["end"] > current["start"] and current["text"].strip():
            sanitized_segments.append({
                "start": round(float(current["start"]), 3),
                "end": round(float(current["end"]), 3),
                "text": current["text"].strip(),
            })

    logger.info(f"AssemblyAI finalizou processamento: {len(sanitized_segments)} segmentos gerados.")
    return sanitized_segments


def _split_sentence_words(
    words: list[Any],
    max_duration: float,
    max_words: int,
) -> list[dict[str, Any]]:
    """Splits a long word list into smaller natural segments."""
    chunks: list[dict[str, Any]] = []
    current_words: list[Any] = []

    for word in words:
        current_words.append(word)
        c_start = current_words[0].start / 1000.0
        c_end = current_words[-1].end / 1000.0
        duration = c_end - c_start
        word_text = getattr(word, "text", "")

        ends_clause = word_text.endswith((",", ";", ":", "-", "—", ".", "!", "?"))
        should_split = (
            len(current_words) >= max_words
            or duration >= max_duration
            or (ends_clause and len(current_words) >= 8)
        )

        if should_split and len(current_words) >= 4:
            text = " ".join(getattr(w, "text", "") for w in current_words).strip()
            if text:
                chunks.append({
                    "start": round(c_start, 3),
                    "end": round(c_end, 3),
                    "text": text,
                })
            current_words = []

    if current_words:
        c_start = current_words[0].start / 1000.0
        c_end = current_words[-1].end / 1000.0
        text = " ".join(getattr(w, "text", "") for w in current_words).strip()
        if text:
            chunks.append({
                "start": round(c_start, 3),
                "end": round(c_end, 3),
                "text": text,
            })

    return chunks


def _group_raw_words(
    words: list[Any],
    max_words: int = 14,
    max_duration: float = 6.5,
) -> list[dict[str, Any]]:
    """Group flat word objects into segments."""
    segments: list[dict[str, Any]] = []
    current_words: list[Any] = []

    for word in words:
        current_words.append(word)
        c_start = current_words[0].start / 1000.0
        c_end = current_words[-1].end / 1000.0
        duration = c_end - c_start
        word_text = getattr(word, "text", "")

        ends_sentence = word_text.endswith((".", "!", "?"))
        ends_clause = word_text.endswith((",", ";", ":"))

        if (
            ends_sentence
            or (ends_clause and len(current_words) >= 6)
            or len(current_words) >= max_words
            or duration >= max_duration
        ):
            text = " ".join(getattr(w, "text", "") for w in current_words).strip()
            if text:
                segments.append({
                    "start": round(c_start, 3),
                    "end": round(c_end, 3),
                    "text": text,
                })
            current_words = []

    if current_words:
        c_start = current_words[0].start / 1000.0
        c_end = current_words[-1].end / 1000.0
        text = " ".join(getattr(w, "text", "") for w in current_words).strip()
        if text:
            segments.append({
                "start": round(c_start, 3),
                "end": round(c_end, 3),
                "text": text,
            })

    return segments

import logging
from typing import Any

from domain.segment import Segment
from services.gemini_service import (
    DEFAULT_GEMINI_MODEL,
    ClipCandidate,
    select_clips_with_gemini,
    select_long_clips_with_gemini,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_DURATION = 20.0
DEFAULT_MAX_DURATION = 85.0
DEFAULT_MAX_CLIPS = 8


def _format_time_hms(seconds: float) -> str:
    """Format float seconds into HH:MM:SS or MM:SS string."""
    total_seconds_int = max(0, int(seconds))
    hours = total_seconds_int // 3600
    minutes = (total_seconds_int % 3600) // 60
    remaining_seconds = total_seconds_int % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def format_transcript_for_ai(segments: list[Segment], max_chars: int = 180000) -> str:
    """Formats a list of segments into a readable transcript with timestamps.

    Example line:
    [00:02:15 - 00:02:21 | 135.2s - 141.8s] O momento em que tudo mudou foi quando...
    """
    transcript_lines: list[str] = []
    total_character_count = 0

    for segment_index, segment in enumerate(segments):
        start_formatted = _format_time_hms(segment.start)
        end_formatted = _format_time_hms(segment.end)
        line = f"[{start_formatted} - {end_formatted} | {segment.start:.1f}s - {segment.end:.1f}s] {segment.text.strip()}"
        transcript_lines.append(line)
        total_character_count += len(line) + 1
        if total_character_count >= max_chars:
            logger.warning(
                f"Transcrição atingiu limite de {max_chars} caracteres. "
                f"Processando os primeiros {segment_index + 1} de {len(segments)} segmentos."
            )
            break

    return "\n".join(transcript_lines)


def align_candidate_to_segments(
    candidate: ClipCandidate,
    all_segments: list[Segment],
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
) -> list[Segment]:
    """Finds and aligns the exact contiguous list of Segment objects that cover the candidate's time window."""
    start_time = candidate["start_time"]
    end_time = candidate["end_time"]

    # Filter segments that fall within or overlap this window
    overlapping_segments = [
        segment
        for segment in all_segments
        if segment.end > start_time and segment.start < end_time
    ]

    if not overlapping_segments:
        # Fallback: find single closest segment
        closest_segment = min(
            all_segments,
            key=lambda segment: abs((segment.start + segment.end) / 2.0 - start_time),
        )
        overlapping_segments = [closest_segment]

    # Find starting and ending indices in all_segments
    first_index = all_segments.index(overlapping_segments[0])
    last_index = all_segments.index(overlapping_segments[-1])

    # Expand if duration is less than min_duration and adjacent segments exist
    current_duration = all_segments[last_index].end - all_segments[first_index].start
    while current_duration < min_duration:
        expanded = False
        if last_index + 1 < len(all_segments):
            next_duration = all_segments[last_index + 1].end - all_segments[first_index].start
            if next_duration <= max_duration:
                last_index += 1
                current_duration = next_duration
                expanded = True

        if current_duration < min_duration and first_index > 0:
            previous_duration = all_segments[last_index].end - all_segments[first_index - 1].start
            if previous_duration <= max_duration:
                first_index -= 1
                current_duration = previous_duration
                expanded = True

        if not expanded:
            break

    # Trim if duration exceeds max_duration
    while (
        (all_segments[last_index].end - all_segments[first_index].start) > max_duration
        and last_index > first_index
    ):
        last_index -= 1

    matched_segments = all_segments[first_index : last_index + 1]

    # Tag segments with AI viral score
    ai_score = float(candidate.get("viral_score", 8.0))
    for segment in matched_segments:
        segment.score = max(segment.score, ai_score)

    return matched_segments


def ai_create_clips(
    segments: list[Segment],
    video_title: str,
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
    max_clips: int = DEFAULT_MAX_CLIPS,
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    channel_name: str = "",
    video_description: str = "",
) -> tuple[list[list[Segment]], list[dict[str, Any]]]:
    """Uses Gemini AI to evaluate full video transcript and extract the most viral clips.

    Args:
        segments: List of transcribed video segments.
        video_title: Video or podcast title.
        min_duration: Desired minimum clip duration in seconds.
        max_duration: Desired maximum clip duration in seconds.
        max_clips: Maximum number of clips to select.
        api_key: Optional Gemini API key override.
        model: Gemini model identifier.
        channel_name: Optional channel or author name.
        video_description: Optional video description / synopsis.

    Returns:
        A tuple of:
        - final_clips: list of list of Segments for each clip.
        - clips_metadata: list of dicts with title, hook, reason, and score generated by Gemini.
    """
    if not segments:
        logger.warning("Nenhum segmento fornecido para seleção por IA.")
        return [], []

    logger.info(f"Formatando transcrição ({len(segments)} segmentos) para análise do Gemini...")
    formatted_transcript = format_transcript_for_ai(segments)

    logger.info("Enviando transcrição para análise semântica e narrativa do Gemini...")
    candidates = select_clips_with_gemini(
        formatted_transcript=formatted_transcript,
        video_title=video_title,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
        api_key=api_key,
        model=model,
        channel_name=channel_name,
        video_description=video_description,
    )

    if not candidates:
        logger.warning("Gemini não retornou nenhum corte válido.")
        return [], []

    logger.info(f"Gemini retornou {len(candidates)} candidatos. Alinhando com os segmentos de fala...")

    aligned_clips: list[list[Segment]] = []
    metadata_list: list[dict[str, Any]] = []

    for candidate in candidates:
        matched_segs = align_candidate_to_segments(
            candidate=candidate,
            all_segments=segments,
            min_duration=min_duration,
            max_duration=max_duration,
        )

        if not matched_segs:
            continue

        clip_start = matched_segs[0].start
        clip_end = matched_segs[-1].end
        duration = clip_end - clip_start

        # Check for heavy overlap (> 60%) with previously accepted clips
        is_duplicate = False
        for existing_clip in aligned_clips:
            existing_start = existing_clip[0].start
            existing_end = existing_clip[-1].end
            overlap_start = max(clip_start, existing_start)
            overlap_end = min(clip_end, existing_end)
            if overlap_end > overlap_start:
                overlap_duration = overlap_end - overlap_start
                if overlap_duration > (duration * 0.6) or overlap_duration > (
                    (existing_end - existing_start) * 0.6
                ):
                    is_duplicate = True
                    break

        if is_duplicate:
            logger.info(
                f"Descartando corte sobreposto [{clip_start:.1f}s - {clip_end:.1f}s]: '{candidate['title']}'"
            )
            continue

        # Attach metadata to the first segment of the clip
        metadata_entry = {
            "title": candidate["title"],
            "hook": candidate["hook"],
            "reason": candidate["reason"],
            "score": candidate["viral_score"],
            "start": clip_start,
            "end": clip_end,
            "duration": round(duration, 1),
        }
        setattr(matched_segs[0], "ai_metadata", metadata_entry)

        aligned_clips.append(matched_segs)
        metadata_list.append(metadata_entry)

        if len(aligned_clips) >= max_clips:
            break

    # Sort clips chronologically by start time
    paired_clips = sorted(zip(aligned_clips, metadata_list), key=lambda pair: pair[0][0].start)
    final_clips = [pair[0] for pair in paired_clips]
    final_metadata = [pair[1] for pair in paired_clips]

    logger.info(
        f"Seleção por IA concluída: {len(final_clips)} clipes otimizados e prontos para corte!"
    )
    return final_clips, final_metadata


def ai_create_long_clips(
    segments: list[Segment],
    video_title: str,
    min_duration: float = 180.0,
    max_duration: float = 1200.0,
    max_clips: int = 3,
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    channel_name: str = "",
    video_description: str = "",
) -> tuple[list[list[Segment]], list[dict[str, Any]]]:
    """Uses Gemini to identify long thematic discussion blocks (up to 20 min) from transcript segments."""
    if not segments:
        logger.warning("Nenhum segmento fornecido para seleção de cortes longos por IA.")
        return [], []

    logger.info(
        f"Formatando transcrição ({len(segments)} segmentos) para análise de cortes longos..."
    )
    formatted_transcript = format_transcript_for_ai(segments)

    logger.info("Enviando transcrição para análise de temas de corte longo com Gemini...")

    candidates = select_long_clips_with_gemini(
        formatted_transcript=formatted_transcript,
        video_title=video_title,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
        api_key=api_key,
        model=model,
        channel_name=channel_name,
        video_description=video_description,
    )

    if not candidates:
        logger.warning("Gemini não retornou nenhum corte longo válido.")
        return [], []

    logger.info(f"Gemini retornou {len(candidates)} temas longos. Alinhando aos segmentos...")

    aligned_clips: list[list[Segment]] = []
    metadata_list: list[dict[str, Any]] = []

    for candidate in candidates:
        matched_segs = align_candidate_to_segments(
            candidate=candidate,
            all_segments=segments,
            min_duration=min_duration,
            max_duration=max_duration,
        )

        if not matched_segs:
            continue

        clip_start = matched_segs[0].start
        clip_end = matched_segs[-1].end
        duration = clip_end - clip_start

        # Check for heavy overlap (> 50%)
        is_duplicate = False
        for existing_clip in aligned_clips:
            existing_start = existing_clip[0].start
            existing_end = existing_clip[-1].end
            overlap_start = max(clip_start, existing_start)
            overlap_end = min(clip_end, existing_end)
            if overlap_end > overlap_start:
                overlap_duration = overlap_end - overlap_start
                if overlap_duration > (duration * 0.5) or overlap_duration > (
                    (existing_end - existing_start) * 0.5
                ):
                    is_duplicate = True
                    break

        if is_duplicate:
            logger.info(
                f"Descartando tema longo sobreposto [{clip_start:.1f}s - {clip_end:.1f}s]: '{candidate['title']}'"
            )
            continue

        metadata_entry = {
            "title": candidate["title"],
            "hook": candidate["hook"],
            "reason": candidate["reason"],
            "score": candidate["viral_score"],
            "start": clip_start,
            "end": clip_end,
            "duration": round(duration, 1),
        }

        setattr(matched_segs[0], "ai_metadata", metadata_entry)

        aligned_clips.append(matched_segs)
        metadata_list.append(metadata_entry)

        if len(aligned_clips) >= max_clips:
            break

    paired_clips = sorted(zip(aligned_clips, metadata_list), key=lambda pair: pair[0][0].start)
    final_clips = [pair[0] for pair in paired_clips]
    final_metadata = [pair[1] for pair in paired_clips]

    logger.info(
        f"Seleção de cortes longos concluída: {len(final_clips)} temas estruturados!"
    )

    return final_clips, final_metadata

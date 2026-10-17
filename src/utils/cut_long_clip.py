import logging
import os
import re
import subprocess
import tempfile
from typing import Callable

logger = logging.getLogger(__name__)


def detect_silences_ffmpeg(
    media_path: str,
    noise_threshold_db: float = -30.0,
    min_silence_duration: float = 0.6,
) -> list[tuple[float, float]]:
    """Detect silent intervals in an audio/video file using FFmpeg's silencedetect filter.

    Args:
        media_path: Path to the media file.
        noise_threshold_db: Noise threshold in dB below which sound is treated as silence (e.g. -30.0).
        min_silence_duration: Minimum duration of silence in seconds to detect (e.g. 0.6).

    Returns:
        A list of tuples (silence_start, silence_end) in seconds.
    """
    if not os.path.exists(media_path):
        logger.error(f"Arquivo não encontrado para detecção de silêncio: {media_path}")
        return []

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "4",
        "-i", media_path,
        "-af", f"silencedetect=noise={noise_threshold_db}dB:d={min_silence_duration}",
        "-f", "null",
        "-",
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        stderr_output = proc.stderr or ""
    except Exception as exc:
        logger.error(f"Falha ao executar FFmpeg silencedetect: {exc}")
        return []

    silences: list[tuple[float, float]] = []
    current_start: float | None = None

    for line in stderr_output.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            try:
                current_start = float(start_match.group(1))
            except ValueError:
                current_start = None

        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and current_start is not None:
            try:
                end_time = float(end_match.group(1))
                if end_time > current_start:
                    silences.append((current_start, end_time))
            except ValueError:
                pass
            current_start = None

    logger.info(f"Detecção de silêncio: {len(silences)} pausas detectadas em {os.path.basename(media_path)}")
    return silences


def calculate_speech_intervals(
    total_duration: float,
    silences: list[tuple[float, float]],
    padding: float = 0.15,
    min_speech_duration: float = 0.25,
) -> tuple[list[tuple[float, float]], float]:
    """Invert silence intervals to produce active speech segments with safety padding.

    Args:
        total_duration: Total duration of the media in seconds.
        silences: List of (silence_start, silence_end) in seconds.
        padding: Safety buffer (in seconds) to retain before and after speech.
        min_speech_duration: Minimum speech duration to retain.

    Returns:
        A tuple of:
            - list of (speech_start, speech_end) segments to keep.
            - total silence duration in seconds that will be eliminated.
    """
    if total_duration <= 0:
        return ([(0.0, total_duration)], 0.0)

    if not silences:
        return ([(0.0, total_duration)], 0.0)

    # Adjust silence intervals with padding: silence begins later and ends earlier
    effective_silence_gaps: list[tuple[float, float]] = []
    for s_start, s_end in silences:
        cut_start = s_start + padding
        cut_end = s_end - padding
        if cut_end > cut_start:
            effective_silence_gaps.append((cut_start, cut_end))

    if not effective_silence_gaps:
        return ([(0.0, total_duration)], 0.0)

    # Invert gaps to obtain kept speech intervals
    speech_intervals: list[tuple[float, float]] = []
    current_pos = 0.0
    total_silence_removed = 0.0

    for gap_start, gap_end in effective_silence_gaps:
        gap_start = max(0.0, min(total_duration, gap_start))
        gap_end = max(0.0, min(total_duration, gap_end))

        if gap_start > current_pos:
            dur = gap_start - current_pos
            if dur >= min_speech_duration:
                speech_intervals.append((round(current_pos, 3), round(gap_start, 3)))
            elif speech_intervals:
                # Merge tiny segment with previous interval
                prev_start, _ = speech_intervals[-1]
                speech_intervals[-1] = (prev_start, round(gap_start, 3))
            else:
                speech_intervals.append((round(current_pos, 3), round(gap_start, 3)))

        total_silence_removed += max(0.0, gap_end - gap_start)
        current_pos = gap_end

    if current_pos < total_duration:
        dur = total_duration - current_pos
        if dur >= min_speech_duration:
            speech_intervals.append((round(current_pos, 3), round(total_duration, 3)))
        elif speech_intervals:
            prev_start, _ = speech_intervals[-1]
            speech_intervals[-1] = (prev_start, round(total_duration, 3))
        else:
            speech_intervals.append((round(current_pos, 3), round(total_duration, 3)))

    return speech_intervals, total_silence_removed


def cut_horizontal_clip_with_silence_removal(
    input_video: str,
    output_video: str,
    start: float,
    end: float,
    remove_silence: bool = True,
    noise_threshold_db: float = -30.0,
    min_silence_duration: float = 0.6,
    silence_padding: float = 0.15,
    on_log: Callable[[str, str], None] | None = None,
) -> dict:
    """Cut a horizontal 16:9 clip from input_video, optionally removing silent pauses.

    Keeps video and audio synchronized with zero drift by applying the trims simultaneously
    to both streams via FFmpeg concat filter.

    Args:
        input_video: Path to source video.
        output_video: Path for the final output video.
        start: Start timestamp in seconds in input_video.
        end: End timestamp in seconds in input_video.
        remove_silence: Whether to detect and remove silences.
        noise_threshold_db: Silence detection dB threshold.
        min_silence_duration: Silence detection minimum duration in seconds.
        silence_padding: Margin in seconds kept around speech cuts.
        on_log: Optional logging callback.

    Returns:
        A dict with processing statistics (duration_before, duration_after, silences_removed, etc.)
    """
    def _log(level: str, msg: str) -> None:
        if level == "error":
            logger.error(msg)
        elif level == "warning":
            logger.warning(msg)
        else:
            logger.info(msg)
        if on_log:
            on_log(level, msg)

    raw_duration = max(0.0, end - start)
    _log("info", f"Processando corte horizontal ({start:.1f}s até {end:.1f}s, duração original: {raw_duration:.1f}s)...")

    # If start/end bounds need pre-trimming from a longer full video
    temp_clip: str | None = None
    source_to_process = input_video

    # If the input video is a full podcast episode (start > 0 or end < input duration), extract raw horizontal segment first
    if start > 0.01:
        temp_clip = output_video.replace(".mp4", "_long_raw.mp4")
        _log("info", "Extraindo trecho bruto horizontal inicial...")
        extract_cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", input_video,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            temp_clip,
        ]
        res = subprocess.run(extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            _log("error", f"Erro ao extrair trecho preliminar: {res.stderr.decode('utf-8', errors='replace')}")
            temp_clip = None
        else:
            source_to_process = temp_clip

    try:
        if not remove_silence:
            _log("info", "Corte de silêncio desativado. Gerando clipe horizontal contínuo...")
            if source_to_process == temp_clip and temp_clip:
                os.replace(temp_clip, output_video)
                temp_clip = None
            else:
                simple_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-ss", f"{start:.3f}",
                    "-to", f"{end:.3f}",
                    "-i", input_video,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    output_video,
                ]
                subprocess.run(simple_cmd, check=True)

            return {
                "success": True,
                "duration_before": raw_duration,
                "duration_after": raw_duration,
                "silence_saved": 0.0,
                "pauses_cut": 0,
            }

        # ── Step 1: Detect silences ──────────────────────────────────────────
        _log("info", f"Analisando frequências de áudio (threshold: {noise_threshold_db}dB, min: {min_silence_duration}s)...")
        silences = detect_silences_ffmpeg(
            source_to_process,
            noise_threshold_db=noise_threshold_db,
            min_silence_duration=min_silence_duration,
        )

        effective_duration = raw_duration if source_to_process != input_video else (end - start)
        speech_intervals, total_silence_removed = calculate_speech_intervals(
            total_duration=effective_duration,
            silences=silences,
            padding=silence_padding,
        )

        pauses_count = len(silences)
        _log(
            "info",
            f"Resultado da análise: {pauses_count} pausas detectadas. "
            f"Economia estimada: {total_silence_removed:.1f}s de silêncio removido."
        )

        # If no significant silences were found or only 1 interval, save directly
        if len(speech_intervals) <= 1:
            _log("info", "Nenhum silêncio significativo detectado. Mantendo clipe contínuo.")
            if source_to_process == temp_clip and temp_clip:
                os.replace(temp_clip, output_video)
                temp_clip = None
            else:
                simple_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-ss", f"{start:.3f}",
                    "-to", f"{end:.3f}",
                    "-i", input_video,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    output_video,
                ]
                subprocess.run(simple_cmd, check=True)

            return {
                "success": True,
                "duration_before": raw_duration,
                "duration_after": raw_duration,
                "silence_saved": 0.0,
                "pauses_cut": 0,
            }

        # ── Step 2: Build FFmpeg filter_complex script ───────────────────────
        # Uses -filter_complex_script to bypass any command line length limitations on Windows
        n_segments = len(speech_intervals)
        filter_lines: list[str] = []
        concat_inputs: list[str] = []

        for idx, (sp_start, sp_end) in enumerate(speech_intervals):
            filter_lines.append(
                f"[0:v]trim=start={sp_start:.3f}:end={sp_end:.3f},setpts=PTS-STARTPTS[v{idx}];"
            )
            filter_lines.append(
                f"[0:a]atrim=start={sp_start:.3f}:end={sp_end:.3f},asetpts=PTS-STARTPTS[a{idx}];"
            )
            concat_inputs.append(f"[v{idx}][a{idx}]")

        filter_lines.append(f"{''.join(concat_inputs)}concat=n={n_segments}:v=1:a=1[outv][outa]")
        filter_script_content = "\n".join(filter_lines)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(filter_script_content)
            script_path = tf.name

        try:
            _log("info", f"Montando e renderizando clipe horizontal com {n_segments} trechos falados concatenados...")
            render_cmd = [
                "ffmpeg", "-y", "-nostdin",
                "-i", source_to_process,
                "-filter_complex_script", script_path,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "19",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_video,
            ]
            proc = subprocess.run(
                render_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if proc.returncode != 0:
                _log("error", f"FFmpeg falhou ao processar concatenador de silêncio: {proc.stderr[:400]}")
                # Fallback: copy without silence cuts
                if source_to_process == temp_clip and temp_clip:
                    os.replace(temp_clip, output_video)
                    temp_clip = None
                return {
                    "success": False,
                    "error": proc.stderr[:300],
                    "duration_before": raw_duration,
                    "duration_after": raw_duration,
                }

        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass

        new_duration = max(0.0, raw_duration - total_silence_removed)
        _log(
            "info",
            f"✅ Corte horizontal finalizado com sucesso! Duração: {new_duration:.1f}s "
            f"({total_silence_removed:.1f}s de silêncio cortado)."
        )

        return {
            "success": True,
            "duration_before": round(raw_duration, 1),
            "duration_after": round(new_duration, 1),
            "silence_saved": round(total_silence_removed, 1),
            "pauses_cut": pauses_count,
        }

    finally:
        if temp_clip and os.path.exists(temp_clip):
            try:
                os.remove(temp_clip)
            except Exception:
                pass

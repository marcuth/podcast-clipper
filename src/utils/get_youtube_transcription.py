import json
import logging
import os
import re
import urllib.request
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

logger = logging.getLogger(__name__)
ytt_api = YouTubeTranscriptApi()

def get_video_id(video_url: str) -> str:
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            return match.group(1)
            
    raise ValueError("Invalid YouTube URL")


def _fetch_subtitles_via_ytdlp(video_url: str) -> list[dict]:
    """Fallback: extract Portuguese subtitles or automatic captions via yt-dlp json3."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "js_runtimes": {"node": {}},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    }
    cookie_path = os.environ.get("YOUTUBE_COOKIES_PATH") or os.environ.get("COOKIES_FILE")
    if cookie_path and os.path.exists(cookie_path):
        ydl_opts["cookiefile"] = cookie_path
    elif os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    candidate_tracks = (
        subs.get("pt")
        or subs.get("pt-orig")
        or subs.get("pt-BR")
        or auto_subs.get("pt")
        or auto_subs.get("pt-orig")
        or auto_subs.get("pt-BR")
        or []
    )

    if not candidate_tracks:
        raise ValueError("Nenhuma legenda em português encontrada via yt-dlp.")

    json3_url = next((track["url"] for track in candidate_tracks if track.get("ext") == "json3"), None)
    if not json3_url:
        raise ValueError("URL de legenda no formato json3 não encontrada no yt-dlp.")

    request_obj = urllib.request.Request(json3_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request_obj, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_segments: list[dict] = []
    for event in payload.get("events", []):
        if "segs" not in event:
            continue
        text_content = "".join(part.get("utf8", "") for part in event["segs"]).replace("\n", " ").strip()
        if not text_content:
            continue
        start_seconds = float(event.get("tStartMs", 0)) / 1000.0
        duration_seconds = float(event.get("dDurationMs", 0)) / 1000.0
        raw_segments.append({
            "start": start_seconds,
            "end": start_seconds + duration_seconds,
            "text": text_content,
        })

    return raw_segments


def get_youtube_transcription(video_url: str) -> list[dict]:
    video_id = get_video_id(video_url)
    normalized_transcript = []

    try:
        transcript = ytt_api.fetch(video_id, languages=["pt"])
        for segment in transcript:
            text = segment.text.replace(">> ", "").replace("\n", " ").strip()
            normalized_transcript.append({
                "start": segment.start,
                "end": segment.start + segment.duration,
                "text": text
            })
    except Exception as exc:
        logger.warning(f"youtube_transcript_api falhou ({exc}). Extraindo legendas diretamente via yt-dlp...")
        normalized_transcript = _fetch_subtitles_via_ytdlp(video_url)
    
    # Ensure sorted by start time
    normalized_transcript.sort(key=lambda item: item["start"])

    final_transcript = []

    # Second pass: fix overlaps to ensure strict sequentiality
    for index, current_segment in enumerate(normalized_transcript):
        if index < len(normalized_transcript) - 1:
            next_start = normalized_transcript[index + 1]["start"]
            if current_segment["end"] > next_start:
                current_segment["end"] = next_start

        if current_segment["end"] > current_segment["start"]:
            final_transcript.append(current_segment)
        
    return final_transcript
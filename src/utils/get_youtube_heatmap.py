"""
Fetch YouTube's "most replayed" heatmap data for a given video.

Primary strategy: yt-dlp (extracts heatmap from the YouTube API directly).
Fallback strategy: scrape ytInitialData from the video page HTML.

Returned list format:
    [
        {
            "start":     float,   # window start in seconds
            "end":       float,   # window end   in seconds
            "intensity": float    # 0.0 → 1.0, higher = more replayed
        },
        ...
    ]
"""

import logging
import json
import re

import requests
import yt_dlp

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_INITIAL_DATA_RE = re.compile(
    r"var ytInitialData\s*=\s*(\{.+?\});\s*(?:var|</script)",
    re.DOTALL,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_video_id(video_url: str) -> str:
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {video_url}")


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 1 – yt-dlp (most reliable)
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_via_ytdlp(video_url: str) -> list[dict]:
    """
    Use yt-dlp to extract heatmap data from the video's info dict.
    yt-dlp returns a list of dicts with keys: start_time, end_time, value.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"]
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    raw = info.get("heatmap") or []

    if not raw:
        return []

    heatmap: list[dict] = []
    max_val = max((entry.get("value", 0) for entry in raw), default=1) or 1

    for entry in raw:
        try:
            start     = float(entry["start_time"])
            end       = float(entry["end_time"])
            intensity = float(entry["value"]) / max_val  # normalise to [0, 1]
            heatmap.append({"start": start, "end": end, "intensity": intensity})
        except (KeyError, ValueError, TypeError):
            continue

    return heatmap


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 2 – HTML scraping (fallback)
# ──────────────────────────────────────────────────────────────────────────────

def _extract_initial_data(html: str) -> dict:
    match = _YT_INITIAL_DATA_RE.search(html)
    if not match:
        raise ValueError("ytInitialData not found in page HTML.")
    return json.loads(match.group(1))


def _find_heat_markers(data: dict) -> list[dict]:
    """Navigate the deeply-nested ytInitialData to find the HEATSEEKER markers."""
    try:
        overlays    = data["playerOverlays"]["playerOverlayRenderer"]
        decorated   = overlays["decoratedPlayerBarRenderer"]["decoratedPlayerBarRenderer"]
        player_bar  = decorated["playerBar"]["multiMarkersPlayerBarRenderer"]
        markers_map = player_bar["markersMap"]
    except KeyError:
        return []

    for entry in markers_map:
        if entry.get("key") == "HEATSEEKER":
            try:
                return entry["value"]["heatmap"]["heatmapRenderer"]["heatMarkers"]
            except KeyError:
                return []

    return []


def _fetch_via_scraping(video_url: str) -> list[dict]:
    video_id = get_video_id(video_url)
    url = f"https://www.youtube.com/watch?v={video_id}"

    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()

    data        = _extract_initial_data(response.text)
    raw_markers = _find_heat_markers(data)

    if not raw_markers:
        return []

    heatmap: list[dict] = []
    for marker in raw_markers:
        try:
            inner     = marker["heatMarkerRenderer"]
            start     = float(inner["timeRangeStartMillis"]) / 1000.0
            duration  = float(inner["markerDurationMillis"]) / 1000.0
            intensity = float(inner["heatMarkerIntensityScoreNormalized"])
            heatmap.append({"start": start, "end": start + duration, "intensity": intensity})
        except (KeyError, ValueError, TypeError):
            continue

    return heatmap


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get_youtube_heatmap(video_url: str) -> list[dict]:
    """
    Return the list of heat-map windows for *video_url*.

    Tries yt-dlp first; falls back to HTML scraping if that yields nothing.
    Each item is a dict with keys ``start``, ``end``, and ``intensity``.
    Returns an empty list when the video has no "most replayed" data.
    """
    logger.info("Fetching YouTube heatmap (most replayed) data…")

    # ── Strategy 1: yt-dlp ───────────────────────────────────────────────────
    try:
        heatmap = _fetch_via_ytdlp(video_url)
        if heatmap:
            logger.info(f"Heatmap fetched via yt-dlp: {len(heatmap)} markers.")
            return heatmap
        logger.debug("yt-dlp returned no heatmap data; trying HTML scraping…")
    except Exception as exc:
        logger.warning(f"yt-dlp heatmap extraction failed: {exc}; trying HTML scraping…")

    # ── Strategy 2: HTML scraping ─────────────────────────────────────────────
    try:
        heatmap = _fetch_via_scraping(video_url)
        if heatmap:
            logger.info(f"Heatmap fetched via scraping: {len(heatmap)} markers.")
            return heatmap
    except Exception as exc:
        logger.warning(f"HTML scraping heatmap extraction failed: {exc}")

    logger.warning(
        "No heatmap data found for this video "
        "(feature may not be available for this video)."
    )
    return []

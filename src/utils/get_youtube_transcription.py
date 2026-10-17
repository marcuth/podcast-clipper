from youtube_transcript_api import YouTubeTranscriptApi
import re

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

def get_youtube_transcription(video_url: str) -> list[dict]:
    video_id = get_video_id(video_url)
    transcript = ytt_api.fetch(video_id, languages=["pt"])
    
    normalized_transcript = []
    
    # First pass: standardize format
    for segment in transcript:
        # Standardize content
        text = segment.text.replace(">> ", "").replace("\n", " ").strip()
        start = segment.start
        duration = segment.duration
        
        normalized_transcript.append({
            "start": start,
            "end": start + duration,
            "text": text
        })

    # Ensure sorted by start time
    normalized_transcript.sort(key=lambda x: x["start"])

    final_transcript = []

    # Second pass: fix overlaps to ensure strict sequentiality
    for i, current_segment in enumerate(normalized_transcript):
        # Determine the maximum allowed end time (start of the next segment)
        if i < len(normalized_transcript) - 1:
            next_start = normalized_transcript[i + 1]["start"]
            if current_segment["end"] > next_start:
                current_segment["end"] = next_start

        # Only add valid segments with positive duration
        if current_segment["end"] > current_segment["start"]:
            final_transcript.append(current_segment)
        
    return final_transcript
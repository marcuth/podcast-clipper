from simple_youtube_api.LocalVideo import LocalVideo
from simple_youtube_api.Channel import Channel
import os

class YouTubeService:
    def __init__(self, client_secrets_file: str = "client_secret.json", credentials_storage_file: str = "credentials.storage"):
        if not os.path.exists(client_secrets_file):
            raise FileNotFoundError(f"Client secrets file not found: {client_secrets_file}. Please download it from Google Cloud Console.")
        
        self.channel = Channel()
        self.channel.login(client_secrets_file, credentials_storage_file)

    def upload_clip(self, video_path: str, details: dict, privacy_status: str = "public") -> str:
        video = LocalVideo(file_path=video_path)
        
        video.set_title(details["title"])
        video.set_description(details["description"])
        video.set_tags(details.get("tags", []))
        video.set_category("Entertainment") 
        video.set_default_language("pt")
        video.set_privacy_status(privacy_status)
        video.set_made_for_kids(False)

        video = self.channel.upload_video(video)

        return video.id

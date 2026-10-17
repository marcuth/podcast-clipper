import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv
from simple_youtube_api import Channel, LocalVideo

load_dotenv()
logger = logging.getLogger(__name__)


class YouTubeUploadResult(TypedDict):
    success: bool
    video_id: str | None
    video_url: str | None
    title: str
    error: str | None


class YouTubeService:
    """Service wrapper around simple-youtube-api for automated YouTube uploads and scheduling."""

    def __init__(
        self,
        client_secrets_file: str | None = None,
        credentials_storage_file: str | None = None,
    ) -> None:
        load_dotenv()
        workspace_root = Path(__file__).resolve().parent.parent.parent

        default_secret_path = os.environ.get("YOUTUBE_CLIENT_SECRET_FILE") or str(
            workspace_root / "client_secret.json"
        )
        default_storage_path = os.environ.get("YOUTUBE_CREDENTIALS_FILE") or str(
            workspace_root / "credentials.storage"
        )

        self.client_secrets_file = client_secrets_file or default_secret_path
        self.credentials_storage_file = credentials_storage_file or default_storage_path
        self.channel: Channel | None = None
        self._ensure_client_secrets_file()

    def _ensure_client_secrets_file(self) -> bool:
        """Ensure client secrets file exists, creating or updating it from YOUTUBE_CLIENT_SECRET if present."""
        load_dotenv()

        env_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
        if not env_secret:
            return os.path.exists(self.client_secrets_file)

        # If it points to an existing file path, use that path
        if os.path.exists(env_secret):
            self.client_secrets_file = env_secret
            return True

        # Otherwise, parse/write JSON content to client_secrets_file
        try:
            # Handle quoted JSON or raw JSON
            raw_content = env_secret
            if (raw_content.startswith("'") and raw_content.endswith("'")) or (
                raw_content.startswith('"') and raw_content.endswith('"')
            ):
                raw_content = raw_content[1:-1].strip()

            parsed_json = json.loads(raw_content)
            os.makedirs(os.path.dirname(os.path.abspath(self.client_secrets_file)), exist_ok=True)
            with open(self.client_secrets_file, "w", encoding="utf-8") as secrets_handle:
                json.dump(parsed_json, secrets_handle, indent=2)
            logger.info(f"Arquivo '{self.client_secrets_file}' gerado com sucesso a partir de YOUTUBE_CLIENT_SECRET.")
            return True
        except Exception as parse_error:
            # Fallback: if it's already a json-like string, attempt writing directly
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.client_secrets_file)), exist_ok=True)
                with open(self.client_secrets_file, "w", encoding="utf-8") as secrets_handle:
                    secrets_handle.write(env_secret)
                return True
            except Exception as write_error:
                logger.error(f"Erro ao salvar YOUTUBE_CLIENT_SECRET no arquivo: {parse_error} / {write_error}")
                return os.path.exists(self.client_secrets_file)

    def is_configured(self) -> bool:
        """Check if client_secret.json is provided on the file system or via YOUTUBE_CLIENT_SECRET."""
        return self._ensure_client_secrets_file()

    def is_authenticated(self) -> bool:
        """Check if credentials.storage exists and is non-empty."""
        return (
            os.path.exists(self.credentials_storage_file)
            and os.path.getsize(self.credentials_storage_file) > 0
        )

    def get_auth_status(self) -> dict[str, Any]:
        """Return diagnostic status of YouTube credentials and setup."""
        return {
            "is_configured": self.is_configured(),
            "is_authenticated": self.is_authenticated(),
            "has_env_secret": bool(os.environ.get("YOUTUBE_CLIENT_SECRET")),
            "client_secrets_file": self.client_secrets_file,
            "credentials_storage_file": self.credentials_storage_file,
        }

    def login(self) -> bool:
        """Authenticate or load existing credentials for the YouTube channel."""
        if not self.is_configured():
            logger.error(
                f"Client secrets file not found at: {self.client_secrets_file}. "
                "Baixe o arquivo client_secret.json no Google Cloud Console e coloque-o na raiz do projeto."
            )
            return False

        try:
            logger.info("Autenticando canal do YouTube com simple-youtube-api...")
            channel_instance = Channel()
            channel_instance.login(self.client_secrets_file, self.credentials_storage_file)
            self.channel = channel_instance
            logger.info("Login no canal do YouTube realizado com sucesso!")
            return True
        except Exception as login_exception:
            logger.error(f"Erro durante o login no YouTube: {login_exception}")
            return False

    def upload_clip(
        self,
        video_path: str,
        details: dict[str, Any],
        privacy_status: str = "public",
        category: str = "Entertainment",
        default_language: str = "pt",
        thumbnail_path: str | None = None,
        publish_at: str | None = None,
        made_for_kids: bool = False,
        like_after_upload: bool = False,
    ) -> YouTubeUploadResult:
        """Upload a video file to the logged-in YouTube channel with metadata.

        Args:
            video_path: Path to the local .mp4 video file to upload.
            details: Dictionary containing 'title', 'description', and optional 'tags'.
            privacy_status: 'public', 'private', or 'unlisted'.
            category: YouTube video category name (e.g. 'Entertainment', 'People & Blogs').
            default_language: Default audio/subtitle language code.
            thumbnail_path: Optional path to custom thumbnail image (PNG/JPG).
            publish_at: Optional ISO 8601 string for scheduled release (e.g. 2026-10-20T15:00:00Z).
            made_for_kids: Whether the video is marked as COPPA compliant child-directed content.
            like_after_upload: Automatically like the uploaded video upon completion.

        Returns:
            YouTubeUploadResult containing status, video_id, and video_url.
        """
        if not os.path.exists(video_path):
            error_message = f"Arquivo de vídeo não encontrado para upload: {video_path}"
            logger.error(error_message)
            return {
                "success": False,
                "video_id": None,
                "video_url": None,
                "title": details.get("title", ""),
                "error": error_message,
            }

        if self.channel is None:
            login_success = self.login()
            if not login_success or self.channel is None:
                error_message = (
                    "Não foi possível autenticar com o YouTube. "
                    "Verifique se o arquivo client_secret.json está configurado."
                )
                logger.error(error_message)
                return {
                    "success": False,
                    "video_id": None,
                    "video_url": None,
                    "title": details.get("title", ""),
                    "error": error_message,
                }

        try:
            logger.info(f"Iniciando preparação de upload para o YouTube: {video_path}")
            local_video = LocalVideo(file_path=video_path)

            raw_title = str(details.get("title", "Sem título")).strip()
            # YouTube titles are limited to 100 characters
            video_title = raw_title[:100] if len(raw_title) > 100 else raw_title
            local_video.set_title(video_title)

            raw_description = str(details.get("description", "")).strip()
            # YouTube descriptions are limited to 5000 characters
            video_description = raw_description[:5000] if len(raw_description) > 5000 else raw_description
            local_video.set_description(video_description)

            raw_tags = details.get("tags", [])
            cleaned_tags: list[str] = []
            if isinstance(raw_tags, list):
                cleaned_tags = [str(tag_item).strip() for tag_item in raw_tags if str(tag_item).strip()]
            elif isinstance(raw_tags, str):
                cleaned_tags = [tag_item.strip() for tag_item in raw_tags.split(",") if tag_item.strip()]

            if cleaned_tags:
                local_video.set_tags(cleaned_tags)

            # Map category to numeric ID to bypass simple_youtube_api case-sensitive lookup bug
            category_normalized = category.lower().strip() if isinstance(category, str) else category
            category_id = 24  # Default: Entertainment (24)
            if isinstance(category_normalized, int):
                category_id = category_normalized
            elif isinstance(category_normalized, str):
                category_map = {
                    "entertainment": 24,
                    "people & blogs": 22,
                    "people": 22,
                    "blogs": 22,
                    "comedy": 23,
                    "news & politics": 25,
                    "news": 25,
                    "politics": 25,
                    "education": 27,
                    "science & technology": 28,
                    "science": 28,
                    "technology": 28,
                    "howto & style": 26,
                    "gaming": 20,
                    "music": 10,
                    "sports": 17,
                    "film & animation": 1,
                    "film": 1,
                    "animation": 1,
                }
                category_id = category_map.get(category_normalized, 24)

            try:
                local_video.set_category(category_id)
            except Exception:
                local_video.category = category_id
            local_video.set_default_language(default_language)
            local_video.set_privacy_status(privacy_status)
            local_video.set_made_for_kids(made_for_kids)
            local_video.set_embeddable(True)
            local_video.set_public_stats_viewable(True)

            if thumbnail_path and os.path.exists(thumbnail_path):
                logger.info(f"Adicionando thumbnail customizada: {thumbnail_path}")
                local_video.set_thumbnail_path(thumbnail_path)

            if publish_at:
                logger.info(f"Agendando publicação automática para: {publish_at}")
                local_video.set_publish_at(publish_at)

            logger.info(f"Enviando vídeo '{video_title}' para o YouTube...")
            uploaded_video = self.channel.upload_video(local_video)

            uploaded_video_id = str(uploaded_video.id)
            uploaded_video_url = f"https://youtu.be/{uploaded_video_id}"

            logger.info(f"Upload concluído com sucesso! ID: {uploaded_video_id} - URL: {uploaded_video_url}")

            if like_after_upload:
                try:
                    uploaded_video.like()
                    logger.info("Vídeo curtido automaticamente com sucesso!")
                except Exception as like_exception:
                    logger.warning(f"Não foi possível curtir o vídeo enviado: {like_exception}")

            return {
                "success": True,
                "video_id": uploaded_video_id,
                "video_url": uploaded_video_url,
                "title": video_title,
                "error": None,
            }

        except Exception as upload_exception:
            error_message = f"Falha durante o upload para o YouTube: {str(upload_exception)}"
            logger.error(error_message)
            
            return {
                "success": False,
                "video_id": None,
                "video_url": None,
                "title": details.get("title", ""),
                "error": error_message,
            }

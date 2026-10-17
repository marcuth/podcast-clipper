import logging
import os
import sys
from pathlib import Path

# Ensure src is in sys.path
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import webview
from dotenv import load_dotenv

from src.gui.api import ClipperApi
from src.gui.server import LocalMediaServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def start_gui() -> None:
    """Launch the PyWebView desktop application for AutoClip."""
    load_dotenv()

    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    logger.info("Iniciando AutoClip Studio...")
    logger.info(f"Workspace root: {workspace_root}")

    # Start local HTTP server for serving assets and range-based video streaming
    server = LocalMediaServer(workspace_root)
    base_url = server.start()

    # Instantiate the native Python API exposed to JS
    api = ClipperApi(workspace_root)

    # Configure PyWebView settings
    webview.settings["ALLOW_FILE_URLS"] = True
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = True

    # Support Vite dev server for hot reloading if specified
    dev_url = os.environ.get("VITE_DEV_URL")
    target_url = dev_url if dev_url else base_url

    # Create native desktop window
    window = webview.create_window(
        title="AutoClip Studio — Podcast Clipper AI",
        url=target_url,
        js_api=api,
        width=1320,
        height=880,
        min_size=(1040, 720),
        background_color="#0A0E17",
    )

    # Allow the API to evaluate JS events back to the window
    api.set_window(window)

    debug_mode = os.environ.get("AUTOCLIP_DEBUG", "").lower() in ("1", "true")
    webview.start(debug=debug_mode)


if __name__ == "__main__":
    start_gui()

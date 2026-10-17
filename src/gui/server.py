import logging
import os
import socket
import threading
from pathlib import Path
from bottle import Bottle, static_file, response

logger = logging.getLogger(__name__)


def find_free_port(default_port: int = 48123) -> int:
    """Check if the default port is free, or find an available one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", default_port)) != 0:
            return default_port
    # Port was occupied, ask OS for an available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def create_app(workspace_root: str) -> Bottle:
    """Create and configure the Bottle application serving web assets and output media."""
    app = Bottle()

    gui_web_dir = os.path.join(os.path.dirname(__file__), "web")
    os.makedirs(gui_web_dir, exist_ok=True)
    output_dir = os.path.join(workspace_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    @app.hook("after_request")
    def enable_cors():
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token"

    @app.route("/")
    def index():
        index_path = os.path.join(gui_web_dir, "index.html")
        if not os.path.exists(index_path):
            return (
                "<h3>AutoClip Studio</h3>"
                "<p>Build do frontend não encontrada. Execute <code>npm run build</code> dentro da pasta "
                "<code>client/</code> ou configure <code>VITE_DEV_URL</code> no <code>.env</code> para desenvolvimento.</p>"
            )
        return static_file("index.html", root=gui_web_dir)

    @app.route("/media/<filepath:path>")
    def serve_media(filepath):
        """Serve video files with automatic Accept-Ranges support for scrubbing."""
        return static_file(filepath, root=output_dir, mimetype="video/mp4")

    @app.route("/<filepath:path>")
    def serve_static(filepath):
        return static_file(filepath, root=gui_web_dir)

    return app


class LocalMediaServer:
    """Embedded HTTP server for serving the web GUI and streaming clips."""

    def __init__(self, workspace_root: str, port: int = 48123) -> None:
        self.workspace_root = workspace_root
        self.port = find_free_port(port)
        self.app = create_app(workspace_root)
        self.server_thread: threading.Thread | None = None
        self._is_running = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> str:
        """Start the server in a background daemon thread and return the base URL."""
        if self._is_running:
            return self.base_url

        def run_server():
            logger.info(f"Iniciando servidor local do AutoClip em {self.base_url}")
            try:
                self.app.run(
                    host="127.0.0.1",
                    port=self.port,
                    quiet=True,
                    server="wsgiref",
                )
            except Exception as e:
                logger.error(f"Erro no servidor local: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self._is_running = True
        return self.base_url

import atexit
import logging
import os
import socket
import subprocess
import sys
import time
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


def is_port_in_use(port_number: int = 5173, host_address: str = "127.0.0.1") -> bool:
    """Check whether a given TCP port is currently open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
        probe_socket.settimeout(0.4)
        return probe_socket.connect_ex((host_address, port_number)) == 0


def wait_for_server(port_number: int = 5173, host_address: str = "127.0.0.1", timeout_seconds: float = 20.0) -> bool:
    """Wait until the development server port is ready and accepting connections."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_port_in_use(port_number, host_address):
            return True
        time.sleep(0.3)
    return False


def start_vite_dev_server(workspace_root: str) -> subprocess.Popen[str] | None:
    """Spawn the Vite development server in the client directory if not already running."""
    if is_port_in_use(5173):
        logger.info("Vite dev server já está ativo e respondendo na porta 5173.")
        return None

    client_directory = os.path.join(workspace_root, "client")
    npm_executable = "npm.cmd" if sys.platform == "win32" else "npm"

    logger.info(f"Iniciando servidor Vite em desenvolvimento: {npm_executable} run dev...")
    vite_process = subprocess.Popen(
        [npm_executable, "run", "dev"],
        cwd=client_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    is_ready = wait_for_server(5173, timeout_seconds=20.0)
    if is_ready:
        logger.info("Servidor Vite iniciado com sucesso em http://127.0.0.1:5173!")
    else:
        logger.warning("Tempo limite aguardando o Vite responder na porta 5173.")

    return vite_process


def start_gui(dev_mode: bool = False) -> None:
    """Launch the PyWebView desktop application for Podcast Clipper.

    Args:
        dev_mode: If True, boots or attaches to the Vite dev server with Hot-Module-Reloading.
                  If False, serves the compiled static web bundle from src/gui/web.
    """
    load_dotenv()

    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    logger.info("Iniciando Podcast Clipper...")
    logger.info(f"Workspace root: {workspace_root}")

    # Start local HTTP server for serving range-based video streaming and media assets
    media_server = LocalMediaServer(workspace_root)
    base_media_url = media_server.start()

    # Instantiate the native Python API exposed to JS
    clipper_api = ClipperApi(workspace_root)

    # Configure PyWebView engine settings
    webview.settings["ALLOW_FILE_URLS"] = True
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = True

    vite_process: subprocess.Popen[str] | None = None

    if dev_mode:
        logger.info("Modo de desenvolvimento ativado. Conectando ao servidor Vite...")
        vite_process = start_vite_dev_server(workspace_root)

        def terminate_vite_process() -> None:
            if vite_process and vite_process.poll() is None:
                logger.info("Encerrando servidor Vite de desenvolvimento...")
                vite_process.terminate()
                try:
                    vite_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    vite_process.kill()

        atexit.register(terminate_vite_process)
        target_url = "http://127.0.0.1:5173"
        window_title = "Podcast Clipper [Modo Dev - Vite HMR]"
        debug_mode = True
    else:
        # Production mode: prioritize local static web build
        dev_url_override = os.environ.get("VITE_DEV_URL")
        target_url = dev_url_override if dev_url_override else base_media_url
        window_title = "Podcast Clipper"
        debug_mode = os.environ.get("AUTOCLIP_DEBUG", "").lower() in ("1", "true")

    logger.info(f"Carregando interface a partir de: {target_url}")

    # Create native desktop window maximized by default
    desktop_window = webview.create_window(
        title=window_title,
        url=target_url,
        js_api=clipper_api,
        width=1440,
        height=900,
        min_size=(1080, 720),
        maximized=True,
        background_color="#0A0E17",
    )

    # Allow the API to evaluate JS events back to the window
    clipper_api.set_window(desktop_window)

    # Ensure the window maximizes reliably upon rendering
    def on_window_shown() -> None:
        try:
            desktop_window.maximize()
        except Exception:
            pass

    desktop_window.events.shown += on_window_shown

    try:
        webview.start(debug=debug_mode)
    finally:
        if dev_mode and vite_process and vite_process.poll() is None:
            logger.info("Janela fechada. Finalizando processo Vite...")
            vite_process.terminate()


def start_gui_dev() -> None:
    """Entry point for development mode (starts Vite server and connects with HMR)."""
    start_gui(dev_mode=True)


if __name__ == "__main__":
    start_gui()

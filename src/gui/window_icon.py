"""Application icon for the pywebview window.

pywebview only honours ``start(icon=...)`` on GTK/Qt, so on Windows the icon is set natively
on the window handle (title bar + taskbar) and the process gets its own taskbar identity.
"""

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

APP_USER_MODEL_ID = "Marcuth.PodcastClipper"
_ICON_DIR = os.path.join("assets", "icons")


def resolve_icon_path(workspace_root: str, extension: str) -> str | None:
    """Locate ``icon.<extension>``, also inside a PyInstaller bundle."""
    roots = [workspace_root, getattr(sys, "_MEIPASS", "")]

    for root in roots:
        candidate = os.path.join(root, _ICON_DIR, f"icon.{extension}") if root else ""

        if candidate and os.path.exists(candidate):
            return candidate

    return None


def set_app_user_model_id() -> None:
    """Make Windows group the taskbar button under this app instead of python.exe."""
    if sys.platform != "win32":
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as exc:
        logger.debug(f"Não foi possível definir o AppUserModelID: {exc}")


def apply_window_icon(window: Any, ico_path: str | None) -> None:
    """Set the title-bar and taskbar icon of *window* (Windows only; no-op elsewhere)."""
    if sys.platform != "win32" or not ico_path:
        return

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        hwnd = int(window.native.Handle.ToInt64())
        image_icon, load_from_file, wm_seticon = 1, 0x10, 0x80

        for icon_kind, size in ((0, 16), (1, 256)):  # ICON_SMALL (title bar), ICON_BIG (taskbar / alt-tab)
            handle = user32.LoadImageW(None, ico_path, image_icon, size, size, load_from_file)

            if handle:
                user32.SendMessageW(hwnd, wm_seticon, icon_kind, handle)
    except Exception as exc:
        logger.debug(f"Não foi possível aplicar o ícone da janela: {exc}")

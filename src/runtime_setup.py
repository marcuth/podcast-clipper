"""Runtime setup for the packaged (PyInstaller) app.

The bundle is read-only, so on first run the resources the app reads relative to its working
directory (``models/``, ``assets/``) are copied into a writable workspace, which also holds
``.env`` and ``output/``. A bundled ``bin/`` folder with ffmpeg/ffprobe is put on PATH.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SEEDED_FOLDERS = ("models", "assets")
SEEDED_FILES = (".env.example",)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_workspace_root() -> str:
    """Source runs use the repository; packaged runs use a writable folder."""
    if not is_frozen():
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # A macOS .app bundle must not be written to, so it uses a folder in the home directory.
    if sys.platform == "darwin":
        return str(Path.home() / "PodcastClipper")

    return os.path.dirname(sys.executable)


def _copy_missing(source: Path, target: Path) -> None:
    """Copy *source* into *target* without overwriting files the user already changed."""
    for item in source.rglob("*"):
        destination = target / item.relative_to(source)

        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def prepare_frozen_workspace(workspace_root: str) -> None:
    """Seed the workspace, make it the working directory and expose the bundled ffmpeg."""
    if not is_frozen():
        return

    bundle = Path(getattr(sys, "_MEIPASS", ""))
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)

    for folder in SEEDED_FOLDERS:
        if (bundle / folder).is_dir():
            _copy_missing(bundle / folder, root / folder)

    for file_name in SEEDED_FILES:
        if (bundle / file_name).is_file() and not (root / file_name).exists():
            shutil.copy2(bundle / file_name, root / file_name)

    bundled_bin = bundle / "bin"
    if bundled_bin.is_dir():
        os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")

    os.chdir(root)
    logger.info(f"Workspace do app empacotado: {root}")

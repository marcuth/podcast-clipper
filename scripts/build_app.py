"""Builds the desktop app with PyInstaller (Windows, macOS or Linux) and optionally zips it.

Run from the repository root, after ``npm run build`` in ``client/``:

    poetry run python scripts/build_app.py --package

Needs PyInstaller in the same environment and ffmpeg/ffprobe on PATH (they are bundled).
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "PodcastClipper"
BUNDLE_ID = "com.marcuth.podcastclipper"

# --collect-all imports every submodule of a package in a helper process, and native libraries such as
# MediaPipe crash that process on headless CI runners (Windows exit code 0xC0000409). For those only
# the data files and shared libraries are collected; the modules the app uses are found by import analysis.
COLLECT_ALL = ["yt_dlp", "imageio_ffmpeg", "moviepy"]  # pure Python, lazily imported modules
COLLECT_DATA = ["mediapipe", "faster_whisper", "ctranslate2", "onnxruntime", "webview"]
COLLECT_BINARIES = ["mediapipe", "ctranslate2", "onnxruntime"]
# Data-only package that MediaPipe loads through importlib.resources.
EXTRA_HIDDEN_IMPORTS = ["mediapipe.tasks.c"]

# The code imports its own packages under two names (``src.utils`` and ``utils``); collecting them
# explicitly makes sure the top-level names exist in the bundle too.
OWN_PACKAGES = ["utils", "domain", "heuristics", "services", "core", "strategies", "cli"]

PLATFORM_HIDDEN_IMPORTS = {
    "win32": ["webview.platforms.winforms", "clr"],
    "darwin": ["webview.platforms.cocoa"],
    "linux": ["webview.platforms.qt"],
}


def _target_label() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    return f"{system}-{arch}"


def _add_data(source: Path, destination: str) -> list[str]:
    return ["--add-data", f"{source}{os.pathsep}{destination}"]


def _stage_resources(stage: Path, with_ffmpeg: bool) -> list[str]:
    """Copy what goes into the bundle into a clean folder (no node_modules, no stray outputs)."""
    if stage.exists():
        shutil.rmtree(stage)

    stage.mkdir(parents=True)
    args: list[str] = []

    remotion = stage / "remotion"
    shutil.copytree(
        ROOT / "remotion",
        remotion,
        ignore=shutil.ignore_patterns("node_modules", "out", "*.webm", "*.mp4"),
    )
    args += _add_data(remotion, "remotion")

    if with_ffmpeg:
        bin_dir = stage / "bin"
        bin_dir.mkdir()

        for tool in ("ffmpeg", "ffprobe"):
            found = shutil.which(tool)

            if not found:
                raise SystemExit(f"{tool} não encontrado no PATH (use --no-ffmpeg para não embutir).")

            shutil.copy2(found, bin_dir)

        args += _add_data(bin_dir, "bin")

    return args


def _mac_icon(stage: Path) -> list[str]:
    from PIL import Image

    icon = stage / "icon.icns"
    Image.open(ROOT / "assets" / "icons" / "icon.png").save(icon)
    return ["--icon", str(icon)]


def build(args: argparse.Namespace) -> Path:
    web_index = ROOT / "src" / "gui" / "web" / "index.html"

    if not web_index.exists():
        raise SystemExit("Interface não compilada: rode `npm run build` dentro de client/ primeiro.")

    stage = ROOT / "build" / "stage"
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--paths", str(ROOT / "src"),
        "--distpath", str(args.distpath),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
    ]
    command.append("--console" if args.console else "--windowed")
    command += _stage_resources(stage, with_ffmpeg=not args.no_ffmpeg)
    command += _add_data(ROOT / "src" / "gui" / "web", "src/gui/web")
    command += _add_data(ROOT / "models", "models")
    command += _add_data(ROOT / "assets", "assets")
    command += _add_data(ROOT / ".env.example", ".")

    for package in COLLECT_ALL:
        command += ["--collect-all", package]

    for package in COLLECT_DATA:
        command += ["--collect-data", package]

    for package in COLLECT_BINARIES:
        command += ["--collect-binaries", package]

    for module in EXTRA_HIDDEN_IMPORTS:
        command += ["--hidden-import", module]

    for package in OWN_PACKAGES:
        command += ["--collect-submodules", package]

    for module in PLATFORM_HIDDEN_IMPORTS.get(sys.platform, []):
        command += ["--hidden-import", module]

    if sys.platform == "win32":
        command += ["--icon", str(ROOT / "assets" / "icons" / "icon.ico")]
    elif sys.platform == "darwin":
        command += _mac_icon(stage) + ["--osx-bundle-identifier", BUNDLE_ID]

    command.append(str(ROOT / "launcher.py"))
    subprocess.run(command, cwd=ROOT, check=True)

    return args.distpath / (f"{APP_NAME}.app" if sys.platform == "darwin" and not args.console else APP_NAME)


def package(built: Path, distpath: Path) -> Path:
    base = distpath / f"{APP_NAME}-{_target_label()}"

    if sys.platform == "darwin" and built.suffix == ".app":
        archive = base.with_suffix(".zip")
        # ditto keeps the symlinks and attributes a .app bundle needs.
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(built), str(archive)], check=True)
        return archive

    archive_format = "zip" if sys.platform == "win32" else "gztar"
    return Path(shutil.make_archive(str(base), archive_format, root_dir=built.parent, base_dir=built.name))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", action="store_true", help="also create the release archive in --distpath")
    parser.add_argument("--console", action="store_true", help="keep a console window (useful to debug a build)")
    parser.add_argument("--no-ffmpeg", action="store_true", help="do not bundle ffmpeg/ffprobe")
    parser.add_argument("--distpath", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    args.distpath = args.distpath.resolve()

    built = build(args)
    print(f"App gerado em: {built}")

    if args.package:
        print(f"Pacote: {package(built, args.distpath)}")


if __name__ == "__main__":
    main()

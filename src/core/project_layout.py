"""
On-disk layout shared by shorts and long clips of the same video.

Both formats live in one project folder (``output/<slug>/``) and share the downloaded video.
They never overwrite each other because the clip files are named by format:

    shorts -> clips/clip_00.mp4, clips/clip_00_details.json, plan in clips.json
    long   -> clips/long_00.mp4, clips/long_00_details.json, plan in long_clips.json
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

SHORT_PREFIX = "clip"
LONG_PREFIX = "long"

_CLIP_NAME = re.compile(r"^(clip|long)_(\d+)(.*)$")


def clip_prefix(is_long: bool) -> str:
    return LONG_PREFIX if is_long else SHORT_PREFIX


def plan_filename(is_long: bool) -> str:
    return "long_clips.json" if is_long else "clips.json"


def clip_name_for(is_long: bool, index: int) -> str:
    return f"{clip_prefix(is_long)}_{index:02d}"


def parse_clip_name(clip_name: str) -> tuple[bool, int] | None:
    """Return ``(is_long, index)`` for names like ``clip_03`` / ``long_00``, or ``None``."""
    match = _CLIP_NAME.match(clip_name)

    if not match:
        return None

    return match.group(1) == LONG_PREFIX, int(match.group(2))


def is_long_clip_name(clip_name: str) -> bool:
    parsed = parse_clip_name(clip_name)
    return bool(parsed and parsed[0])


def migrate_legacy_long_clips(project_dir: str) -> int:
    """
    Rename ``clip_NN*`` files of projects created before the formats were separated.

    Old long-clip projects stored their clips as ``clip_NN`` next to ``long_clips.json``. When a project has
    ``long_clips.json`` but no ``clips.json``, every ``clip_NN*`` file is a long clip and is renamed to
    ``long_NN*`` (also inside ``timestamps.json``), so shorts can be generated later without colliding.

    Returns the number of renamed files.
    """
    clips_dir = os.path.join(project_dir, "clips")

    if not os.path.isdir(clips_dir):
        return 0

    has_long_plan = os.path.exists(os.path.join(project_dir, plan_filename(True)))
    has_short_plan = os.path.exists(os.path.join(project_dir, plan_filename(False)))

    if not has_long_plan or has_short_plan:
        return 0

    renamed = 0

    for file_name in sorted(os.listdir(clips_dir)):
        match = _CLIP_NAME.match(file_name)

        if not match or match.group(1) != SHORT_PREFIX:
            continue

        target = f"{LONG_PREFIX}_{match.group(2)}{match.group(3)}"

        if os.path.exists(os.path.join(clips_dir, target)):
            continue

        os.rename(os.path.join(clips_dir, file_name), os.path.join(clips_dir, target))
        renamed += 1

    timestamps_path = os.path.join(project_dir, "timestamps.json")

    if renamed and os.path.exists(timestamps_path):
        try:
            with open(timestamps_path, "r", encoding="utf-8") as file:
                entries = json.load(file)

            for entry in entries:
                match = _CLIP_NAME.match(str(entry.get("name", "")))

                if match and match.group(1) == SHORT_PREFIX:
                    entry["name"] = f"{LONG_PREFIX}_{match.group(2)}"
                    entry["video_file"] = f"{entry['name']}.mp4" if entry.get("video_file") else None
                    video_path = entry.get("video_path")
                    entry["video_path"] = (
                        os.path.join(os.path.dirname(video_path), f"{entry['name']}.mp4") if video_path else None
                    )
                    details_path = entry.get("details_path")
                    entry["details_path"] = (
                        os.path.join(os.path.dirname(details_path), f"{entry['name']}_details.json")
                        if details_path
                        else details_path
                    )

            with open(timestamps_path, "w", encoding="utf-8") as file:
                json.dump(entries, file, indent=4, ensure_ascii=False)
        except (OSError, ValueError) as exc:
            logger.warning(f"Não foi possível migrar timestamps.json de {project_dir}: {exc}")

    if renamed:
        logger.info(f"Projeto {os.path.basename(project_dir)}: {renamed} arquivos de cortes longos renomeados para long_NN.")

    return renamed


def merge_timestamps(existing: list[dict], generated: list[dict], is_long: bool) -> list[dict]:
    """Replace the entries of the format that was just generated, keeping the other format's entries."""
    prefix = f"{clip_prefix(is_long)}_"
    kept = [entry for entry in existing if not str(entry.get("name", "")).startswith(prefix)]

    return sorted(kept + generated, key=lambda entry: str(entry.get("name", "")))

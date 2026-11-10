"""Command-line entry point (``poetry run start``). The interface lives in ``src/cli``."""

import os
import sys
import warnings
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def main() -> None:
    load_dotenv()

    from cli import main as run_cli

    sys.exit(run_cli())


if __name__ == "__main__":
    main()

import multiprocessing
import os
import sys

# Ensure src is in sys.path
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# The packaged app must have its workspace (models/, assets/, .env, cwd) ready before the heavy
# imports below: the face detector loads its model file at import time.
from src.runtime_setup import prepare_frozen_workspace, resolve_workspace_root

prepare_frozen_workspace(resolve_workspace_root())

from src.gui.app import start_gui

if __name__ == "__main__":
    multiprocessing.freeze_support()
    start_gui(dev_mode=False)

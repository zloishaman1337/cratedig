"""python -m cratedig.gui entry point."""

import sys

from ..config import load_config
from . import run_gui

try:
    sys.exit(run_gui(load_config()))
except ImportError as exc:
    if "PySide6" in str(exc):
        print(
            "PySide6 is required for the GUI. Install with: pip install 'cratedig[gui]'",
            file=sys.stderr,
        )
        sys.exit(1)
    raise

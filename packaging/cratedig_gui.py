"""Frozen GUI entry point.

PyInstaller builds this as the windowed `cratedig` app. The console `cratedig`
CLI keeps its own entry (`cratedig.__main__`); the installed desktop app is
GUI-only.
"""

import sys

from cratedig.config import load_config
from cratedig.gui import run_gui

if __name__ == "__main__":
    sys.exit(run_gui(load_config()))

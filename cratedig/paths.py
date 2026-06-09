"""Runtime path resolution for frozen (PyInstaller) and source runs.

Centralizes three concerns that differ between a normal `python -m` run and an
installed/frozen build:
  * a per-user writable data root (config, db, downloads, saved exports),
  * bundled read-only resource lookup (`schema.sql`, `config.example.toml`),
  * ffmpeg/ffplay executable resolution (bundled copies preferred when frozen).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import platformdirs

APP_NAME = "cratedig"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """Per-user writable data root.

    Win: %APPDATA%\\cratedig, macOS: ~/Library/Application Support/cratedig,
    Linux: ~/.local/share/cratedig.
    """
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False, roaming=True))


def resource_root() -> Path:
    """Root for bundled read-only data files.

    Frozen onedir: `sys._MEIPASS` (the `_internal` folder). Source run: the repo
    root (parent of the `cratedig` package).
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    """Absolute path to a bundled resource by relative name."""
    return resource_root() / name


def _bin_name(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def bundled_binary(name: str) -> str | None:
    """Path to a bundled executable (ffmpeg/ffplay) when frozen, else None."""
    if not is_frozen():
        return None
    exe = _bin_name(name)
    for cand in (
        Path(getattr(sys, "_MEIPASS")) / exe,
        Path(sys.executable).parent / exe,
        Path(getattr(sys, "_MEIPASS")) / "bin" / exe,
    ):
        if cand.is_file():
            return str(cand)
    return None


def ffmpeg_path() -> str | None:
    """Bundled ffmpeg when frozen, else the one on PATH."""
    return bundled_binary("ffmpeg") or shutil.which("ffmpeg")


def ffplay_path() -> str | None:
    """Bundled ffplay when frozen, else the one on PATH."""
    return bundled_binary("ffplay") or shutil.which("ffplay")

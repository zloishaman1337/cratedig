"""Shared helpers for the binary DAW-project parsers."""

from __future__ import annotations

import re
from pathlib import Path

# Hard cap on project file size — real Bitwig/Nuendo projects are well under this.
# Guards against OOM when an arbitrary (possibly hostile) file is opened.
MAX_PROJECT_BYTES = 256 * 1024 * 1024  # 256 MB

# Audio extensions a project may reference as sample/media files.
_AUDIO_EXTS = ("wav", "aiff", "aif", "flac", "mp3", "ogg", "m4a", "wma")
# The filename token is length-bounded ({1,160}) so an adversarial run of valid
# name characters with no extension can't drive pathological regex backtracking.
_AUDIO_RE = re.compile(
    r"[\w .()&'\-]{1,160}\.(?:" + "|".join(_AUDIO_EXTS) + r")\b",
    re.IGNORECASE,
)
_PRINTABLE_RUN = re.compile(rb"[ -~]{3,}")


def read_project_bytes(path: str | Path) -> bytes:
    """Read a project file, refusing anything larger than ``MAX_PROJECT_BYTES``."""
    p = Path(path)
    size = p.stat().st_size
    if size > MAX_PROJECT_BYTES:
        raise ValueError(
            f"project file too large ({size} bytes > {MAX_PROJECT_BYTES} limit)"
        )
    return p.read_bytes()


def extract_sample_basenames(data: bytes) -> list[str]:
    """Return distinct referenced audio file basenames found in a binary blob.

    Scans printable ASCII runs and pulls filename-with-audio-extension tokens.
    Directory prefixes and binary length-prefix bytes (which are non-filename
    characters) are naturally dropped, leaving the basename.
    """
    found: set[str] = set()
    for run in _PRINTABLE_RUN.finditer(data):
        text = run.group().decode("latin1")
        for token in _AUDIO_RE.findall(text):
            name = Path(token.replace("\\", "/")).name.strip()
            if name:
                found.add(name)
    return sorted(found, key=str.lower)


def read_be_string(data: bytes, pos: int) -> tuple[str, int] | None:
    """Read a 4-byte big-endian length-prefixed UTF-8 string at ``pos``.

    Returns (value, next_pos) or None if the length is implausible. Trailing NUL
    and a UTF-8 BOM (stored by some formats) are stripped from the value.
    """
    if pos + 4 > len(data):
        return None
    length = int.from_bytes(data[pos : pos + 4], "big")
    if length <= 0 or length > 4096 or pos + 4 + length > len(data):
        return None
    raw = data[pos + 4 : pos + 4 + length]
    value = raw.decode("utf-8", "ignore").replace("﻿", "").strip("\x00").strip()
    return value, pos + 4 + length

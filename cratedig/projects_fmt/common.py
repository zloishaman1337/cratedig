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


def iter_printable_runs(data: bytes, min_len: int = 4):
    """Yield decoded printable-ASCII runs (length ≥ ``min_len``) from a blob.

    Shared by the best-effort binary scanners (FL Studio / Pro Tools / Logic) that
    recover plugin/sample names from embedded strings rather than a parsed tree.
    """
    pat = re.compile(rb"[ -~]{%d,}" % max(min_len, 1))
    for run in pat.finditer(data):
        yield run.group().decode("latin1")


def resolve_samples_on_disk(
    basenames: list[str], project_path: str | Path, *, max_files: int = 20_000
) -> dict:
    """Split ``basenames`` into found/missing by scanning the project's directory.

    The binary parsers recover only sample *basenames* (no reliable absolute path),
    so existence is checked against the files living next to the project file
    (recursively, bounded by ``max_files`` to keep a hostile/huge tree cheap).
    Returns ``{"found": [...], "missing": [...]}`` in the input order.
    """
    p = Path(project_path).resolve()
    # Bundle formats (Logic .logicx) hand us the package directory itself; scan it.
    # File formats hand us a file; scan the folder it lives in.
    base = p if p.is_dir() else p.parent
    present: set[str] = set()
    if base.is_dir():
        seen = 0
        for p in base.rglob("*"):
            seen += 1
            if seen > max_files:
                break
            if p.is_file():
                present.add(p.name.lower())
    found = [n for n in basenames if n.lower() in present]
    missing = [n for n in basenames if n.lower() not in present]
    return {"found": found, "missing": missing}


def _arrangement_from(bpm, length: str) -> dict | None:
    """Synthesise the panel's ``arrangement`` dict from a best-effort bpm/length.

    The panel renders BPM/Length from this block; binary formats rarely expose a
    bar count, so ``bars`` stays 0 and ``time_str`` defaults to ``0:00`` when only
    a tempo is known.
    """
    if bpm is None and not length:
        return None
    return {
        "beats": 0.0,
        "bars": 0.0,
        "time_str": length or "0:00.00",
        "bpm": round(bpm, 2) if isinstance(bpm, (int, float)) else (bpm or "—"),
    }


def to_checker_data(data: dict, project_path: str | Path) -> dict:
    """Adapt a flat parser result to the rich schema the project-checker panel uses.

    Binary/best-effort formats yield a flat ``{version, plugins, samples, tracks,
    bpm?, length?, key?}``; the panel (shared with the Ableton checker) expects
    ``main``/``arrangement``/``tracks``/``samples{found,missing}``.

    Rich tracks (a non-empty ``tracks`` list of dicts, e.g. from the Reaper/Studio
    One parsers) are passed through unchanged so the Instruments/Plugins/Tracks tabs
    show the real per-track layout. Otherwise plugins are hung on one synthetic
    "Project" track so they still surface in the Plugins tab.
    """
    raw_tracks = data.get("tracks") or []
    plugins = list(data.get("plugins", []))
    if raw_tracks and all(isinstance(t, dict) for t in raw_tracks):
        tracks = raw_tracks
    elif plugins:
        tracks = [{"name": "Project", "type": "audio", "instruments": [], "plugins": plugins}]
    else:
        tracks = []
    version = data.get("version", "")
    return {
        "ableton_version": version,
        "version": version,
        "main": {"fader_db": None, "fader_above_0db": False, "plugins": [], "instruments": []},
        "arrangement": _arrangement_from(data.get("bpm"), data.get("length", "")),
        "bpm": data.get("bpm"),
        "length": data.get("length", ""),
        "key": data.get("key", ""),
        "tracks": tracks,
        "samples": resolve_samples_on_disk(list(data.get("samples", [])), project_path),
    }


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

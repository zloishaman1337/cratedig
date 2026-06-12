"""Best-effort parser for Nuendo / Cubase ``.npr`` project files.

The format is a RIFF-framed tagged binary tree. Each tagged string is stored as
``<4-byte BE name-len><name>\x00 \x08 <4-byte BE value-len><value>``. We do not
reconstruct the full track tree; we recover the plugin/device names ("Plugin
Name" tags) and referenced sample files, which is what the project checker needs.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .common import extract_sample_basenames, read_be_string, read_project_bytes

_VERSION_RE = re.compile(rb"Version (\d+\.\d+(?:\.\d+)?)")
_PLUGIN_NAME_TAG = re.compile(rb"Plugin Name\x00")
# Routing/utility "Plugin Name" values that are not user-facing plugins.
_PLUGIN_DENYLIST = {"standard panner", ""}


def parse_npr(path: str | Path) -> dict:
    """Parse a Nuendo/Cubase .npr into {format, version, plugins, samples, tracks}."""
    data = read_project_bytes(path)
    if data[:4] != b"RIFF":
        raise ValueError("not a Nuendo/Cubase .npr file (missing RIFF header)")
    return {
        "format": "nuendo",
        "version": _version(data),
        "bpm": _tempo(data),
        "plugins": _plugins(data),
        "samples": extract_sample_basenames(data),
        "tracks": [],
    }


def _tempo(data: bytes) -> float | None:
    """Best-effort project tempo from the ``MTempoTrackEvent`` block.

    Nuendo/Cubase store the initial tempo as a big-endian IEEE float a short
    distance after the ``MTempoTrackEvent`` marker. Scan a bounded window for the
    first plausible float.
    """
    i = data.find(b"MTempoTrackEvent")
    if i < 0:
        return None
    window = data[i : i + 96]
    for p in range(len(window) - 4):
        try:
            v = struct.unpack(">f", window[p : p + 4])[0]
        except struct.error:
            continue
        if 20.0 <= v <= 500.0:
            return round(v, 3)
    return None


def _version(data: bytes) -> str:
    app = "Nuendo" if b"Nuendo" in data else ("Cubase" if b"Cubase" in data else "Nuendo")
    m = _VERSION_RE.search(data)
    return f"{app} {m.group(1).decode('ascii', 'ignore')}" if m else app


def _plugins(data: bytes) -> list[str]:
    names: set[str] = set()
    for m in _PLUGIN_NAME_TAG.finditer(data):
        # After "Plugin Name\x00": <pad 0x00><type 0x08><4-byte BE len><value>.
        p = m.end()
        if data[p : p + 2] != b"\x00\x08":
            continue
        result = read_be_string(data, p + 2)
        if result is None:
            continue
        value = result[0]
        if value.lower() not in _PLUGIN_DENYLIST:
            names.add(value)
    return sorted(names, key=str.lower)

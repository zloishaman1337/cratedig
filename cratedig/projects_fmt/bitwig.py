"""Best-effort parser for Bitwig Studio ``.bwproject`` files.

A ``.bwproject`` is a ``BtWg`` header + a length-prefixed metadata/string table
(the project graph) followed by a ZIP tail holding ``plugin-states/*`` presets.
We recover the project version, plugin/device names (with their format, derived
from the file extension in the embedded paths) and referenced sample files.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
from pathlib import Path

from .common import extract_sample_basenames, read_project_bytes

# (basename, extension) pairs in the embedded path/string table.
_PLUGIN_RE = re.compile(r"([\w .()+&'\-]+)\.(vst3|vst|dll|bwdevice)\b", re.IGNORECASE)
_EXT_SUFFIX = {"vst3": "[VST3]", "vst": "[VST2]", "dll": "[VST2]", "bwdevice": ""}
_VERSION_KEY = b"application_version_name"
_PRINTABLE_RUN = re.compile(rb"[ -~]{4,}")


def parse_bwproject(path: str | Path) -> dict:
    """Parse a .bwproject into {format, version, plugins, samples, tracks}."""
    raw = read_project_bytes(path)
    if raw[:4] != b"BtWg":
        raise ValueError("not a Bitwig .bwproject file (missing BtWg header)")
    zip_at = raw.find(b"PK\x03\x04")
    blob = raw if zip_at < 0 else raw[:zip_at]
    return {
        "format": "bitwig",
        "version": _version(raw),
        "bpm": _tempo(blob),
        "plugins": _plugins(blob),
        "samples": extract_sample_basenames(blob),
        "tracks": [],
        "plugin_state_count": _preset_count(raw, zip_at),
    }


def _tempo(blob: bytes) -> float | None:
    """Best-effort project tempo from the ``TEMPO`` automation block.

    Bitwig stores the transport tempo as a big-endian IEEE double tagged ``0x07``
    a short distance after the ``TEMPO`` key (``0x08``-tagged doubles nearby are the
    automation min/max range, not the value). Scan a bounded window for the first
    plausible ``0x07`` double.
    """
    i = blob.find(b"TEMPO")
    if i < 0:
        return None
    window = blob[i + 5 : i + 5 + 256]
    for p in range(len(window) - 9):
        if window[p] != 0x07:
            continue
        try:
            v = struct.unpack(">d", window[p + 1 : p + 9])[0]
        except struct.error:
            continue
        if 20.0 <= v <= 500.0:
            return round(v, 3)
    return None


def _version(raw: bytes) -> str:
    i = raw.find(_VERSION_KEY)
    if i >= 0:
        p = i + len(_VERSION_KEY)
        if raw[p : p + 1] == b"\x08":  # 0x08 = string type marker
            length = int.from_bytes(raw[p + 1 : p + 5], "big")
            if 0 < length <= 64 and p + 5 + length <= len(raw):
                return "Bitwig " + raw[p + 5 : p + 5 + length].decode("utf-8", "ignore")
    return "Bitwig"


def _plugins(blob: bytes) -> list[str]:
    by_name: dict[str, str] = {}
    for run in _PRINTABLE_RUN.finditer(blob):
        text = run.group().decode("latin1")
        for name, ext in _PLUGIN_RE.findall(text):
            name = name.strip()
            if not name:
                continue
            suffix = _EXT_SUFFIX[ext.lower()]
            # Prefer a format-suffixed (3rd-party) label over a bare one.
            if name not in by_name or (suffix and not by_name[name]):
                by_name[name] = suffix
    return sorted(
        (f"{n} {s}".strip() if s else n for n, s in by_name.items()),
        key=str.lower,
    )


def _preset_count(raw: bytes, zip_at: int) -> int:
    if zip_at < 0:
        return 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw[zip_at:]))
        names = zf.namelist()
        # Read-only: we only count central-directory entries (never decompress).
        # Cap the count to bound a forged/zip-bomb central directory.
        if len(names) > 50_000:
            return 0
        return sum(1 for n in names if n.startswith("plugin-states/") and not n.endswith("/"))
    except (zipfile.BadZipFile, OSError):
        return 0

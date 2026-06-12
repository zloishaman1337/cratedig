"""Parser for Logic Pro ``.logicx`` project bundles.

A ``.logicx`` is a macOS package *directory*. The richest, most reliable data
lives in the bundle's property lists: ``MetaData.plist`` exposes tempo, key,
signature, track count and the referenced audio files structurally, and
``ProjectInformation.plist`` carries the saving app version. Third-party AU/VST
plugin names are recovered best-effort from ``ProjectData`` (the component type
4-char codes are stored byte-reversed, e.g. ``aumu`` → ``umua``).
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

from .common import MAX_PROJECT_BYTES

# Reversed AU component 4cc → (suffix, is_instrument). Logic stores them LE.
_AU_TYPE = {b"umua": True, b"xfua": False, b"fmua": False}
_AU_MARKER = re.compile(rb"(umua|xfua|fmua)")
_RUN_RE = re.compile(rb"[\x20-\x7e]{2,48}")
_VERSION_RE = re.compile(r"(Logic Pro[\w .]*?)\s*\(")


def parse_logicx(path: str | Path) -> dict:
    """Parse a .logicx bundle into {format, version, bpm, key, plugins, samples,
    tracks, track_count}."""
    root = Path(path)
    if not root.is_dir():
        raise ValueError("not a Logic .logicx bundle (expected a package directory)")

    alt = _first_alternative(root)
    meta = _read_plist(alt / "MetaData.plist") if alt else {}
    if not meta:
        raise ValueError("not a Logic .logicx bundle (no MetaData.plist found)")
    proj_info = _read_plist(root / "Resources" / "ProjectInformation.plist")

    bpm = meta.get("BeatsPerMinute")
    key = _key(meta)
    samples = _samples(meta)
    instruments, effects = _plugins(alt / "ProjectData") if alt else ([], [])
    track_count = meta.get("NumberOfTracks")

    tracks = []
    if instruments or effects:
        tracks = [{"name": "Project", "type": "audio",
                   "instruments": instruments, "plugins": effects}]

    return {
        "format": "logic",
        "version": _version(proj_info),
        "bpm": round(float(bpm), 3) if isinstance(bpm, (int, float)) else None,
        "key": key,
        "plugins": instruments + effects,
        "samples": samples,
        "tracks": tracks,
        "track_count": int(track_count) if isinstance(track_count, (int, float)) else None,
    }


def _first_alternative(root: Path) -> Path | None:
    alts = root / "Alternatives"
    if not alts.is_dir():
        return None
    for sub in sorted(alts.iterdir()):
        if (sub / "MetaData.plist").is_file():
            return sub
    return None


def _read_plist(p: Path) -> dict:
    try:
        if p.is_file():
            return plistlib.loads(p.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        pass
    return {}


def _key(meta: dict) -> str:
    note = str(meta.get("SongKey", "")).strip()
    gender = str(meta.get("SongGenderKey", "")).strip()
    return f"{note} {gender}".strip()


def _samples(meta: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for field in ("AudioFiles", "PlaybackFiles", "SamplerInstrumentsFiles",
                  "QuicksamplerFiles", "UltrabeatFiles"):
        for entry in meta.get(field, []) or []:
            name = Path(str(entry).replace("\\", "/")).name.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
    return sorted(names, key=str.lower)


def _version(proj_info: dict) -> str:
    saved = str(proj_info.get("LastSavedFrom", "")).strip()
    m = _VERSION_RE.match(saved)
    if m:
        return m.group(1).strip()
    return saved or "Logic Pro"


def _plugins(project_data: Path) -> tuple[list[str], list[str]]:
    """Best-effort 3rd-party AU plugins from ProjectData → (instruments, effects)."""
    try:
        if not project_data.is_file() or project_data.stat().st_size > MAX_PROJECT_BYTES:
            return [], []
        data = project_data.read_bytes()
    except OSError:
        return [], []

    by_name: dict[str, bool] = {}  # name → is_instrument
    for m in _AU_MARKER.finditer(data):
        i = m.start()
        is_instr = _AU_TYPE[m.group(1)]
        # Layout: \x02 NAME \x00 <4-byte manufacturer> <4cc type@i>. The name is the
        # last printable run ending before the manufacturer bytes.
        window = data[max(0, i - 72): i - 4]
        runs = _RUN_RE.findall(window)
        if not runs:
            continue
        name = runs[-1].decode("latin1", "ignore").strip()
        if 2 <= len(name) <= 48:
            # Prefer instrument flag if any occurrence marks it as such.
            by_name[name] = by_name.get(name, False) or is_instr

    instruments = sorted((f"{n} [AU]" for n, ins in by_name.items() if ins), key=str.lower)
    effects = sorted((f"{n} [AU]" for n, ins in by_name.items() if not ins), key=str.lower)
    return instruments, effects

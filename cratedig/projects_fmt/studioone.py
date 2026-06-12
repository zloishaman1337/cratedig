"""Best-effort parser for PreSonus Studio One ``.song`` files.

A ``.song`` is a ZIP. Device/plugin metadata lives in ``Devices/*.xml`` and
``Song/song.xml`` as ``classInfo`` attribute groups
(``name``/``category``/``subCategory``); referenced media live in the
``mediapool.xml`` and as ZIP members. We read only the members we need and never
decompress the whole archive (zip-bomb discipline mirrors ``bitwig.py``).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .common import MAX_PROJECT_BYTES

_MAX_ENTRIES = 50_000
_MAX_MEMBER = 32 * 1024 * 1024  # per-member uncompressed cap for the XML we parse
_AUDIO_EXTS = (".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".m4a")

# A device descriptor tag: <Attributes ... classID="..." name="X" category="Y" subCategory="Z" .../>
_CLASS_TAG = re.compile(r"<Attributes\b[^>]*\bclassID=\"[^\"]*\"[^>]*>", re.DOTALL)
_ATTR = lambda name: re.compile(r'\b%s="([^"]*)"' % name)
_NAME_RE = _ATTR("name")
_CAT_RE = _ATTR("category")
_SUBCAT_RE = _ATTR("subCategory")

_SUFFIX = {"VST2": "[VST2]", "VST3": "[VST3]", "AU": "[AU]", "AUv3": "[AU]"}
_INSTR_CATS = {"AudioSynth", "Instrument"}


def parse_song(path: str | Path) -> dict:
    """Parse a .song into {format, version, bpm, plugins, samples, tracks}."""
    p = Path(path)
    if p.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError("project file too large")
    if not zipfile.is_zipfile(p):
        raise ValueError("not a Studio One .song file (not a ZIP container)")

    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        if len(names) > _MAX_ENTRIES:
            raise ValueError("Studio One .song has an implausible number of entries")

        instruments, effects = _devices(zf, names)
        samples = _samples(zf, names)

    plugins = instruments + effects
    tracks = []
    if instruments or effects:
        tracks = [{"name": "Project", "type": "audio",
                   "instruments": instruments, "plugins": effects}]

    return {
        "format": "studioone",
        "version": "Studio One",
        "bpm": None,  # Studio One stores tempo normalised; not reliably recoverable
        "plugins": plugins,
        "samples": samples,
        "tracks": tracks,
    }


def _read_member(zf: zipfile.ZipFile, name: str) -> str:
    info = zf.getinfo(name)
    if info.file_size > _MAX_MEMBER:
        return ""
    try:
        return zf.read(name).decode("utf-8", "ignore")
    except (OSError, zipfile.BadZipFile):
        return ""


def _devices(zf: zipfile.ZipFile, names: list[str]) -> tuple[list[str], list[str]]:
    instruments: dict[str, None] = {}
    effects: dict[str, None] = {}
    targets = [n for n in names if n.startswith("Devices/") and n.endswith(".xml")]
    targets += [n for n in ("Song/song.xml",) if n in names]
    for member in targets:
        xml = _read_member(zf, member)
        for tag in _CLASS_TAG.findall(xml):
            nm = _NAME_RE.search(tag)
            cat = _CAT_RE.search(tag)
            if not nm or not nm.group(1).strip():
                continue
            name = nm.group(1).strip()
            category = cat.group(1) if cat else ""
            sub = _SUBCAT_RE.search(tag)
            suffix = _SUFFIX.get(sub.group(1) if sub else "", "")
            label = f"{name} {suffix}".strip()
            if category in _INSTR_CATS:
                instruments.setdefault(label)
            else:
                effects.setdefault(label)
    return (sorted(instruments, key=str.lower), sorted(effects, key=str.lower))


def _samples(zf: zipfile.ZipFile, names: list[str]) -> list[str]:
    found: dict[str, None] = {}
    # Audio members carried inside the archive.
    for n in names:
        base = Path(n).name
        if base.lower().endswith(_AUDIO_EXTS):
            found.setdefault(base)
    # External references in the media pool.
    if "Song/mediapool.xml" in names:
        mp = _read_member(zf, "Song/mediapool.xml")
        for m in re.finditer(r'[^"\\/]{1,160}\.(?:wav|aiff?|flac|mp3|ogg|m4a)', mp, re.IGNORECASE):
            found.setdefault(Path(m.group().replace("\\", "/")).name)
    return sorted(found, key=str.lower)

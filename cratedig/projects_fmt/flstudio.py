"""Best-effort parser for FL Studio ``.flp`` project files.

An ``.flp`` is an ``FLhd`` header chunk + an ``FLdt`` event stream. Events are
``<id:byte>[data]`` where the data width is implied by the id: <64 → 1 byte,
64-127 → word, 128-191 → dword, ≥192 → a varint-length text/data blob. We walk
the stream for the version (id 199), tempo (id 66 word / 159 fine dword),
sample file names (id 196) and native FL plugin names (id 201 generators, 203
effects). Wrapped third-party VST names are recovered from the embedded plugin
``.dll``/``.vst3`` paths.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .common import read_project_bytes

_EV_VERSION = 199
_EV_SAMPLE = 196
_EV_GEN = 201   # generator (instrument) plugin display name
_EV_FX = 203    # effect plugin display name
_EV_TEMPO_W = 66       # legacy word tempo (BPM)
_EV_TEMPO_FINE = 159   # fine tempo dword (BPM * 1000)

_AUDIO_RE = re.compile(r"[^\\/:*?\"<>|]{1,160}\.(?:wav|aiff?|flac|mp3|ogg|m4a)\b", re.IGNORECASE)
_VST_PATH_RE = re.compile(r"([\w .()+&'\-]+)\.(vst3|vst|dll)(?![a-z])", re.IGNORECASE)
_VST_SUFFIX = {"vst3": "[VST3]", "vst": "[VST2]", "dll": "[VST2]"}
# The FL host wrapper itself is not a user-facing plugin name.
_GEN_NOISE = {"fruity wrapper"}


def parse_flp(path: str | Path) -> dict:
    """Parse a .flp into {format, version, bpm, plugins, samples, tracks}."""
    raw = read_project_bytes(path)
    if raw[:4] != b"FLhd":
        raise ValueError("not an FL Studio .flp file (missing FLhd header)")
    d = raw.find(b"FLdt")
    if d < 0:
        raise ValueError("not an FL Studio .flp file (missing FLdt chunk)")

    dlen = struct.unpack("<I", raw[d + 4 : d + 8])[0]
    pos = d + 8
    end = min(pos + dlen, len(raw))

    version = "FL Studio"
    bpm: float | None = None
    bpm_fine: float | None = None
    samples: list[str] = []
    seen_s: set[str] = set()
    instruments: list[str] = []
    effects: list[str] = []
    seen_i: set[str] = set()
    seen_e: set[str] = set()

    while pos < end:
        eid = raw[pos]
        pos += 1
        if eid < 64:
            pos += 1
        elif eid < 128:
            if pos + 2 <= end:
                val = struct.unpack("<H", raw[pos : pos + 2])[0]
                if eid == _EV_TEMPO_W and 20 <= val <= 500:
                    bpm = float(val)
            pos += 2
        elif eid < 192:
            if pos + 4 <= end:
                val = struct.unpack("<I", raw[pos : pos + 4])[0]
                if eid == _EV_TEMPO_FINE and 20000 <= val <= 500000:
                    bpm_fine = val / 1000.0
            pos += 4
        else:
            length, pos = _varint(raw, pos, end)
            s = raw[pos : pos + length]
            pos += length
            text = _decode(s)
            if not text:
                continue
            if eid == _EV_VERSION:
                version = f"FL Studio {text}"
            elif eid == _EV_SAMPLE:
                name = Path(text.replace("\\", "/")).name
                if name and name.lower() not in seen_s:
                    seen_s.add(name.lower())
                    samples.append(name)
            elif eid == _EV_GEN and text.lower() not in _GEN_NOISE:
                if text not in seen_i:
                    seen_i.add(text)
                    instruments.append(text)
            elif eid == _EV_FX:
                if text not in seen_e:
                    seen_e.add(text)
                    effects.append(text)

    # Wrapped 3rd-party VSTs from embedded plugin binary paths. Skip names that are
    # already known native FL plugins (their bundled .dll would otherwise duplicate).
    native = {n.lower() for n in instruments + effects}
    for name, suffix in _scan_vst_paths(raw):
        if name.lower() in native:
            continue
        label = f"{name} {suffix}".strip()
        if label not in seen_e and label not in seen_i:
            seen_e.add(label)
            effects.append(label)

    plugins = instruments + effects
    tracks = []
    if instruments or effects:
        tracks = [{"name": "Project", "type": "audio",
                   "instruments": instruments, "plugins": effects}]

    return {
        "format": "flstudio",
        "version": version,
        "bpm": round(bpm_fine if bpm_fine is not None else bpm, 3)
        if (bpm_fine is not None or bpm is not None) else None,
        "plugins": plugins,
        "samples": samples,
        "tracks": tracks,
    }


def _varint(b: bytes, p: int, end: int) -> tuple[int, int]:
    shift = 0
    val = 0
    while p < end:
        c = b[p]
        p += 1
        val |= (c & 0x7F) << shift
        if not c & 0x80:
            break
        shift += 7
    return val, p


def _decode(s: bytes) -> str:
    """FL <11 stores ASCII text events; FL 11+ stores UTF-16-LE."""
    if b"\x00\x00" in s[:4] or (len(s) >= 2 and s[1] == 0):
        return s.decode("utf-16-le", "ignore").split("\x00", 1)[0].strip()
    return s.split(b"\x00", 1)[0].decode("latin1", "ignore").strip()


def _scan_vst_paths(raw: bytes) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for run in re.finditer(rb"[ -~]{6,}", raw):
        text = run.group().decode("latin1")
        for m in _VST_PATH_RE.finditer(text):
            name = Path(m.group(1).replace("\\", "/")).name.strip()
            if name:
                found[name] = _VST_SUFFIX[m.group(2).lower()]
    return sorted(found.items(), key=lambda kv: kv[0].lower())

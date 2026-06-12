"""Parser for Reaper ``.rpp`` / ``.rpp-bak`` project files.

Reaper projects are plain-text S-expressions, so this parser reaches full parity
with the Ableton checker: real per-track instruments/plugins, tempo, and the
referenced media files. Read size-capped via :func:`read_project_bytes`.
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import read_project_bytes

_HEADER_RE = re.compile(r'<REAPER_PROJECT\s+[\d.]+\s+"([^"/]+)')
_TEMPO_RE = re.compile(r"^TEMPO\s+([\d.]+)")
_QUOTED_RE = re.compile(r'"([^"]*)"')
# A plugin opener: <VST "VST3: Serum (Xfer)" "serum.vst3" ... / <AU ... / <CLAP ...
_FX_RE = re.compile(r'<(VST|AU|AUi|CLAP|CLAPi)\s+"([^"]*)"')
_JS_RE = re.compile(r"<JS\s+(\S+)")

_FORMAT_SUFFIX = {"VST3": "[VST3]", "VST3i": "[VST3]", "VST": "[VST2]", "VSTi": "[VST2]"}


def parse_rpp(path: str | Path) -> dict:
    """Parse a .rpp into {format, version, bpm, plugins, samples, tracks}."""
    raw = read_project_bytes(path)
    text = raw.decode("utf-8", "ignore")
    if "<REAPER_PROJECT" not in text:
        raise ValueError("not a Reaper .rpp file (missing <REAPER_PROJECT header)")

    m = _HEADER_RE.search(text)
    version = f"Reaper {m.group(1).strip()}" if m else "Reaper"

    bpm = None
    tracks: list[dict] = []
    cur: dict | None = None
    samples: list[str] = []
    seen_samples: set[str] = set()
    all_plugins: list[str] = []
    seen_plugins: set[str] = set()
    stack: list[str] = []

    def _add_plugin(track: dict | None, label: str, is_instr: bool) -> None:
        if track is None:
            return
        bucket = track["instruments"] if is_instr else track["plugins"]
        if label not in bucket:
            bucket.append(label)
        if label not in seen_plugins:
            seen_plugins.add(label)
            all_plugins.append(label)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line[0] == "<":
            tag = line[1:].split(None, 1)[0]
            stack.append(tag)
            if tag == "TRACK":
                cur = {"name": "Unnamed", "type": "audio", "instruments": [], "plugins": []}
                tracks.append(cur)
                continue
            fx = _FX_RE.match(line)
            if fx and "FXCHAIN" in stack:
                kind, desc, is_instr = _classify_fx(fx.group(1), fx.group(2))
                _add_plugin(cur, _label(desc, kind), is_instr)
                continue
            js = _JS_RE.match(line)
            if js and "FXCHAIN" in stack:
                _add_plugin(cur, Path(js.group(1).strip('"')).name + " [JS]", False)
            continue

        if line == ">":
            if stack:
                stack.pop()
            continue

        if bpm is None:
            tm = _TEMPO_RE.match(line)
            if tm:
                try:
                    bpm = round(float(tm.group(1)), 3)
                except ValueError:
                    pass

        if line.startswith("NAME ") and stack and stack[-1] == "TRACK" and cur is not None:
            q = _QUOTED_RE.search(line)
            if q and q.group(1):
                cur["name"] = q.group(1)
            continue

        if line.startswith("FILE ") and "SOURCE" in stack:
            q = _QUOTED_RE.search(line)
            if q and q.group(1):
                name = Path(q.group(1).replace("\\", "/")).name
                if name and name.lower() not in seen_samples:
                    seen_samples.add(name.lower())
                    samples.append(name)

    return {
        "format": "reaper",
        "version": version,
        "bpm": bpm,
        "plugins": all_plugins,
        "samples": samples,
        "tracks": tracks,
    }


def _classify_fx(tag: str, desc: str) -> tuple[str, str, bool]:
    """Map an FX opener tag + descriptor to (kind, name, is_instrument).

    Reaper VST descriptors carry the format inline, e.g. ``VST3i: Serum (Xfer)``.
    """
    is_instr = tag.endswith("i") or desc.split(":", 1)[0].strip().endswith("i")
    prefix = desc.split(":", 1)[0].strip()
    name = desc.split(":", 1)[1].strip() if ":" in desc else desc.strip()
    if prefix.upper().startswith("VST3"):
        kind = "VST3"
    elif prefix.upper().startswith("VST"):
        kind = "VST"
    elif prefix.upper().startswith("AU"):
        kind = "AU"
    elif prefix.upper().startswith("CLAP"):
        kind = "CLAP"
    else:
        kind = tag.rstrip("i").upper()
    return kind, name, is_instr


def _label(name: str, kind: str) -> str:
    """Strip the trailing vendor parenthetical and append a format suffix."""
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name.strip()
    suffix = _FORMAT_SUFFIX.get(kind, f"[{kind}]")
    return f"{name} {suffix}".strip()

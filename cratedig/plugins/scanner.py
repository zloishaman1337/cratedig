"""Installed-plugin detection: scan plugin folders, match plugin display names.

Pure helpers (``standard_plugin_dirs``, ``normalize_stem``, ``scan_installed``,
``match_name``/``match_installed``) are unit-testable with no I/O beyond walking
the directories passed in. ``load_or_scan`` adds a disk cache keyed by a light
directory signature so a project load reuses a previous scan when nothing on disk
changed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Plugin file / bundle extensions grouped by format. Lowercase, leading dot.
_FORMAT_EXTS: dict[str, tuple[str, ...]] = {
    "vst3": (".vst3",),
    "vst2": (".dll", ".vst"),       # Windows .dll, macOS .vst bundle
    "au": (".component",),
    "aax": (".aaxplugin",),
}
_EXT_TO_FORMAT: dict[str, str] = {
    ext: fmt for fmt, exts in _FORMAT_EXTS.items() for ext in exts
}

# Trailing architecture/bitness noise stripped from a plugin file stem.
_NOISE_RE = re.compile(r"\s*\(?(?:x64|x86|64-?bit|32-?bit|win64|win32)\)?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class InstalledIndex:
    """Normalized set of installed plugin stems plus a per-format breakdown.

    ``signature`` is a light (path, mtime, top-level-count) tuple used to decide
    whether a cached index is still valid without re-walking every bundle.
    """

    stems: frozenset[str]
    by_format: dict[str, frozenset[str]]
    signature: tuple

    def __contains__(self, display_name: str) -> bool:
        return match_name(display_name, self.stems)


def _format_for(name: str) -> str | None:
    low = name.lower()
    for ext, fmt in _EXT_TO_FORMAT.items():
        if low.endswith(ext):
            return fmt
    return None


def normalize_stem(name: str) -> str:
    """Lowercase a plugin file/bundle name, drop its extension and arch noise."""
    base = name
    low = base.lower()
    for ext in _EXT_TO_FORMAT:
        if low.endswith(ext):
            base = base[: -len(ext)]
            break
    base = " ".join(base.split()).strip().lower()
    prev = None
    while prev != base:  # strip possibly-stacked noise tokens ("Foo x64 64-bit")
        prev = base
        base = _NOISE_RE.sub("", base).strip()
    return base


def match_name(name: str, stems) -> bool:
    """True iff ``name`` matches an installed stem (exact, then substring both ways).

    The fuzzy match mirrors the historical ALS plugin matcher: a host display name
    like "FabFilter Pro-Q 3" should match an installed "Pro-Q 3" stem and vice
    versa. This is the single source of truth for both the ALS parser and the
    installed-plugin badges.
    """
    n = name.lower().strip()
    if n in stems:
        return True
    for s in stems:
        if n in s or s in n:
            return True
    return False


def match_installed(display_name: str, index: InstalledIndex) -> bool:
    """True iff a plugin display name resolves to something in the scanned index."""
    return match_name(display_name, index.stems)


def standard_plugin_dirs() -> dict[str, list[Path]]:
    """Standard OS plugin directories per format. Keys are always present; each
    value lists only directories that currently exist on disk."""
    out: dict[str, list[Path]]
    if sys.platform.startswith("win"):
        common = Path(os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files"))
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        out = {
            "vst3": [common / "VST3"],
            "vst2": [pf / "VSTPlugins", pf / "Steinberg" / "VSTPlugins", common / "VST2"],
            "au": [],
            "aax": [common / "Avid" / "Audio" / "Plug-Ins"],
        }
    elif sys.platform == "darwin":
        home = Path.home()
        out = {
            "vst3": [Path("/Library/Audio/Plug-Ins/VST3"), home / "Library/Audio/Plug-Ins/VST3"],
            "vst2": [Path("/Library/Audio/Plug-Ins/VST"), home / "Library/Audio/Plug-Ins/VST"],
            "au": [Path("/Library/Audio/Plug-Ins/Components"), home / "Library/Audio/Plug-Ins/Components"],
            "aax": [Path("/Library/Application Support/Avid/Audio/Plug-Ins")],
        }
    else:  # linux / other
        home = Path.home()
        out = {
            "vst3": [Path("/usr/lib/vst3"), Path("/usr/local/lib/vst3"), home / ".vst3"],
            "vst2": [Path("/usr/lib/vst"), Path("/usr/local/lib/vst"), home / ".vst"],
            "au": [],
            "aax": [],
        }
    return {fmt: [d for d in dirs if d.is_dir()] for fmt, dirs in out.items()}


def all_scan_dirs(custom_dirs=None) -> list[Path]:
    """Flatten standard dirs across formats plus existing custom dirs (deduped)."""
    dirs: list[Path] = []
    for fmt_dirs in standard_plugin_dirs().values():
        dirs.extend(fmt_dirs)
    for c in custom_dirs or []:
        p = Path(c)
        if p.is_dir():
            dirs.append(p)
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _iter_plugins(d: Path):
    """Yield plugin files/bundles directly in ``d`` and one level deep.

    A directory whose name carries a plugin extension (a macOS .vst3/.component
    bundle) is yielded as a single plugin and never descended into.
    """
    try:
        entries = sorted(d.iterdir())
    except OSError:
        return
    for entry in entries:
        if _format_for(entry.name) is not None:
            yield entry
        elif entry.is_dir():
            try:
                subs = sorted(entry.iterdir())
            except OSError:
                continue
            for sub in subs:
                if _format_for(sub.name) is not None:
                    yield sub


def _dirs_signature(dirs) -> tuple:
    """Light signature (path, mtime, top-level count) — cheap cache key, no recursion."""
    sig = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        try:
            mtime = int(d.stat().st_mtime)
            count = sum(1 for _ in d.iterdir())
        except OSError:
            continue
        sig.append((str(d), mtime, count))
    return tuple(sorted(sig))


def scan_installed(dirs) -> InstalledIndex:
    """Walk the given dirs and build a normalized installed-plugin index."""
    stems: set[str] = set()
    by_format: dict[str, set[str]] = {fmt: set() for fmt in _FORMAT_EXTS}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for entry in _iter_plugins(d):
            fmt = _format_for(entry.name)
            if fmt is None:
                continue
            stem = normalize_stem(entry.name)
            if not stem:
                continue
            stems.add(stem)
            by_format[fmt].add(stem)
    return InstalledIndex(
        stems=frozenset(stems),
        by_format={fmt: frozenset(s) for fmt, s in by_format.items()},
        signature=_dirs_signature(dirs),
    )


def _cache_path() -> Path:
    from cratedig.paths import user_data_dir

    return user_data_dir() / "plugin_index.json"


def _load_cache(path: Path) -> InstalledIndex | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return InstalledIndex(
            stems=frozenset(raw["stems"]),
            by_format={fmt: frozenset(v) for fmt, v in raw["by_format"].items()},
            signature=tuple(tuple(item) for item in raw["signature"]),
        )
    except (KeyError, TypeError):
        return None


def _save_cache(path: Path, index: InstalledIndex) -> None:
    payload = {
        "stems": sorted(index.stems),
        "by_format": {fmt: sorted(s) for fmt, s in index.by_format.items()},
        "signature": [list(item) for item in index.signature],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def load_or_scan(custom_dirs=None, force=False, cache_path: Path | None = None) -> InstalledIndex:
    """Return a cached index when the on-disk signature is unchanged, else rescan."""
    dirs = all_scan_dirs(custom_dirs)
    path = cache_path or _cache_path()
    if not force:
        cached = _load_cache(path)
        if cached is not None and cached.signature == _dirs_signature(dirs):
            return cached
    index = scan_installed(dirs)
    _save_cache(path, index)
    return index

"""Pure GUI logic: no Qt, no DB I/O. Safe to import without PySide6."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from cratedig.db.models import Sample
    from cratedig.sources.base import SearchHit
    from cratedig.tui.browser import FolderNode


def similar_name(path: str) -> str:
    """Return '<stem>  ·  <parent dir>' for display in similar-results mode."""
    p = Path(path)
    if p.parent == p:  # filesystem root — no meaningful parent dir
        return p.stem
    return f"{p.stem}  ·  {p.parent}"


def format_metadata(sample, embedded: dict | None) -> list[tuple[str, str]]:
    """Return ordered (label, value) pairs from scan/analyze fields + embedded tags.

    Only fields that are not None/empty are included.
    """
    if sample is None:
        return []
    rows: list[tuple[str, str]] = []

    def _add(label: str, value) -> None:
        if value is not None and value != "":
            rows.append((label, str(value)))

    fmt = getattr(sample, "format", None)
    _add("Format", fmt)

    sr = getattr(sample, "samplerate", None)
    if sr is not None:
        _add("Sample rate", f"{sr} Hz")

    ch = getattr(sample, "channels", None)
    _add("Channels", ch)

    dur = getattr(sample, "duration_sec", None)
    if dur is not None:
        total = int(dur)
        _add("Duration", f"{total // 60}:{total % 60:02d}")

    fsize = getattr(sample, "file_size", None)
    if fsize is not None:
        if fsize >= 1_048_576:
            _add("Size", f"{fsize / 1_048_576:.1f} MB")
        else:
            _add("Size", f"{fsize / 1024:.1f} KB")

    bpm = getattr(sample, "bpm", None)
    if bpm is not None:
        _add("BPM", f"{bpm:.1f}")

    key = getattr(sample, "musical_key", None)
    scale = getattr(sample, "key_scale", None)
    key_parts = [p for p in (key, scale) if p]
    if key_parts:
        _add("Key", " ".join(key_parts))

    loudness = getattr(sample, "loudness_lufs", None)
    if loudness is not None:
        _add("Loudness", f"{loudness:.1f} LUFS")

    _add("Category", getattr(sample, "category", None))
    _add("Class", getattr(sample, "instrument_class", None))
    _add("Source", getattr(sample, "source", None))

    if embedded:
        rows.append(("", ""))
        for key_name, label in (
            ("artist", "Artist"),
            ("title", "Title"),
            ("album", "Album"),
            ("genre", "Genre"),
            ("date", "Year"),
            ("albumartist", "Album Artist"),
            ("tracknumber", "Track"),
        ):
            v = embedded.get(key_name)
            if v:
                _add(label, v)

    return rows


def compute_peaks(samples: np.ndarray, width: int) -> list[tuple[float, float]]:
    """Reduce a 1-D mono float signal to (min, max) peak pairs.

    Non-finite values are dropped first. Returns [] when width <= 0 or the
    cleaned array is empty. Produces exactly min(width, len(clean)) pairs.
    """
    if width <= 0:
        return []

    clean = samples[np.isfinite(samples)]
    if clean.size == 0:
        return []

    n_bins = min(width, len(clean))
    chunks = np.array_split(clean, n_bins)
    return [(float(chunk.min()), float(chunk.max())) for chunk in chunks]


def tree_rows(
    nodes: dict[str, "FolderNode"],
    favorites: list["Sample"],
) -> list[tuple]:
    """Flatten folder tree + favorites into ordered (parent_key, key, label, is_favorites_branch) rows.

    Order: ★ Favorites root + favorite children, then a synthetic Library root
    with every folder node beneath it (root folders reparented under Library),
    mirroring the TUI's Favorites-then-Library layout.
    """
    rows: list[tuple] = [(None, "__favorites__", "★ Favorites", True)]

    for s in favorites:
        rows.append(("__favorites__", f"fav:{s.id}", s.filename, True))

    rows.append((None, "__library__", "Library", False))

    for key in sorted(nodes.keys()):
        node = nodes[key]
        parent = node.parent_key if node.parent_key is not None else "__library__"
        rows.append((parent, node.key, node.name, False))

    return rows


def is_sample_favorite(favorites_by_id: dict, sample_id: int) -> bool:
    """True iff sample_id is a key in the favorites-by-id map."""
    return sample_id in favorites_by_id


def filename_parts(filename: str) -> tuple[str, str]:
    """Return display name without the final suffix and the suffix itself."""
    path = Path(filename)
    return path.stem, path.suffix


def resolve_similar(
    hits: list[tuple[int, float]],
    samples_by_id: dict[int, "Sample | None"],
) -> list["Sample"]:
    """Resolve (sample_id, score) hits to Sample objects in hit order.

    Ids missing from the map or mapped to None (e.g. deleted between the
    similarity query and the fetch) are skipped.
    """
    return [s for sid, _score in hits if (s := samples_by_id.get(sid)) is not None]


def hit_rows(hits: list["SearchHit"]) -> list[tuple[str, str, str, str]]:
    """Flatten search hits into (title, artist, duration, backend) display rows.

    Mirrors the TUI hit table. Duration shows one decimal second, or "-" when
    unknown. Order is preserved so a row index maps back to its hit.
    """
    rows: list[tuple[str, str, str, str]] = []
    for h in hits:
        dur = f"{h.duration_sec:.1f}" if h.duration_sec else "-"
        rows.append((h.title or "", h.artist or "", dur, h.backend or ""))
    return rows

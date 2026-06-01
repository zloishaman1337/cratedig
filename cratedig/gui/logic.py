"""Pure GUI logic: no Qt, no DB I/O. Safe to import without PySide6."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from cratedig.db.models import Sample
    from cratedig.sources.base import SearchHit
    from cratedig.tui.browser import FolderNode


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

    Order: favorites root, favorite children, then folder nodes sorted by key.
    """
    rows: list[tuple] = [(None, "__favorites__", "★ Favorites", True)]

    for s in favorites:
        rows.append(("__favorites__", f"fav:{s.id}", s.filename, True))

    for key in sorted(nodes.keys()):
        node = nodes[key]
        rows.append((node.parent_key, node.key, node.name, False))

    return rows


def is_sample_favorite(favorites_by_id: dict, sample_id: int) -> bool:
    """True iff sample_id is a key in the favorites-by-id map."""
    return sample_id in favorites_by_id


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

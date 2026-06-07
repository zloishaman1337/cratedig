"""Pure GUI logic: no Qt, no DB I/O. Safe to import without PySide6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from cratedig.db.models import Sample
    from cratedig.sources.base import SearchHit
    from cratedig.tui.browser import FolderNode


@dataclass(frozen=True)
class ABState:
    """Immutable model for the A/B audition workflow.

    slot_a / slot_b hold sample IDs (or None when empty).
    current is 'a' or 'b' to indicate which slot is active.
    """

    slot_a: int | None
    slot_b: int | None
    current: str  # 'a' or 'b'

    def active_id(self) -> int | None:
        """Return the ID of the active slot.

        If the current slot is empty but the other slot is filled, return the
        other slot's ID so callers always get a usable value when possible.
        """
        if self.current == 'a':
            return self.slot_a if self.slot_a is not None else self.slot_b
        return self.slot_b if self.slot_b is not None else self.slot_a

    def set_a(self, sample_id: int | None) -> "ABState":
        """Return a new ABState with slot_a updated."""
        return ABState(slot_a=sample_id, slot_b=self.slot_b, current=self.current)

    def set_b(self, sample_id: int | None) -> "ABState":
        """Return a new ABState with slot_b updated."""
        return ABState(slot_a=self.slot_a, slot_b=sample_id, current=self.current)

    def toggle(self) -> tuple["ABState", int]:
        """Flip current a<->b and return (new_state, active_sample_id).

        If the other slot is empty, stay on the filled slot.
        Raises ValueError when both slots are None.
        """
        if self.slot_a is None and self.slot_b is None:
            raise ValueError("Cannot toggle A/B: both slots are empty")

        if self.current == 'a':
            if self.slot_b is not None:
                new_state = ABState(slot_a=self.slot_a, slot_b=self.slot_b, current='b')
                return new_state, self.slot_b
            # B empty — stay on A
            new_state = ABState(slot_a=self.slot_a, slot_b=self.slot_b, current='a')
            return new_state, self.slot_a  # type: ignore[return-value]
        else:
            if self.slot_a is not None:
                new_state = ABState(slot_a=self.slot_a, slot_b=self.slot_b, current='a')
                return new_state, self.slot_a
            # A empty — stay on B
            new_state = ABState(slot_a=self.slot_a, slot_b=self.slot_b, current='b')
            return new_state, self.slot_b  # type: ignore[return-value]


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

    fsize = getattr(sample, "file_size", None)
    if fsize is not None:
        if fsize >= 1_048_576:
            _add("Size", f"{fsize / 1_048_576:.1f} MB")
        else:
            _add("Size", f"{fsize / 1024:.1f} KB")

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
    crates: list | None = None,
    saved: list["Sample"] | None = None,
    saved_root: Path | str | None = None,
) -> list[tuple]:
    """Flatten folder tree + favorites/crates/saved into ordered tree rows.

    Order: favorites, then crates, then a Saved branch (Simpler exports), then a
    synthetic Library root with every folder node beneath it.
    """
    rows: list[tuple] = [(None, "__favorites__", "★ Favorites", True)]

    for s in favorites:
        rows.append(("__favorites__", f"fav:{s.id}", s.filename, True))

    if crates:
        rows.append((None, "__crates__", "📦 Crates", False))
        for crate in crates:
            rows.append(("__crates__", f"crate:{crate.id}", crate.name, False))

    if saved:
        rows.append((None, "__saved__", "💾 Saved", False))
        saved_root_path = Path(saved_root).resolve() if saved_root is not None else None
        date_keys: set[str] = set()
        for s in saved:
            path = Path(s.path)
            parent = path.parent
            label = parent.name
            if saved_root_path is not None:
                try:
                    rel_parent = parent.resolve().relative_to(saved_root_path)
                except (OSError, ValueError):
                    rel_parent = Path(label)
                if rel_parent.parts:
                    label = rel_parent.parts[0]
                else:
                    try:
                        label = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d_%m_%Y")
                    except OSError:
                        label = datetime.now().strftime("%d_%m_%Y")
            date_key = f"saved-dir:{label}"
            if date_key not in date_keys:
                rows.append(("__saved__", date_key, label, False))
                date_keys.add(date_key)

    rows.append((None, "__library__", "Library", False))

    for key in sorted(nodes.keys()):
        node = nodes[key]
        parent = node.parent_key if node.parent_key is not None else "__library__"
        rows.append((parent, node.key, node.name, False))

    return rows


def time_to_x(t: float, width: int, duration: float) -> int:
    """Map a time in seconds to a pixel x in [0, width]."""
    if duration <= 0 or width <= 0:
        return 0
    return int(round(max(0.0, min(1.0, t / duration)) * width))


def x_to_time(x: float, width: int, duration: float) -> float:
    """Map a pixel x to a time in seconds, clamped to [0, duration]."""
    if width <= 0 or duration <= 0:
        return 0.0
    return max(0.0, min(1.0, x / width)) * duration


def clamp_region(
    start: float, end: float, duration: float, min_len: float = 0.01
) -> tuple[float, float]:
    """Clamp a (start, end) region to [0, duration] with a minimum length."""
    start = max(0.0, min(start, duration))
    end = max(0.0, min(end, duration))
    if end < start:
        start, end = end, start
    if end - start < min_len:
        end = min(duration, start + min_len)
        if end - start < min_len:  # start was at the very tail
            start = max(0.0, end - min_len)
    return start, end


def is_sample_favorite(favorites_by_id: dict, sample_id: int) -> bool:
    """True iff sample_id is a key in the favorites-by-id map."""
    return sample_id in favorites_by_id


def filename_parts(filename: str) -> tuple[str, str]:
    """Return display name without the final suffix and the suffix itself."""
    path = Path(filename)
    return path.stem, path.suffix


def file_urls(samples: list["Sample"]) -> list[str]:
    """Return sample paths in input order for local file URL drag payloads."""
    return [s.path for s in samples]


def resolve_similar(
    hits: list[tuple[int, float]],
    samples_by_id: dict[int, "Sample | None"],
) -> list["Sample"]:
    """Resolve (sample_id, score) hits to Sample objects in hit order.

    Ids missing from the map or mapped to None (e.g. deleted between the
    similarity query and the fetch) are skipped.
    """
    return [s for sid, _score in hits if (s := samples_by_id.get(sid)) is not None]


_BACKEND_BADGES: dict[str, tuple[str, str]] = {
    "youtube": ("YT", "#ff0000"),
    "yandex": ("YA", "#ffcc00"),
    "freesound": ("FS", "#00aa44"),
    "archive": ("AR", "#1565c0"),
}
_BADGE_FALLBACK: tuple[str, str] = ("?", "#888888")


def backend_badge(source: str) -> tuple[str, str]:
    """Return (short_label, color_hex) for a download backend name.

    Case-insensitive. Unknown/empty sources return a generic fallback.
    """
    return _BACKEND_BADGES.get(source.lower(), _BADGE_FALLBACK)


def match_als_samples(names: list[str], index: dict) -> dict:
    """Match ALS sample names against the library basename index.

    index maps lowercase-basename → list of sample entries.
    Returns {"found": [...], "candidates": [...], "unresolved": [...]}.
    - found: (name, entry_or_list) — exact case-insensitive basename match
    - candidates: (name, entries_list) — same stem, different extension
    - unresolved: name — no match at all
    """
    found: list = []
    candidates: list = []
    unresolved: list = []

    for name in names:
        key = name.lower()
        if key in index:
            entries = index[key]
            found.append((name, entries[0] if len(entries) == 1 else list(entries)))
        else:
            stem = key.rsplit(".", 1)[0] if "." in key else key
            matched = [v for k, v in index.items() if (k.rsplit(".", 1)[0] if "." in k else k) == stem]
            if matched:
                merged = [entry for entries in matched for entry in entries]
                candidates.append((name, merged))
            else:
                unresolved.append(name)

    return {"found": found, "candidates": candidates, "unresolved": unresolved}


def hit_rows(hits: list["SearchHit"]) -> list[tuple[str, str, str, str, str, str]]:
    """Flatten search hits into display rows.

    Mirrors the TUI hit table. Duration shows one decimal second, or "-" when
    unknown. Order is preserved so a row index maps back to its hit.
    """
    rows: list[tuple[str, str, str, str, str, str]] = []
    for h in hits:
        meta = h.extra.get("metadata", {}) if h.extra else {}
        dur = f"{h.duration_sec:.1f}" if h.duration_sec else "-"
        rows.append((
            meta.get("title") or h.title or "",
            meta.get("artist") or h.artist or "",
            str(meta.get("year") or "-"),
            meta.get("album") or "",
            dur,
            h.backend or "",
        ))
    return rows

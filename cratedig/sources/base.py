"""Downloader plugin contract + registry.

Each backend implements `Downloader`. The manager picks one or falls back across
several. Backends self-register via the @register decorator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DownloadRequest:
    query: str                       # search text OR a URL
    dest_dir: Path
    is_url: bool = False
    extra: dict | None = None


@dataclass
class DownloadResult:
    ok: bool
    source: str
    path: Path | None = None         # downloaded audio file
    source_url: str | None = None
    title: str | None = None
    error: str | None = None


@dataclass
class SearchHit:
    """One search result candidate the user can pick before downloading."""
    backend: str                     # downloader name that produced this hit
    id: str                          # backend-specific id/URL (used by fetch_hit)
    title: str
    artist: str = ""
    duration_sec: float | None = None
    url: str | None = None
    extra: dict = field(default_factory=dict)

    def label(self) -> str:
        dur = f" [{int(self.duration_sec)}s]" if self.duration_sec else ""
        who = f" — {self.artist}" if self.artist else ""
        return f"{self.title}{who}{dur}"

    def preview_url(self) -> str | None:
        """Direct audio URL suitable for quick audition, when a backend has one."""
        preview = self.extra.get("preview") or self.extra.get("preview_url")
        return str(preview) if preview else None


_ILLEGAL = '<>:"/\\|?*'


def safe_filename(title: str, artist: str = "") -> str:
    """Filesystem-safe '<TRACK> - <ARTIST>' stem built from track metadata."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    stem = f"{title} - {artist}" if artist else title
    stem = "".join(c for c in stem if c not in _ILLEGAL and c >= " ")
    stem = " ".join(stem.split()).rstrip(". ")
    return stem[:120] or "track"


def unique_path(dest_dir: Path, stem: str, ext: str) -> Path:
    """Path for stem+ext under dest_dir, suffixing ' (n)' to avoid clobber."""
    if not ext.startswith("."):
        ext = "." + ext
    cand = dest_dir / f"{stem}{ext}"
    n = 2
    while cand.exists():
        cand = dest_dir / f"{stem} ({n}){ext}"
        n += 1
    return cand


REGISTRY: dict[str, type["Downloader"]] = {}


def register(name: str):
    def deco(cls: type["Downloader"]) -> type["Downloader"]:
        cls.name = name
        REGISTRY[name] = cls
        return cls
    return deco


class Downloader(ABC):
    """One audio source backend."""

    name: str = "base"

    def __init__(self, config: dict):
        self.config = config

    def available(self) -> bool:
        """True if this backend is usable (deps present, token set, exe found)."""
        return True

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Return up to `limit` candidate hits for the query. Default: empty."""
        return []

    def fetch_hit(self, hit: SearchHit, dest_dir: Path) -> DownloadResult:
        """Download a specific SearchHit. Default: build a DownloadRequest from hit.url."""
        req = DownloadRequest(
            query=hit.url or hit.id, dest_dir=dest_dir, is_url=bool(hit.url),
        )
        return self.fetch(req)

    @abstractmethod
    def fetch(self, req: DownloadRequest) -> DownloadResult:
        """Download one audio file for the request."""
        raise NotImplementedError

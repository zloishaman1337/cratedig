"""Download orchestration: search, fallback, auto-index.

Modes:
  - "samples" → search FreeSound (sample-oriented backend)
  - "tracks"  → search Yandex; if no results / unavailable, fall back to YouTube
  - "single"  → use one named backend

`fetch_hit` downloads a chosen SearchHit and (optionally) auto-indexes the
resulting file into the samples table with source=<backend>.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import Config
from ..db import Database
from ..scan import index_file
from .base import REGISTRY, DownloadRequest, DownloadResult, Downloader, SearchHit

# Import backends so they register themselves.
from . import youtube, yandex, freesound, archive  # noqa: F401,E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TRACK_FALLBACK = ["yandex", "youtube"]
SAMPLE_BACKENDS = ["freesound"]


class DownloadManager:
    def __init__(self, db: Database, cfg: Config):
        self.db = db
        self.cfg = cfg
        s = cfg.sources
        self.strategy = s.get("strategy", "combined")
        self.default = s.get("default", "youtube")
        self.order = s.get("order", ["youtube", "yandex", "archive"])

    # --- backend instantiation -------------------------------------------------
    def _make(self, name: str) -> Downloader | None:
        cls = REGISTRY.get(name)
        if cls is None:
            return None
        return cls(self.cfg.source(name))

    def available_backends(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for name in REGISTRY:
            dl = self._make(name)
            out[name] = bool(dl and dl.available())
        return out

    # --- search ---------------------------------------------------------------
    def search(self, query: str, mode: str = "tracks", limit: int = 20) -> tuple[list[SearchHit], str]:
        """Search a mode. Returns (hits, used_backend).

        mode "samples": search FreeSound.
        mode "tracks":  try Yandex; if empty/unavailable → YouTube.
        Otherwise (mode == backend name): search just that backend.
        """
        if mode == "samples":
            order = SAMPLE_BACKENDS
        elif mode == "tracks":
            order = TRACK_FALLBACK
        else:
            order = [mode]

        last_err = ""
        for name in order:
            dl = self._make(name)
            if not dl or not dl.available():
                continue
            try:
                hits = dl.search(query, limit=limit)
            except Exception as e:
                last_err = f"{name}: {type(e).__name__}"
                hits = []
            if hits:
                return hits, name
        used = last_err or (order[-1] if order else "")
        return [], used

    # --- download by hit ------------------------------------------------------
    def fetch_hit(
        self,
        hit: SearchHit,
        *,
        auto_index: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> DownloadResult:
        dest = self.cfg.paths.download_dir
        dest.mkdir(parents=True, exist_ok=True)
        dl = self._make(hit.backend)
        if dl is None or not dl.available():
            return DownloadResult(ok=False, source=hit.backend, error="backend unavailable")

        if progress:
            progress(f"downloading [{hit.backend}] {hit.title[:60]}")
        job_id = self._record_start(hit.backend, hit.title, hit.url)
        try:
            res = dl.fetch_hit(hit, dest)
        except Exception as e:
            res = DownloadResult(ok=False, source=hit.backend, error=repr(e))

        sample_id: int | None = None
        if res.ok and res.path and auto_index:
            if progress:
                progress(f"indexing {Path(res.path).name[:60]}")
            try:
                sample_id = index_file(self.db, Path(res.path), source=hit.backend)
            except Exception:
                sample_id = None
        self._record_end(job_id, res, sample_id)
        if progress:
            progress("done" if res.ok else f"error: {res.error}")
        return res

    # --- legacy text/URL path (CLI) -------------------------------------------
    def fetch(self, query: str, *, is_url: bool = False, source: str | None = None,
              auto_index: bool = True) -> DownloadResult:
        dest = self.cfg.paths.download_dir
        dest.mkdir(parents=True, exist_ok=True)
        req = DownloadRequest(query=query, dest_dir=dest, is_url=is_url)

        names = [source] if source else (
            [self.default] if self.strategy == "single" else list(self.order)
        )
        last = DownloadResult(ok=False, source="none", error="no backend tried")
        for name in names:
            dl = self._make(name)
            if dl is None or not dl.available():
                last = DownloadResult(ok=False, source=name or "?", error="backend unavailable")
                continue
            job_id = self._record_start(name, query, query if is_url else None)
            try:
                res = dl.fetch(req)
            except Exception as e:
                res = DownloadResult(ok=False, source=name, error=repr(e))
            sample_id: int | None = None
            if res.ok and res.path and auto_index:
                try:
                    sample_id = index_file(self.db, Path(res.path), source=name)
                except Exception:
                    sample_id = None
            self._record_end(job_id, res, sample_id)
            if res.ok:
                return res
            last = res
        return last

    # --- downloads table bookkeeping ------------------------------------------
    def _record_start(self, source: str, query: str | None, url: str | None) -> int:
        with self.db.lock:
            cur = self.db.conn.execute(
                "INSERT INTO downloads(source, query, source_url, status, requested_at) "
                "VALUES(?,?,?,?,?)",
                (source, query, url, "running", _now()),
            )
            self.db.conn.commit()
            return int(cur.lastrowid)

    def _record_end(self, job_id: int, res: DownloadResult, sample_id: int | None = None) -> None:
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE downloads SET status=?, dest_path=?, source_url=COALESCE(?, source_url), "
                "error=?, completed_at=?, sample_id=COALESCE(?, sample_id) WHERE id=?",
                (
                    "done" if res.ok else "error",
                    str(res.path) if res.path else None,
                    res.source_url,
                    res.error,
                    _now(),
                    sample_id,
                    job_id,
                ),
            )
            self.db.conn.commit()

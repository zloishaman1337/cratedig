"""Yandex Music backend via the `yandex-music` Python library.

Replaces the older yamdl.exe subprocess wrapper (yamdl.exe turned out to be an
interactive TUI app, not a CLI — so it can't be driven headlessly).

Needs an OAuth token (sources.yandex.token, or fall back to token_file path).
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    Downloader, DownloadRequest, DownloadResult, SearchHit,
    register, safe_filename, unique_path,
)


@register("yandex")
class YandexDownloader(Downloader):
    def _token(self) -> str | None:
        t = self.config.get("token")
        if t:
            return t.strip()
        token_file = self.config.get("token_file")
        if token_file and Path(token_file).is_file():
            return Path(token_file).read_text(encoding="utf-8").strip()
        return None

    def _client(self):
        from yandex_music import Client

        token = self._token()
        if not token:
            return None
        try:
            return Client(token).init()
        except Exception:
            return None

    def available(self) -> bool:
        try:
            import yandex_music  # noqa: F401
        except ImportError:
            return False
        return self._token() is not None

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        client = self._client()
        if client is None:
            return []
        try:
            res = client.search(query, type_="track")
        except Exception:
            return []
        if not res or not res.tracks:
            return []
        out: list[SearchHit] = []
        for t in (res.tracks.results or [])[:limit]:
            artist = ", ".join(a.name for a in (t.artists or []))
            tid = f"{t.id}:{t.albums[0].id}" if t.albums else str(t.id)
            out.append(SearchHit(
                backend=self.name,
                id=tid,
                title=t.title or "?",
                artist=artist,
                duration_sec=(t.duration_ms / 1000) if t.duration_ms else None,
                url=f"https://music.yandex.ru/track/{t.id}",
                extra={"track_id": str(t.id)},
            ))
        return out

    def fetch_hit(self, hit: SearchHit, dest_dir: Path) -> DownloadResult:
        client = self._client()
        if client is None:
            return DownloadResult(ok=False, source=self.name, error="no client/token")
        track_id = hit.extra.get("track_id") or hit.id.split(":")[0]
        try:
            tracks = client.tracks([track_id])
        except Exception as e:
            return DownloadResult(ok=False, source=self.name, error=f"track lookup: {e!r}")
        if not tracks:
            return DownloadResult(ok=False, source=self.name, error="track not found")
        track = tracks[0]
        dest = unique_path(dest_dir, safe_filename(hit.title, hit.artist), ".mp3")
        try:
            track.download(str(dest), codec="mp3", bitrate_in_kbps=320)
        except Exception as e:
            return DownloadResult(ok=False, source=self.name, error=f"download: {e!r}")
        return DownloadResult(
            ok=dest.is_file(), source=self.name, path=dest,
            source_url=hit.url, title=f"{hit.artist} — {hit.title}" if hit.artist else hit.title,
        )

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        """Text/URL query path. Picks the top search hit."""
        if req.is_url:
            tid = _extract_track_id(req.query)
            if tid:
                hit = SearchHit(
                    backend=self.name, id=tid, title=f"track {tid}",
                    url=req.query, extra={"track_id": tid},
                )
                return self.fetch_hit(hit, req.dest_dir)
            return DownloadResult(ok=False, source=self.name, error="can't parse track id from URL")
        hits = self.search(req.query, limit=1)
        if not hits:
            return DownloadResult(ok=False, source=self.name, error="no results")
        return self.fetch_hit(hits[0], req.dest_dir)


def _extract_track_id(url: str) -> str | None:
    # https://music.yandex.ru/album/<aid>/track/<tid>  OR  /track/<tid>
    parts = [p for p in url.rstrip("/").split("/") if p]
    if "track" in parts:
        i = parts.index("track")
        if i + 1 < len(parts) and parts[i + 1].isdigit():
            return parts[i + 1]
    return None

"""FreeSound backend — sample-oriented downloads via the FreeSound APIv2.

Needs an API token (sources.freesound.token). Token-only auth allows search and
preview (lo-fi mp3) downloads; full-quality original downloads require OAuth2,
which is out of scope here. Previews are fine for sampling/auditioning.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    Downloader, DownloadRequest, DownloadResult, SearchHit,
    register, safe_filename, unique_path,
)

API = "https://freesound.org/apiv2"


@register("freesound")
class FreeSoundDownloader(Downloader):
    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.config['token']}"}

    def _session(self):
        import requests

        s = requests.Session()
        # System/registry proxies (e.g. a local VPN proxy) reset the TLS
        # handshake to freesound.org; it is reachable directly, so skip them.
        s.trust_env = False
        return s

    def available(self) -> bool:
        if not self.config.get("token"):
            return False
        try:
            import requests  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        import requests

        sess = self._session()
        last_exc: Exception | None = None
        for _ in range(2):  # one retry: connection can still reset transiently
            try:
                r = sess.get(
                    f"{API}/search/text/",
                    params={
                        "query": query,
                        "page_size": limit,
                        "fields": "id,name,username,duration,previews,url",
                    },
                    headers=self._headers(), timeout=30,
                )
                break
            except requests.exceptions.ConnectionError as e:
                last_exc = e
        else:
            raise last_exc  # type: ignore[misc]
        r.raise_for_status()
        hits: list[SearchHit] = []
        for snd in r.json().get("results", []):
            preview = (snd.get("previews") or {}).get("preview-hq-mp3")
            if not preview:
                continue
            hits.append(SearchHit(
                backend=self.name,
                id=str(snd["id"]),
                title=snd.get("name", "?"),
                artist=snd.get("username", ""),
                duration_sec=snd.get("duration"),
                url=snd.get("url"),
                extra={"preview": preview, "id": str(snd["id"])},
            ))
        return hits

    def fetch_hit(self, hit: SearchHit, dest_dir: Path) -> DownloadResult:
        preview = hit.extra.get("preview")
        if not preview:
            return DownloadResult(ok=False, source=self.name, error="no preview url")
        dest = unique_path(dest_dir, safe_filename(hit.title, hit.artist), ".mp3")
        sess = self._session()
        with sess.get(preview, headers=self._headers(), stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(1 << 14):
                    fh.write(chunk)
        return DownloadResult(
            ok=dest.is_file(), source=self.name, path=dest,
            source_url=hit.url, title=hit.title,
        )

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        hits = self.search(req.query, limit=1)
        if not hits:
            return DownloadResult(ok=False, source=self.name, error="no results")
        return self.fetch_hit(hits[0], req.dest_dir)

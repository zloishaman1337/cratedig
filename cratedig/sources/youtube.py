"""YouTube (and any yt-dlp-supported site: Bandcamp, SoundCloud, ...) backend.

Uses yt-dlp as a library. For a search query, uses ytsearch<N>:. If ffmpeg is
available, audio is extracted to the configured format; otherwise yt-dlp keeps
the native bestaudio file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import Downloader, DownloadRequest, DownloadResult, SearchHit, register


@register("youtube")
class YouTubeDownloader(Downloader):
    def available(self) -> bool:
        try:
            import yt_dlp  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        import yt_dlp

        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
        target = f"ytsearch{limit}:{query}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
        hits: list[SearchHit] = []
        for entry in (info.get("entries") or [])[:limit]:
            if not entry:
                continue
            vid = entry.get("id") or entry.get("url")
            url = entry.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else None)
            hits.append(SearchHit(
                backend=self.name,
                id=vid or url or "?",
                title=entry.get("title") or "?",
                artist=entry.get("uploader") or entry.get("channel") or "",
                duration_sec=entry.get("duration"),
                url=url,
            ))
        return hits

    def _opts(self, dest_dir: Path) -> dict:
        fmt = self.config.get("audio_format", "wav")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(dest_dir / "youtube_%(id)s_%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        if fmt not in ("native", "source") and shutil.which("ffmpeg"):
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
            ]
        return opts

    def _run(self, target: str, dest_dir: Path) -> DownloadResult:
        import yt_dlp

        opts = self._opts(dest_dir)
        fmt = self.config.get("audio_format", "wav")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=True)
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title")
            vid = info.get("id")
            url = info.get("webpage_url")
            path = Path(dest_dir) / f"youtube_{vid}_{title}.{fmt}"
            if not path.is_file():
                rd = info.get("requested_downloads") or []
                if rd:
                    path = Path(rd[0].get("filepath", path))
        return DownloadResult(
            ok=path.is_file(), source=self.name, path=path if path.is_file() else None,
            source_url=url, title=title,
            error=None if path.is_file() else "output file not found",
        )

    def fetch_hit(self, hit: SearchHit, dest_dir: Path) -> DownloadResult:
        target = hit.url or hit.id
        return self._run(target, dest_dir)

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        target = req.query if req.is_url else f"ytsearch1:{req.query}"
        return self._run(target, req.dest_dir)

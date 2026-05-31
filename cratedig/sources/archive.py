"""Internet Archive backend — public audio via the `internetarchive` library.

No API key needed for public items. Searches the audio mediatype, picks the
first item, and downloads its first audio file.
"""

from __future__ import annotations

from pathlib import Path

from .base import Downloader, DownloadRequest, DownloadResult, register

_AUDIO_EXT = (".mp3", ".flac", ".wav", ".ogg", ".m4a")


@register("archive")
class ArchiveDownloader(Downloader):
    def available(self) -> bool:
        try:
            import internetarchive  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        import internetarchive as ia

        if req.is_url:
            identifier = req.query.rstrip("/").split("/")[-1]
        else:
            hits = list(
                ia.search_items(f'({req.query}) AND mediatype:audio')
            )
            if not hits:
                return DownloadResult(ok=False, source=self.name, error="no results")
            identifier = hits[0]["identifier"]

        item = ia.get_item(identifier)
        audio_files = [f for f in item.files if f["name"].lower().endswith(_AUDIO_EXT)]
        if not audio_files:
            return DownloadResult(ok=False, source=self.name, error="item has no audio file")

        fname = audio_files[0]["name"]
        item.download(
            files=[fname], destdir=str(req.dest_dir), no_directory=True,
            silent=True, ignore_existing=True,
        )
        path = req.dest_dir / fname
        return DownloadResult(
            ok=path.is_file(), source=self.name, path=path,
            source_url=f"https://archive.org/details/{identifier}", title=identifier,
        )

"""MusicBrainz provider via musicbrainzngs. Read-only recording search."""

from __future__ import annotations

import json

from ..db.models import MetadataRecord
from .base import MetadataProvider, MetadataQuery, register


@register("musicbrainz")
class MusicBrainzProvider(MetadataProvider):
    def available(self) -> bool:
        try:
            import musicbrainzngs  # noqa: F401
            return True
        except ImportError:
            return False

    def lookup(self, sample_id: int, q: MetadataQuery) -> MetadataRecord | None:
        import musicbrainzngs as mb

        ua = self.config.get("musicbrainz_useragent", "sufee@proton.me")
        mb.set_useragent("cratedig", "0.1", ua)
        res = mb.search_recordings(
            recording=q.title or "", artist=q.artist or "", limit=5
        )
        recs = res.get("recording-list", [])
        if not recs:
            return None
        r = recs[0]
        artist = None
        if r.get("artist-credit"):
            artist = r["artist-credit"][0].get("artist", {}).get("name")
        release = _earliest_release(r.get("release-list") or [])
        return MetadataRecord(
            sample_id=sample_id,
            provider=self.name,
            ext_id=r.get("id"),
            artist=artist,
            title=r.get("title"),
            album=release.get("title") if release else None,
            year=_year(release.get("date")) if release else None,
            raw_json=json.dumps(r, ensure_ascii=False),
        )


def _year(date: str | None) -> int | None:
    if not date or len(date) < 4:
        return None
    try:
        return int(date[:4])
    except ValueError:
        return None


def _earliest_release(releases: list[dict]) -> dict | None:
    dated = [(year, rel) for rel in releases if (year := _year(rel.get("date"))) is not None]
    if dated:
        return min(dated, key=lambda item: item[0])[1]
    return releases[0] if releases else None

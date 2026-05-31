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

        ua = self.config.get("musicbrainz_useragent", "cratedig/0.1 (local use)")
        mb.set_useragent("cratedig", "0.1", ua)
        res = mb.search_recordings(
            recording=q.title or "", artist=q.artist or "", limit=1
        )
        recs = res.get("recording-list", [])
        if not recs:
            return None
        r = recs[0]
        artist = None
        if r.get("artist-credit"):
            artist = r["artist-credit"][0].get("artist", {}).get("name")
        return MetadataRecord(
            sample_id=sample_id,
            provider=self.name,
            ext_id=r.get("id"),
            artist=artist,
            title=r.get("title"),
            raw_json=json.dumps(r, ensure_ascii=False),
        )

"""Discogs provider via python-discogs-client. Needs a personal access token."""

from __future__ import annotations

import json

from ..db.models import MetadataRecord
from .base import MetadataProvider, MetadataQuery, register


@register("discogs")
class DiscogsProvider(MetadataProvider):
    def available(self) -> bool:
        if not self.config.get("discogs_token"):
            return False
        try:
            import discogs_client  # noqa: F401
            return True
        except ImportError:
            return False

    def lookup(self, sample_id: int, q: MetadataQuery) -> MetadataRecord | None:
        import discogs_client

        ua = self.config.get("discogs_useragent", "cratedig/0.1")
        client = discogs_client.Client(ua, user_token=self.config["discogs_token"])
        terms = " ".join(t for t in (q.artist, q.title, q.album) if t)
        results = client.search(terms, type="release")
        if not results or len(results) == 0:
            return None
        rel = results[0]
        return MetadataRecord(
            sample_id=sample_id,
            provider=self.name,
            ext_id=str(rel.id),
            artist=", ".join(a.name for a in getattr(rel, "artists", []) or []) or None,
            title=getattr(rel, "title", None),
            album=getattr(rel, "title", None),
            year=getattr(rel, "year", None),
            genre=", ".join(getattr(rel, "genres", []) or []) or None,
            raw_json=json.dumps({"id": rel.id, "title": getattr(rel, "title", None)}),
        )

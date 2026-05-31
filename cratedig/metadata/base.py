"""Metadata-provider contract (MusicBrainz, Discogs).

Providers enrich a sample with artist/title/album/year/genre. They register via
@register and write a `metadata` row through the caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..db.models import MetadataRecord


@dataclass
class MetadataQuery:
    artist: str | None = None
    title: str | None = None
    album: str | None = None


PROVIDERS: dict[str, type["MetadataProvider"]] = {}


def register(name: str):
    def deco(cls: type["MetadataProvider"]) -> type["MetadataProvider"]:
        cls.name = name
        PROVIDERS[name] = cls
        return cls
    return deco


class MetadataProvider(ABC):
    name: str = "base"

    def __init__(self, config: dict):
        self.config = config

    def available(self) -> bool:
        return True

    @abstractmethod
    def lookup(self, sample_id: int, q: MetadataQuery) -> MetadataRecord | None:
        raise NotImplementedError

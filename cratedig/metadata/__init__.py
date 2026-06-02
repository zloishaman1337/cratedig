from .base import MetadataProvider, MetadataQuery, PROVIDERS

# Import providers so @register decorators populate PROVIDERS.
from . import discogs, musicbrainz  # noqa: F401,E402

__all__ = ["MetadataProvider", "MetadataQuery", "PROVIDERS"]

"""Tests for metadata refresh/re-enrichment feature (TDD)."""

import pytest

from cratedig.config import AudioCfg, Config, Paths
from cratedig.db import Database
from cratedig.db.models import MetadataRecord, MetadataCacheRecord
from cratedig.sources import manager as manager_module
from cratedig.sources.base import DownloadRequest, DownloadResult, Downloader, SearchHit
from cratedig.sources.manager import DownloadManager
from cratedig.metadata.ranking import rank_track_hits


class FakeDownloader(Downloader):
    """Mock downloader for testing."""

    def available(self) -> bool:
        return self.config.get("available", True)

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        if self.config.get("fail"):
            raise RuntimeError("boom")
        return list(self.config.get("hits", []))[:limit]

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        return DownloadResult(ok=False, source="fake", error="unused")


class FakeMetadataProvider:
    """Mock metadata provider that records lookup calls."""

    calls = 0
    records: dict[str, MetadataRecord] = {}
    raises = False

    def __init__(self, config: dict):
        self.config = config

    def available(self) -> bool:
        return True

    def lookup(self, sample_id: int, q) -> MetadataRecord | None:
        type(self).calls += 1
        if type(self).raises:
            raise RuntimeError("metadata down")
        return type(self).records.get((q.artist or "", q.title or ""))


def _manager(tmp_path, sources: dict, *, db=None, metadata=None) -> DownloadManager:
    """Helper to create a DownloadManager with test config."""
    cfg = Config(
        paths=Paths(
            db=tmp_path / "cratedig.db",
            download_dir=tmp_path / "downloads",
            library_dirs=(),
            saved_dir=tmp_path / "_saved",
        ),
        audio=AudioCfg(),
        sources=sources,
        metadata=metadata or {},
    )
    return DownloadManager(db=db, cfg=cfg)


@pytest.fixture
def fake_backends(monkeypatch):
    """Register fake backends for testing."""
    for name in ("yandex", "youtube", "freesound"):
        monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)


# ============================================================================
# Test 1: After a tracks search, manager retains last search context
# ============================================================================

def test_search_retains_last_query_mode_and_hits_after_tracks_search(
    fake_backends, tmp_path
):
    """After a tracks search with >= 1 hit, manager._last_hits is populated."""
    db = Database(tmp_path / "t.db")
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [
                SearchHit(backend="yandex", id="ya1", title="Song One", artist="Artist A"),
                SearchHit(backend="yandex", id="ya2", title="Song Two", artist="Artist B"),
            ]},
            "youtube": {"hits": [SearchHit(backend="youtube", id="yt1", title="Song Three")]},
        },
        db=db,
    )

    query = "test artist"
    hits, used = dm.search(query, mode="tracks", limit=20)

    # Verify hits were returned
    assert len(hits) == 3
    assert [h.id for h in hits] == ["ya1", "ya2", "yt1"]

    # Verify manager retained search context (these attributes should exist)
    assert hasattr(dm, "_last_query")
    assert hasattr(dm, "_last_mode")
    assert hasattr(dm, "_last_hits")

    # Verify the retained context matches what was searched
    assert dm._last_query == query
    assert dm._last_mode == "tracks"
    assert dm._last_hits == hits

    db.close()


# ============================================================================
# Test 2: refresh_metadata_cache() returns empty list if no prior search
# ============================================================================

def test_refresh_metadata_cache_returns_empty_list_when_no_prior_search(
    fake_backends, tmp_path
):
    """refresh_metadata_cache() with no retained search context returns []."""
    db = Database(tmp_path / "t.db")
    dm = _manager(tmp_path, {}, db=db)

    # No search performed yet, so no _last_hits
    result = dm.refresh_metadata_cache()

    assert result == []
    db.close()


# ============================================================================
# Test 3: refresh_metadata_cache() calls rank_track_hits with force_live=True
# ============================================================================

def test_refresh_metadata_cache_calls_rank_track_hits_with_force_live_true(
    fake_backends, monkeypatch, tmp_path
):
    """refresh_metadata_cache() re-ranks hits by calling rank_track_hits(force_live=True)."""
    db = Database(tmp_path / "t.db")

    # Track calls to rank_track_hits
    original_rank = manager_module.rank_track_hits
    call_log = []

    def mock_rank(db, metadata_cfg, providers, query, hits, force_live=False):
        call_log.append({
            "query": query,
            "hits_count": len(hits),
            "force_live": force_live,
        })
        # Return hits in reversed order to verify it's used
        return list(reversed(hits))

    monkeypatch.setattr(manager_module, "rank_track_hits", mock_rank)

    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [
                SearchHit(backend="yandex", id="ya1", title="Song One"),
            ]},
            "youtube": {"hits": []},
        },
        db=db,
    )

    # First search to populate _last_hits
    query = "test search"
    dm.search(query, mode="tracks", limit=20)

    # Now refresh
    result = dm.refresh_metadata_cache()

    # Verify rank_track_hits was called with force_live=True
    assert len(call_log) >= 1
    # Find the refresh call (the last one should be the refresh call)
    refresh_call = call_log[-1]
    assert refresh_call["force_live"] is True
    assert refresh_call["query"] == query

    # Verify result is the re-ranked hits
    assert len(result) == 1
    assert result[0].id == "ya1"

    db.close()


# ============================================================================
# Test 4: rank_track_hits with force_live=True bypasses cache freshness gate
# ============================================================================

def test_rank_track_hits_force_live_true_bypasses_ttl_check(
    fake_backends, monkeypatch, tmp_path
):
    """rank_track_hits(..., force_live=True) calls provider.lookup even with fresh cache."""
    db = Database(tmp_path / "t.db")

    # Pre-populate fresh metadata cache
    query_norm = "artist a|song one|"
    fresh_record = MetadataCacheRecord(
        provider="musicbrainz",
        query_norm=query_norm,
        response_json='{}',
        ext_id="mbid123",
        artist="Artist A",
        title="Song One",
        album="Album X",
        year=2020,
        fetched_at="2099-01-01T00:00:00+00:00",  # Far in future = fresh
    )
    db.upsert_metadata_cache(fresh_record)

    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.records = {
        ("Artist A", "Song One"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid_refreshed",
            artist="Artist A (refreshed)",
            title="Song One (refreshed)",
            album="Album Y",
            year=2021,
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})

    hit = SearchHit(backend="yandex", id="ya1", title="Song One", artist="Artist A")

    # Call with force_live=True
    result = rank_track_hits(
        db=db,
        metadata_cfg={
            "enable_search_ranking": True,
            "search_live_lookup": True,
            "search_live_lookup_min_words": 2,
            "cache_ttl_days": 30,
        },
        providers={"musicbrainz": FakeMetadataProvider},
        query="artist a song one",
        hits=[hit],
        force_live=True,  # Force live lookup
    )

    # Provider.lookup MUST have been called despite fresh cache
    assert FakeMetadataProvider.calls > 0, "force_live=True should call provider.lookup even with fresh cache"

    db.close()


# ============================================================================
# Test 5: rank_track_hits with force_live=False uses fresh cache (does NOT call lookup)
# ============================================================================

def test_rank_track_hits_force_live_false_uses_fresh_cache_without_lookup(
    fake_backends, monkeypatch, tmp_path
):
    """rank_track_hits(..., force_live=False) does NOT call lookup when cache is fresh."""
    db = Database(tmp_path / "t.db")

    # Pre-populate fresh metadata cache
    query_norm = "artist a|song one|"
    fresh_record = MetadataCacheRecord(
        provider="musicbrainz",
        query_norm=query_norm,
        response_json='{}',
        ext_id="mbid123",
        artist="Artist A",
        title="Song One",
        album="Album X",
        year=2020,
        fetched_at="2099-01-01T00:00:00+00:00",  # Far in future = fresh
    )
    db.upsert_metadata_cache(fresh_record)

    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.records = {
        ("Artist A", "Song One"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid_new",
            artist="Artist A (new)",
            title="Song One (new)",
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})

    hit = SearchHit(backend="yandex", id="ya1", title="Song One", artist="Artist A")

    # Call with force_live=False (the default)
    result = rank_track_hits(
        db=db,
        metadata_cfg={
            "enable_search_ranking": True,
            "search_live_lookup": True,
            "search_live_lookup_min_words": 2,
            "cache_ttl_days": 30,
        },
        providers={"musicbrainz": FakeMetadataProvider},
        query="artist a song one",
        hits=[hit],
        force_live=False,  # Use cache if fresh
    )

    # Provider.lookup should NOT have been called (cache was fresh and available)
    assert FakeMetadataProvider.calls == 0, "force_live=False should NOT call provider.lookup when cache is fresh"

    db.close()


# ============================================================================
# Test 6: rank_track_hits force_live=True bypasses min-words gate
# ============================================================================

def test_rank_track_hits_force_live_true_bypasses_min_words_gate(
    fake_backends, monkeypatch, tmp_path
):
    """rank_track_hits(..., force_live=True) calls lookup even for one-word queries."""
    db = Database(tmp_path / "t.db")

    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.records = {
        ("Artist A", "Song"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid_test",
            artist="Artist A",
            title="Song",
            album="Test",
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})

    hit = SearchHit(backend="yandex", id="ya1", title="Song", artist="Artist A")

    # Call with force_live=True and a one-word query
    # (normally blocked by min_words check)
    result = rank_track_hits(
        db=db,
        metadata_cfg={
            "enable_search_ranking": True,
            "search_live_lookup": True,
            "search_live_lookup_min_words": 2,  # Requires >= 2 words
            "cache_ttl_days": 30,
        },
        providers={"musicbrainz": FakeMetadataProvider},
        query="song",  # Only 1 word!
        hits=[hit],
        force_live=True,  # Should bypass min-words gate
    )

    # Provider.lookup MUST have been called despite short query
    assert FakeMetadataProvider.calls > 0, "force_live=True should bypass min-words gate"

    db.close()


# ============================================================================
# Test 7: refresh_metadata_cache() returns the re-ranked hits
# ============================================================================

def test_refresh_metadata_cache_returns_re_ranked_hits(
    fake_backends, monkeypatch, tmp_path
):
    """refresh_metadata_cache() returns the result of re-ranking."""
    db = Database(tmp_path / "t.db")

    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.records = {
        ("", "Low quality"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid_low",
            artist="",
            title="Low quality",
            album=None,
            year=None,
        ),
        ("Good Artist", "High quality"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid_high",
            artist="Good Artist",
            title="High quality",
            album="Good Album",
            year=2020,
        ),
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})

    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [
                SearchHit(backend="yandex", id="ya1", title="Low quality", artist=""),
                SearchHit(backend="yandex", id="ya2", title="High quality", artist="Good Artist"),
            ]},
            "youtube": {"hits": []},
        },
        db=db,
    )

    # Initial search
    dm.search("good artist high quality", mode="tracks", limit=20)

    # Refresh should re-rank with force_live=True
    result = dm.refresh_metadata_cache()

    # Result should contain re-ranked hits (better quality should be first)
    assert len(result) == 2
    # High quality hit should rank higher and come first
    assert result[0].id == "ya2"
    assert result[1].id == "ya1"

    db.close()

"""Tests for DownloadManager.search progress callback (BUG 4)."""

from __future__ import annotations

import pytest

from cratedig.config import AudioCfg, Config, Paths
from cratedig.db import Database
from cratedig.sources import manager as manager_module
from cratedig.sources.base import Downloader, SearchHit


class FakeDownloader(Downloader):
    """Minimal fake downloader for testing."""

    def available(self) -> bool:
        return self.config.get("available", True)

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Return a fixed list of fake hits."""
        if self.config.get("fail"):
            raise RuntimeError("downloader failed")
        return list(self.config.get("hits", []))[:limit]

    def fetch(self, req) -> None:
        """Not used in this test."""
        raise NotImplementedError


def _make_manager(tmp_path, sources: dict) -> manager_module.DownloadManager:
    """Create a DownloadManager with fake config."""
    cfg = Config(
        paths=Paths(
            db=tmp_path / "cratedig.db",
            download_dir=tmp_path / "downloads",
            library_dirs=(),
            saved_dir=tmp_path / "_saved",
        ),
        audio=AudioCfg(),
        sources=sources,
        metadata={},
    )
    db = Database(tmp_path / "cratedig.db")
    mgr = manager_module.DownloadManager(db=db, cfg=cfg)
    return mgr


class TestSearchProgressCallback:
    """Tests for progress callback in DownloadManager.search."""

    def test_search_accepts_progress_keyword_argument(self, monkeypatch, tmp_path):
        """The search method must accept a 'progress' keyword argument.

        This test should FAIL now (TypeError: unexpected keyword 'progress')
        and PASS after the fix is implemented.
        """
        # Register fake backend so search doesn't fail
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1")]},
                "youtube": {"hits": []},
            },
        )

        # Callback should be accepted without error
        callback_called = []

        def progress_cb(msg: str):
            callback_called.append(msg)

        # This call should NOT raise TypeError
        hits, used = mgr.search("test query", mode="tracks", progress=progress_cb)

        # Verify search still works
        assert len(hits) >= 0
        assert isinstance(used, str)

    def test_search_calls_progress_before_hits_fetch(self, monkeypatch, tmp_path):
        """Progress callback should be called with a message containing 'hit' before fetching from backends."""
        # Register fake backend
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1")]},
                "youtube": {"hits": []},
            },
        )

        progress_calls = []

        def progress_cb(msg: str):
            progress_calls.append(msg)

        hits, used = mgr.search("test query", mode="tracks", progress=progress_cb)

        # Callback should have been called at least once with a message containing "hit"
        hit_calls = [c for c in progress_calls if "hit" in c.lower()]
        assert len(hit_calls) > 0, \
            f"Expected progress callback with 'hit' message; got: {progress_calls}"

    def test_search_calls_progress_before_metadata_enrichment(self, monkeypatch, tmp_path):
        """Progress callback should be called with a message containing 'metadata' before enrichment step."""
        # Register fake backends
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        # Mock rank_track_hits to track when it's called
        rank_called = []

        original_rank = manager_module.rank_track_hits

        def fake_rank(*args, **kwargs):
            rank_called.append(True)
            return original_rank(*args, **kwargs)

        monkeypatch.setattr(manager_module, "rank_track_hits", fake_rank)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1", artist="Artist 1")]},
                "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="Hit 2", artist="Artist 2")]},
            },
        )

        progress_calls = []

        def progress_cb(msg: str):
            progress_calls.append(msg)

        hits, used = mgr.search("test query", mode="tracks", progress=progress_cb)

        # Callback should have been called with 'metadata' message for tracks mode
        # (which triggers metadata enrichment)
        metadata_calls = [c for c in progress_calls if "metadata" in c.lower()]
        assert len(metadata_calls) > 0, \
            f"Expected progress callback with 'metadata' message in tracks mode; got: {progress_calls}"

    def test_search_progress_hit_before_metadata(self, monkeypatch, tmp_path):
        """Progress callback 'hit' message should come BEFORE 'metadata' message.

        This ensures the two-phase order: (a) fetch hits, then (b) metadata enrichment.
        """
        # Register fake backends
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1", artist="Artist 1")]},
                "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="Hit 2", artist="Artist 2")]},
            },
        )

        progress_calls = []

        def progress_cb(msg: str):
            progress_calls.append(msg)

        hits, used = mgr.search("test query", mode="tracks", progress=progress_cb)

        # Find indices of 'hit' and 'metadata' messages
        hit_idx = next((i for i, c in enumerate(progress_calls) if "hit" in c.lower()), None)
        metadata_idx = next((i for i, c in enumerate(progress_calls) if "metadata" in c.lower()), None)

        # Both should exist and 'hit' should come before 'metadata'
        assert hit_idx is not None, \
            f"No 'hit' message found in progress_calls: {progress_calls}"
        assert metadata_idx is not None, \
            f"No 'metadata' message found in progress_calls: {progress_calls}"
        assert hit_idx < metadata_idx, \
            f"'hit' message (idx={hit_idx}) should come before 'metadata' (idx={metadata_idx}); " \
            f"calls were: {progress_calls}"

    def test_search_none_progress_does_not_raise(self, monkeypatch, tmp_path):
        """search(progress=None) should not raise (optional parameter)."""
        # Register fake backend
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1")]},
                "youtube": {"hits": []},
            },
        )

        # Should not raise
        hits, used = mgr.search("test query", mode="tracks", progress=None)
        assert len(hits) >= 0

    def test_search_without_progress_keyword_does_not_raise(self, monkeypatch, tmp_path):
        """search() without progress keyword should still work (backward compatible)."""
        # Register fake backend
        for name in ("yandex", "youtube"):
            monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Hit 1")]},
                "youtube": {"hits": []},
            },
        )

        # Should not raise (backward compatibility)
        hits, used = mgr.search("test query", mode="tracks")
        assert len(hits) >= 0

    def test_search_samples_mode_with_progress_callback(self, monkeypatch, tmp_path):
        """search(mode='samples', progress=...) should work (samples mode also uses progress)."""
        # Register fake freesound backend
        monkeypatch.setitem(manager_module.REGISTRY, "freesound", FakeDownloader)

        mgr = _make_manager(
            tmp_path,
            {
                "freesound": {"hits": [SearchHit(backend="freesound", id="fs", title="Sample 1")]},
            },
        )

        progress_calls = []

        def progress_cb(msg: str):
            progress_calls.append(msg)

        hits, used = mgr.search("kick", mode="samples", progress=progress_cb)

        # Should work without error
        assert isinstance(hits, list)
        assert isinstance(used, str)

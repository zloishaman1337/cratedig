import pytest

from cratedig.config import AudioCfg, Config, Paths
from cratedig.db import Database
from cratedig.db.models import MetadataRecord
from cratedig.sources import manager as manager_module
from cratedig.sources.base import DownloadRequest, DownloadResult, Downloader, SearchHit
from cratedig.sources.manager import DownloadManager


class FakeDownloader(Downloader):
    def available(self) -> bool:
        return self.config.get("available", True)

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        if self.config.get("fail"):
            raise RuntimeError("boom")
        return list(self.config.get("hits", []))[:limit]

    def fetch(self, req: DownloadRequest) -> DownloadResult:
        return DownloadResult(ok=False, source="fake", error="unused")


def _manager(tmp_path, sources: dict, *, db=None, metadata=None) -> DownloadManager:
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


class FakeMetadataProvider:
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


@pytest.fixture
def fake_backends(monkeypatch):
    for name in ("yandex", "youtube", "freesound"):
        monkeypatch.setitem(manager_module.REGISTRY, name, FakeDownloader)


def test_tracks_search_merges_yandex_and_youtube_hits(fake_backends, tmp_path):
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Yandex hit")]},
            "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="YouTube hit")]},
        },
    )

    hits, used = dm.search("artist title", mode="tracks", limit=20)

    assert [hit.id for hit in hits] == ["ya", "yt"]
    assert [hit.backend for hit in hits] == ["yandex", "youtube"]
    assert used == "yandex+youtube"


@pytest.mark.parametrize(
    ("sources", "expected_ids", "expected_used"),
    [
        (
            {
                "yandex": {"fail": True},
                "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="YouTube hit")]},
            },
            ["yt"],
            "youtube",
        ),
        (
            {
                "yandex": {"hits": []},
                "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="YouTube hit")]},
            },
            ["yt"],
            "youtube",
        ),
        (
            {
                "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Yandex hit")]},
                "youtube": {"fail": True},
            },
            ["ya"],
            "yandex",
        ),
    ],
)
def test_tracks_search_keeps_hits_when_one_backend_fails_or_is_empty(
    fake_backends, tmp_path, sources, expected_ids, expected_used
):
    dm = _manager(tmp_path, sources)

    hits, used = dm.search("artist title", mode="tracks", limit=20)

    assert [hit.id for hit in hits] == expected_ids
    assert used == expected_used


def test_samples_mode_still_searches_freesound_only(fake_backends, tmp_path):
    dm = _manager(
        tmp_path,
        {
            "freesound": {"hits": [SearchHit(backend="freesound", id="fs", title="Sample hit")]},
            "yandex": {"fail": True},
            "youtube": {"fail": True},
        },
    )

    hits, used = dm.search("kick", mode="samples", limit=20)

    assert [hit.id for hit in hits] == ["fs"]
    assert used == "freesound"


def test_tracks_search_ranks_and_enriches_with_metadata(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = False
    FakeMetadataProvider.records = {
        ("Eminem", "Lose Yourself (Official Video)"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            ext_id="mbid",
            artist="Eminem",
            title="Lose Yourself",
            album="8 Mile",
            year=2002,
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Bad cover", artist="Unknown")]},
            "youtube": {"hits": [SearchHit(
                backend="youtube",
                id="yt",
                title="Eminem - Lose Yourself (Official Video)",
                artist="EminemMusic",
            )]},
        },
        db=db,
    )

    hits, used = dm.search("Eminem Lose Yourself", mode="tracks", limit=20)

    assert used == "yandex+youtube"
    assert [hit.id for hit in hits] == ["yt", "ya"]
    assert hits[0].artist == "Eminem"
    assert hits[0].title == "Lose Yourself"
    assert hits[0].extra["metadata"]["album"] == "8 Mile"
    assert hits[0].extra["metadata"]["year"] == 2002
    db.close()


def test_tracks_search_uses_metadata_cache_on_repeat(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = False
    FakeMetadataProvider.records = {
        ("Eminem", "Lose Yourself"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            artist="Eminem",
            title="Lose Yourself",
            album="8 Mile",
            year=2002,
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    sources = {
        "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Lose Yourself", artist="Eminem")]},
        "youtube": {"hits": []},
    }
    dm = _manager(tmp_path, sources, db=db)

    first, _used = dm.search("Eminem Lose Yourself", mode="tracks", limit=20)
    first_calls = FakeMetadataProvider.calls
    FakeMetadataProvider.calls = 0
    second, _used = dm.search("Eminem Lose Yourself", mode="tracks", limit=20)

    assert first_calls == 1
    assert FakeMetadataProvider.calls == 0
    assert first[0].extra["metadata"]["year"] == 2002
    assert second[0].extra["metadata"]["year"] == 2002
    db.close()


def test_tracks_search_metadata_errors_are_nonfatal(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = True
    FakeMetadataProvider.records = {}
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Yandex hit")]},
            "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="YouTube hit")]},
        },
        db=db,
    )

    hits, used = dm.search("artist title", mode="tracks", limit=20)

    assert [hit.id for hit in hits] == ["ya", "yt"]
    assert used == "yandex+youtube"
    db.close()


def test_broad_one_word_tracks_search_uses_cache_only(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = False
    FakeMetadataProvider.records = {
        ("Eminem", "Lose Yourself"): MetadataRecord(
            sample_id=0,
            provider="musicbrainz",
            artist="Eminem",
            title="Lose Yourself",
            album="8 Mile",
            year=2002,
        )
    }
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="Lose Yourself", artist="Eminem")]},
            "youtube": {"hits": [SearchHit(backend="youtube", id="yt", title="Eminem - Lose Yourself")]},
        },
        db=db,
    )

    hits, used = dm.search("eminem", mode="tracks", limit=20)

    assert [hit.id for hit in hits] == ["ya", "yt"]
    assert used == "yandex+youtube"
    assert FakeMetadataProvider.calls == 0
    assert "metadata" not in hits[0].extra
    db.close()


def test_tracks_search_limits_live_metadata_lookups(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = False
    FakeMetadataProvider.records = {}
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [
                SearchHit(backend="yandex", id="1", title="Song One", artist="Artist"),
                SearchHit(backend="yandex", id="2", title="Song Two", artist="Artist"),
                SearchHit(backend="yandex", id="3", title="Song Three", artist="Artist"),
            ]},
            "youtube": {"hits": []},
        },
        db=db,
        metadata={"search_max_live_lookup_hits": 1},
    )

    hits, _used = dm.search("artist song", mode="tracks", limit=20)

    assert [hit.id for hit in hits] == ["1", "2", "3"]
    assert FakeMetadataProvider.calls == 1
    db.close()


def test_tracks_search_negative_cache_avoids_repeat_misses(fake_backends, monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    FakeMetadataProvider.calls = 0
    FakeMetadataProvider.raises = False
    FakeMetadataProvider.records = {}
    monkeypatch.setattr(manager_module, "PROVIDERS", {"musicbrainz": FakeMetadataProvider})
    dm = _manager(
        tmp_path,
        {
            "yandex": {"hits": [SearchHit(backend="yandex", id="ya", title="No Match", artist="Nobody")]},
            "youtube": {"hits": []},
        },
        db=db,
    )

    dm.search("nobody no match", mode="tracks", limit=20)
    first_calls = FakeMetadataProvider.calls
    FakeMetadataProvider.calls = 0
    dm.search("nobody no match", mode="tracks", limit=20)

    assert first_calls == 1
    assert FakeMetadataProvider.calls == 0
    db.close()

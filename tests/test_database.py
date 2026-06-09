import sqlite3
import sys
from types import SimpleNamespace

import numpy as np

from cratedig import index as indexer
from cratedig.audio.features import FEATURE_DIM
from cratedig.db import Database
from cratedig.db.models import MetadataCacheRecord, Sample


def _sample(path: str, **kw) -> Sample:
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


def test_upsert_and_get(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/kick.wav", bpm=120.0, musical_key="A", key_scale="minor"))
    s = db.get_sample(sid)
    assert s and s.filename == "kick.wav" and s.bpm == 120.0
    assert db.count_samples() == 1
    db.close()


def test_get_samples_by_ids_returns_existing_rows_keyed_by_id(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/kick.wav"))
    sid2 = db.upsert_sample(_sample("/a/snare.wav"))

    samples = db.get_samples_by_ids([sid2, 999, sid1, sid2])

    assert set(samples) == {sid1, sid2}
    assert samples[sid1].filename == "kick.wav"
    assert samples[sid2].filename == "snare.wav"
    db.close()


def test_upsert_is_idempotent_on_path(tmp_path):
    db = Database(tmp_path / "t.db")
    a = db.upsert_sample(_sample("/a/x.wav", bpm=100.0))
    b = db.upsert_sample(_sample("/a/x.wav", bpm=140.0))
    assert a == b
    assert db.count_samples() == 1
    assert db.get_sample(a).bpm == 140.0
    db.close()


def test_vector_roundtrip(tmp_path):
    db = Database(tmp_path / "t.db")
    vec = np.arange(8, dtype=np.float32)
    sid = db.upsert_sample(_sample("/a/v.wav"), vector=vec)
    got = db.get_vector(sid)
    assert got is not None and np.allclose(got, vec)
    assert [i for i, _ in db.vectors()] == [sid]
    db.close()


def test_waveform_preview_roundtrip(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/w.wav", waveform_preview="▁▃█▃"))
    assert db.get_sample(sid).waveform_preview == "▁▃█▃"
    db.close()


def test_migration_adds_waveform_preview_to_existing_database(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'local',
            file_hash TEXT,
            format TEXT,
            file_size INTEGER,
            duration_sec REAL,
            samplerate INTEGER,
            channels INTEGER,
            bpm REAL,
            musical_key TEXT,
            key_scale TEXT,
            loudness_lufs REAL,
            category TEXT,
            mood TEXT,
            feature_vector BLOB,
            feature_dim INTEGER,
            analyzed_at TEXT,
            created_at TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        """
    )
    conn.close()

    db = Database(path)
    columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(samples)").fetchall()}
    assert "waveform_preview" in columns
    assert "instrument_class" in columns
    db.close()


def test_analyze_pending_updates_waveform_preview(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"fake")
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample(str(audio)))

    def fake_analyze(path, sr):
        return SimpleNamespace(
            bpm=120.0,
            musical_key="C",
            key_scale="minor",
            loudness_lufs=-12.0,
            waveform_preview="▁▃█▃",
            vector=np.arange(4, dtype=np.float32),
            centroid_norm=0.3,
            zcr=0.1,
        )

    monkeypatch.setattr("cratedig.audio.analyzer.analyze", fake_analyze)
    assert indexer.analyze_pending(db, SimpleNamespace(audio=SimpleNamespace(analysis_sr=22050))) == 1
    sample = db.get_sample(sid)
    assert sample.waveform_preview == "▁▃█▃"
    assert sample.feature_dim == 4
    db.close()


def test_analyze_pending_rebuilds_old_feature_dimensions(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"fake")
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample(str(audio)), vector=np.ones(58, dtype=np.float32))

    def fake_analyze(path, sr):
        return SimpleNamespace(
            bpm=None,
            musical_key=None,
            key_scale=None,
            loudness_lufs=None,
            waveform_preview="▁" * 28,
            vector=np.ones(FEATURE_DIM, dtype=np.float32),
            centroid_norm=0.2,
            zcr=0.05,
        )

    monkeypatch.setattr("cratedig.audio.analyzer.analyze", fake_analyze)
    assert indexer.analyze_pending(db, SimpleNamespace(audio=SimpleNamespace(analysis_sr=22050))) == 1
    assert db.get_sample(sid).feature_dim == FEATURE_DIM
    db.close()


def test_analyze_pending_preserves_existing_category(monkeypatch, tmp_path):
    # Cryptic filename (no keyword) + no audio-derivable class → COALESCE must
    # keep the previously-set category/instrument_class rather than null them.
    audio = tmp_path / "0413.wav"
    audio.write_bytes(b"fake")
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample(str(audio)))
    db.set_classification(sid, "loop", "snare")

    def fake_analyze(path, sr):
        return SimpleNamespace(
            bpm=None, musical_key=None, key_scale=None, loudness_lufs=None,
            waveform_preview="▁", vector=np.ones(FEATURE_DIM, dtype=np.float32),
            centroid_norm=None, zcr=None,
        )

    monkeypatch.setattr("cratedig.audio.analyzer.analyze", fake_analyze)
    indexer.analyze_pending(db, SimpleNamespace(audio=SimpleNamespace(analysis_sr=22050)))
    sample = db.get_sample(sid)
    assert sample.category == "loop"
    assert sample.instrument_class == "snare"
    db.close()


def test_tags(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")
    db.add_tag(sid, "loop")
    db.add_tag(sid, "drums")  # dedup
    assert db.tags_for(sid) == ["drums", "loop"]
    db.close()


def test_migration_adds_source_to_existing_sample_tags(tmp_path):
    path = tmp_path / "old_tags.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'local',
            file_hash TEXT,
            format TEXT,
            file_size INTEGER,
            duration_sec REAL,
            samplerate INTEGER,
            channels INTEGER,
            bpm REAL,
            musical_key TEXT,
            key_scale TEXT,
            loudness_lufs REAL,
            category TEXT,
            instrument_class TEXT,
            mood TEXT,
            waveform_preview TEXT,
            feature_vector BLOB,
            feature_dim INTEGER,
            analyzed_at TEXT,
            created_at TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE sample_tags (
            sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (sample_id, tag_id)
        );
        """
    )
    conn.close()

    db = Database(path)
    columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(sample_tags)").fetchall()}

    assert "source" in columns
    db.close()


def test_auto_tags_do_not_replace_manual_tags(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "manual")

    db.set_auto_tags_for(sid, ["bright", "short"])

    assert db.tags_for(sid) == ["bright", "manual", "short"]

    db.set_auto_tags_for(sid, ["dark"])

    assert db.tags_for(sid) == ["dark", "manual"]
    db.close()


def test_set_tags_for_replaces_only_manual_tags(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "manual")
    db.set_auto_tags_for(sid, ["bright"])

    db.set_tags_for(sid, ["loop"])

    assert db.tags_for(sid) == ["bright", "loop"]
    db.close()


def test_tag_pending_writes_auto_tags_without_manual_overwrite(monkeypatch, tmp_path):
    audio = tmp_path / "bright.wav"
    audio.write_bytes(b"fake")
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(
        _sample(str(audio), analyzed_at="2026-06-02T00:00:00+00:00")
    )
    db.add_tag(sid, "manual")

    sr = 22050
    t = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    y = np.sin(2 * np.pi * 8000.0 * t).astype(np.float32)

    monkeypatch.setitem(
        sys.modules,
        "librosa",
        SimpleNamespace(load=lambda path, sr, mono: (y, sr)),
    )

    assert indexer.tag_pending(db, SimpleNamespace(audio=SimpleNamespace(analysis_sr=sr))) == 1
    assert "manual" in db.tags_for(sid)
    assert "bright" in db.tags_for(sid)
    db.close()


def test_duplicate_samples_group_by_file_hash(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav", file_hash="same"))
    db.upsert_sample(_sample("/b/kick-copy.wav", file_hash="same"))
    db.upsert_sample(_sample("/c/snare.wav", file_hash="unique"))
    db.upsert_sample(_sample("/d/no-hash.wav"))

    dupes = db.duplicate_samples()
    assert [s.filename for s in dupes] == ["kick-copy.wav", "kick.wav"]
    assert {s.file_hash for s in dupes} == {"same"}
    db.close()


def test_classify_pending_updates_missing_categories(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/packs/kicks/kick_01.wav"))
    assert db.get_sample(sid).category is None
    assert db.get_sample(sid).instrument_class is None

    # First call: classify the unclassified sample
    assert indexer.classify_pending(db) == 1
    sample = db.get_sample(sid)
    # kick_01.wav: category is None (kick is not a CATEGORY_KEYWORD)
    # but instrument_class is "kick" (kick IS an INSTRUMENT_KEYWORD)
    assert sample.category is None
    assert sample.instrument_class == "kick"

    # Second call processes nothing: the first pass marked the row
    # classify_attempted=1, so partial rows no longer churn every run.
    assert indexer.classify_pending(db) == 0
    assert db.get_sample(sid).instrument_class == "kick"
    db.close()


def test_metadata_cache_roundtrip(tmp_path):
    db = Database(tmp_path / "t.db")
    record = MetadataCacheRecord(
        provider="musicbrainz",
        query_norm="eminem|lose yourself|",
        ext_id="mbid",
        artist="Eminem",
        title="Lose Yourself",
        album="8 Mile",
        year=2002,
        genre="Hip Hop",
        response_json='{"id":"mbid"}',
    )

    db.upsert_metadata_cache(record)
    cached = db.get_metadata_cache("musicbrainz", "eminem|lose yourself|")

    assert cached is not None
    assert cached.artist == "Eminem"
    assert cached.album == "8 Mile"
    assert cached.year == 2002
    assert cached.fetched_at
    db.close()


def test_stale_metadata_cache_lists_old_entries(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_metadata_cache(MetadataCacheRecord(
        provider="discogs",
        query_norm="a|b|",
        response_json="{}",
        fetched_at="2020-01-01T00:00:00+00:00",
    ))

    stale = db.stale_metadata_cache("2021-01-01T00:00:00+00:00")

    assert [row.query_norm for row in stale] == ["a|b|"]
    db.close()


# --- Favorites ---


def test_add_favorite_folder(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    assert db.is_favorite("folder", "packs/drums") is True
    db.close()


def test_add_favorite_sample(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("sample", "42")
    assert db.is_favorite("sample", "42") is True
    db.close()


def test_is_favorite_returns_false_for_non_favorite(tmp_path):
    db = Database(tmp_path / "t.db")
    assert db.is_favorite("folder", "packs/drums") is False
    db.close()


def test_add_favorite_is_idempotent(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    db.add_favorite("folder", "packs/drums")
    # Should not raise an error and should still have only one row
    rows = db.conn.execute(
        "SELECT COUNT(*) c FROM favorites WHERE kind='folder' AND ref='packs/drums'"
    ).fetchone()
    assert rows["c"] == 1
    db.close()


def test_remove_favorite(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    assert db.is_favorite("folder", "packs/drums") is True
    db.remove_favorite("folder", "packs/drums")
    assert db.is_favorite("folder", "packs/drums") is False
    db.close()


def test_list_favorites_returns_both_kinds(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    db.add_favorite("sample", "42")

    favorites = db.list_favorites()

    assert len(favorites) == 2
    kinds = {f["kind"] for f in favorites}
    assert kinds == {"folder", "sample"}
    refs = {f["ref"] for f in favorites}
    assert refs == {"packs/drums", "42"}
    db.close()


def test_list_favorites_filters_by_kind(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    db.add_favorite("folder", "packs/bass")
    db.add_favorite("sample", "42")

    folder_favs = db.list_favorites(kind="folder")

    assert len(folder_favs) == 2
    assert all(f["kind"] == "folder" for f in folder_favs)
    assert {f["ref"] for f in folder_favs} == {"packs/drums", "packs/bass"}
    db.close()


def test_list_favorites_ordered_by_created_at_then_ref(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "z_last")
    db.add_favorite("folder", "a_first")

    favorites = db.list_favorites(kind="folder")

    assert len(favorites) == 2
    # Should be ordered by created_at then ref
    assert favorites[0]["ref"] == "z_last"
    assert favorites[1]["ref"] == "a_first"
    db.close()


def test_list_favorites_has_required_keys(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")

    favorites = db.list_favorites()

    assert len(favorites) == 1
    fav = favorites[0]
    assert "kind" in fav
    assert "ref" in fav
    assert "created_at" in fav
    db.close()


def test_folders_and_samples_are_independent_favorites(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "X")
    db.add_favorite("sample", "X")

    assert db.is_favorite("folder", "X") is True
    assert db.is_favorite("sample", "X") is True

    db.remove_favorite("folder", "X")

    assert db.is_favorite("folder", "X") is False
    assert db.is_favorite("sample", "X") is True
    db.close()


def test_toggle_favorite_on_non_favorite_returns_true_and_adds(tmp_path):
    db = Database(tmp_path / "t.db")
    result = db.toggle_favorite("folder", "packs/drums")
    assert result is True
    assert db.is_favorite("folder", "packs/drums") is True
    db.close()


def test_toggle_favorite_on_existing_favorite_returns_false_and_removes(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_favorite("folder", "packs/drums")
    assert db.is_favorite("folder", "packs/drums") is True
    result = db.toggle_favorite("folder", "packs/drums")
    assert result is False
    assert db.is_favorite("folder", "packs/drums") is False
    db.close()


def test_toggle_favorite_round_trip(tmp_path):
    db = Database(tmp_path / "t.db")
    result1 = db.toggle_favorite("sample", "42")
    assert result1 is True
    assert db.is_favorite("sample", "42") is True
    result2 = db.toggle_favorite("sample", "42")
    assert result2 is False
    assert db.is_favorite("sample", "42") is False
    result3 = db.toggle_favorite("sample", "42")
    assert result3 is True
    assert db.is_favorite("sample", "42") is True
    db.close()


def test_toggle_favorite_folder_and_sample_kinds_independent(tmp_path):
    db = Database(tmp_path / "t.db")
    db.toggle_favorite("folder", "X")
    assert db.is_favorite("folder", "X") is True
    db.toggle_favorite("sample", "X")
    assert db.is_favorite("sample", "X") is True
    db.toggle_favorite("folder", "X")
    assert db.is_favorite("folder", "X") is False
    assert db.is_favorite("sample", "X") is True
    db.close()


# --- Recent Folders ---


def test_touch_recent_folder_creates_entry(tmp_path):
    db = Database(tmp_path / "t.db")
    db.touch_recent_folder("packs/drums")

    recent = db.list_recent_folders()

    assert len(recent) == 1
    assert recent[0] == "packs/drums"
    db.close()


def test_touch_recent_folder_ordering(tmp_path):
    db = Database(tmp_path / "t.db")
    db.touch_recent_folder("packs/drums")
    db.touch_recent_folder("packs/bass")
    db.touch_recent_folder("packs/synth")

    recent = db.list_recent_folders()

    assert recent[0] == "packs/synth"
    assert recent[1] == "packs/bass"
    assert recent[2] == "packs/drums"
    db.close()


def test_touch_recent_folder_moves_to_front_on_retouch(tmp_path):
    db = Database(tmp_path / "t.db")
    db.touch_recent_folder("packs/drums")
    db.touch_recent_folder("packs/bass")
    db.touch_recent_folder("packs/synth")

    # Re-touch drums, should move to front
    db.touch_recent_folder("packs/drums")

    recent = db.list_recent_folders()

    assert recent[0] == "packs/drums"
    assert recent[1] == "packs/synth"
    assert recent[2] == "packs/bass"
    db.close()


def test_list_recent_folders_default_limit(tmp_path):
    db = Database(tmp_path / "t.db")
    # Add 25 folders
    for i in range(25):
        db.touch_recent_folder(f"path_{i:02d}")

    recent = db.list_recent_folders()

    assert len(recent) == 20
    db.close()


def test_list_recent_folders_keeps_most_recent_20(tmp_path):
    db = Database(tmp_path / "t.db")
    # Add 25 folders
    for i in range(25):
        db.touch_recent_folder(f"path_{i:02d}")

    recent = db.list_recent_folders()

    # Should have exactly 20 rows
    assert len(recent) == 20
    # The most recent should be path_24
    assert recent[0] == "path_24"
    # The oldest of the kept 20 should be path_05
    assert recent[19] == "path_05"
    # path_00 through path_04 should be pruned
    assert "path_00" not in recent
    assert "path_04" not in recent
    db.close()


def test_list_recent_folders_with_custom_limit(tmp_path):
    db = Database(tmp_path / "t.db")
    for i in range(10):
        db.touch_recent_folder(f"path_{i}")

    recent = db.list_recent_folders(limit=5)

    assert len(recent) == 5
    db.close()


def test_touch_recent_folder_upserts(tmp_path):
    db = Database(tmp_path / "t.db")
    db.touch_recent_folder("packs/drums")
    db.touch_recent_folder("packs/bass")
    # Re-touch drums multiple times
    db.touch_recent_folder("packs/drums")
    db.touch_recent_folder("packs/drums")

    recent = db.list_recent_folders()

    # Should still have exactly 2 entries, not 4
    assert len(recent) == 2
    assert recent[0] == "packs/drums"
    db.close()


# --- Remove Tag (new) ---


def test_remove_tag_removes_single_tag(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")
    db.add_tag(sid, "loop")

    db.remove_tag(sid, "drums")

    assert db.tags_for(sid) == ["loop"]
    db.close()


def test_remove_tag_only_removes_association(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/t1.wav"))
    sid2 = db.upsert_sample(_sample("/a/t2.wav"))
    db.add_tag(sid1, "drums")
    db.add_tag(sid2, "drums")

    db.remove_tag(sid1, "drums")

    assert db.tags_for(sid1) == []
    assert db.tags_for(sid2) == ["drums"]
    db.close()


def test_remove_tag_nonexistent_tag_does_not_error(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")

    # Should not raise
    db.remove_tag(sid, "nonexistent")

    assert db.tags_for(sid) == ["drums"]
    db.close()


# --- All Tags (new) ---


def test_all_tags_returns_distinct_sorted(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/t1.wav"))
    sid2 = db.upsert_sample(_sample("/a/t2.wav"))
    db.add_tag(sid1, "drums")
    db.add_tag(sid1, "loop")
    db.add_tag(sid2, "drums")
    db.add_tag(sid2, "sample")

    tags = db.all_tags()

    assert tags == ["drums", "loop", "sample"]
    db.close()


def test_all_tags_empty_database(tmp_path):
    db = Database(tmp_path / "t.db")
    assert db.all_tags() == []
    db.close()


def test_all_tags_single_tag(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")

    assert db.all_tags() == ["drums"]
    db.close()


# --- Set Tags (atomic replace) ---


def test_set_tags_for_replaces_existing(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")
    db.add_tag(sid, "loop")

    db.set_tags_for(sid, ["kick", "drums"])

    assert db.tags_for(sid) == ["drums", "kick"]
    db.close()


def test_set_tags_for_empty_clears_all(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")

    db.set_tags_for(sid, [])

    assert db.tags_for(sid) == []
    db.close()


def test_set_tags_for_dedups(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))

    db.set_tags_for(sid, ["loop", "loop", "drums"])

    assert db.tags_for(sid) == ["drums", "loop"]
    db.close()


def test_set_tags_for_only_affects_target_sample(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/t1.wav"))
    sid2 = db.upsert_sample(_sample("/a/t2.wav"))
    db.add_tag(sid2, "snare")

    db.set_tags_for(sid1, ["kick"])

    assert db.tags_for(sid1) == ["kick"]
    assert db.tags_for(sid2) == ["snare"]
    db.close()


# --- Delete Sample (new) ---


def test_delete_sample_removes_from_count(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    assert db.count_samples() == 1

    db.delete_sample(sid)

    assert db.count_samples() == 0
    assert db.get_sample(sid) is None
    db.close()


def test_delete_sample_cascades_tags(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")
    db.add_tag(sid, "loop")

    db.delete_sample(sid)

    assert db.tags_for(sid) == []
    db.close()


def test_delete_sample_removes_favorite_entry(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_favorite("sample", str(sid))
    assert db.is_favorite("sample", str(sid)) is True

    db.delete_sample(sid)

    assert db.is_favorite("sample", str(sid)) is False
    db.close()


def test_delete_sample_does_not_affect_other_samples(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/t1.wav"))
    sid2 = db.upsert_sample(_sample("/a/t2.wav"))
    db.add_tag(sid1, "drums")
    db.add_tag(sid2, "snare")

    db.delete_sample(sid1)

    assert db.count_samples() == 1
    assert db.get_sample(sid2) is not None
    assert db.tags_for(sid2) == ["snare"]
    db.close()


# --- Crates ---


def test_create_crate_and_list_sorted(tmp_path):
    db = Database(tmp_path / "t.db")

    drums = db.create_crate("Drums")
    bass = db.create_crate("Bass")

    crates = db.list_crates()

    assert [c.name for c in crates] == ["Bass", "Drums"]
    assert {c.id for c in crates} == {drums, bass}
    db.close()


def test_create_crate_is_idempotent_by_name(tmp_path):
    db = Database(tmp_path / "t.db")

    first = db.create_crate("Ideas")
    second = db.create_crate("Ideas")

    assert first == second
    assert len(db.list_crates()) == 1
    db.close()


def test_add_to_crate_lists_samples_in_insert_order(tmp_path):
    db = Database(tmp_path / "t.db")
    sid1 = db.upsert_sample(_sample("/a/kick.wav"))
    sid2 = db.upsert_sample(_sample("/a/snare.wav"))
    crate_id = db.create_crate("Breaks")

    db.add_to_crate(crate_id, sid2)
    db.add_to_crate(crate_id, sid1)
    db.add_to_crate(crate_id, sid2)

    assert [s.id for s in db.crate_samples(crate_id)] == [sid2, sid1]
    db.close()


def test_remove_from_crate_only_removes_membership(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/kick.wav"))
    crate_id = db.create_crate("Keepers")
    db.add_to_crate(crate_id, sid)

    db.remove_from_crate(crate_id, sid)

    assert db.crate_samples(crate_id) == []
    assert db.get_sample(sid) is not None
    db.close()


def test_delete_sample_removes_crate_membership(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/kick.wav"))
    crate_id = db.create_crate("Keepers")
    db.add_to_crate(crate_id, sid)

    db.delete_sample(sid)

    assert db.crate_samples(crate_id) == []
    db.close()


# --- Update Sample Location (new) ---


def test_update_sample_location_updates_path_and_filename(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/old/path/kick.wav"))

    db.update_sample_location(sid, "/new/path", "new_kick.wav")

    sample = db.get_sample(sid)
    assert sample.path == "/new/path"
    assert sample.filename == "new_kick.wav"
    db.close()


def test_update_sample_location_preserves_other_fields(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/old/path/kick.wav", bpm=120.0, musical_key="C"))

    db.update_sample_location(sid, "/new/path", "new_kick.wav")

    sample = db.get_sample(sid)
    assert sample.bpm == 120.0
    assert sample.musical_key == "C"
    db.close()


def test_update_sample_location_keeps_id_unchanged(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/old/path/kick.wav"))

    db.update_sample_location(sid, "/new/path", "new_kick.wav")

    sample = db.get_sample(sid)
    assert sample.id == sid
    db.close()


# --- BUG C: classify_pending churn and COALESCE tests (failing) ---


def test_classify_pending_churn_reselects_unrecognizable_every_run(tmp_path):
    """Bug C.1: classify_pending re-processes NULL-class rows every run (no attempt marker).

    Current behavior: a sample with an unrecognizable filename (e.g., 'xyzzy_random_1234.wav')
    has category=NULL and instrument_class=NULL after the first run. On the second run,
    the WHERE clause includes "instrument_class IS NULL", so the row is re-selected and
    updated again (idempotent, but wasteful churn).

    After the fix: a `classify_attempted` column (INTEGER DEFAULT 0 on samples table) is set
    to 1 after each attempt. The WHERE clause excludes attempted rows, so the second run
    returns 0 (no rows to update).

    This test should FAIL (red) with the current code because the second call returns 1+.
    """
    db = Database(tmp_path / "t.db")

    # Insert a sample with a completely unrecognizable filename
    unrecognizable_path = "/packs/xyzzy_random_1234.wav"
    sid = db.upsert_sample(_sample(unrecognizable_path))

    # Verify it starts unclassified
    sample = db.get_sample(sid)
    assert sample.category is None
    assert sample.instrument_class is None

    # First run: attempt to classify
    count1 = indexer.classify_pending(db)
    assert count1 == 1, "First run should process 1 row"

    # Verify after first run: still None (unrecognizable)
    sample = db.get_sample(sid)
    assert sample.category is None
    assert sample.instrument_class is None

    # Second run: THIS SHOULD RETURN 0 (row marked attempted, not re-selected)
    # With the current bug, this returns 1 or more (row re-selected and re-updated).
    count2 = indexer.classify_pending(db)
    assert count2 == 0, \
        f"FAIL: second run should return 0 (row marked attempted); got {count2}"

    db.close()


def test_classify_pending_coalesce_preserves_existing_class(tmp_path):
    """Bug C.2: UPDATE statement lacks COALESCE, so a good existing class gets nulled.

    Current behavior: if a sample has an unrecognizable filename but instrument_class
    is already set to a good value (e.g., 'kick'), the UPDATE statement overwrites it
    with NULL (because classify_instrument returns None for the bad filename).

    After the fix: the UPDATE uses COALESCE(..., column) so that a previously-set good
    value is never nulled by a None classification attempt.

    This test should FAIL (red) with the current code because the class gets nulled.
    """
    db = Database(tmp_path / "t.db")

    # Insert a sample with an unrecognizable filename
    unrecognizable_path = "/packs/xyzzy_random_5678.wav"
    sid = db.upsert_sample(_sample(unrecognizable_path))

    # Manually set a good instrument_class value via SQL
    with db.lock:
        db.conn.execute(
            "UPDATE samples SET instrument_class=? WHERE id=?",
            ("kick", sid),
        )
        db.conn.commit()

    # Verify it's set
    sample = db.get_sample(sid)
    assert sample.instrument_class == "kick", "Initial class should be 'kick'"

    # Run classify_pending: it will try to classify the unrecognizable filename,
    # get None, and (with the bug) overwrite the good 'kick' value with NULL.
    indexer.classify_pending(db)

    # After the fix, instrument_class should REMAIN 'kick' (COALESCE preserves it)
    # With the bug, it becomes NULL.
    sample = db.get_sample(sid)
    assert sample.instrument_class == "kick", \
        f"FAIL: instrument_class should be preserved as 'kick'; got {sample.instrument_class}"

    db.close()

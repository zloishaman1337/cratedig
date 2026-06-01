import sqlite3
from types import SimpleNamespace

import numpy as np

from cratedig import index as indexer
from cratedig.audio.features import FEATURE_DIM
from cratedig.db import Database
from cratedig.db.models import Sample


def _sample(path: str, **kw) -> Sample:
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


def test_upsert_and_get(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/kick.wav", bpm=120.0, musical_key="A", key_scale="minor"))
    s = db.get_sample(sid)
    assert s and s.filename == "kick.wav" and s.bpm == 120.0
    assert db.count_samples() == 1
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
        )

    monkeypatch.setattr("cratedig.audio.analyzer.analyze", fake_analyze)
    assert indexer.analyze_pending(db, SimpleNamespace(audio=SimpleNamespace(analysis_sr=22050))) == 1
    assert db.get_sample(sid).feature_dim == FEATURE_DIM
    db.close()


def test_tags(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/a/t.wav"))
    db.add_tag(sid, "drums")
    db.add_tag(sid, "loop")
    db.add_tag(sid, "drums")  # dedup
    assert db.tags_for(sid) == ["drums", "loop"]
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

    assert indexer.classify_pending(db) == 1
    assert db.get_sample(sid).category == "kick"
    assert indexer.classify_pending(db) == 0
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

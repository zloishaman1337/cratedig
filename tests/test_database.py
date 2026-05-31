import numpy as np

from cratedig import index as indexer
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

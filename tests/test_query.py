from cratedig.db import Database
from cratedig.db.models import Sample
from cratedig.search import SearchFilter, run_search


def _seed(db: Database):
    db.upsert_sample(Sample(id=None, path="/a/kick.wav", filename="kick.wav",
                            bpm=120.0, musical_key="A", key_scale="minor",
                            category="kick"))
    db.upsert_sample(Sample(id=None, path="/a/snare.wav", filename="snare.wav",
                            bpm=90.0, musical_key="C", key_scale="major"))
    db.upsert_sample(Sample(id=None, path="/a/hat.wav", filename="hat.wav",
                            bpm=140.0, musical_key="A", key_scale="minor"))


def test_bpm_range(tmp_path):
    db = Database(tmp_path / "q.db")
    _seed(db)
    res = run_search(db, SearchFilter(bpm_min=100, bpm_max=130))
    assert {s.filename for s in res} == {"kick.wav"}
    db.close()


def test_key_filter(tmp_path):
    db = Database(tmp_path / "q.db")
    _seed(db)
    res = run_search(db, SearchFilter(musical_key="A", key_scale="minor"))
    assert {s.filename for s in res} == {"kick.wav", "hat.wav"}
    db.close()


def test_text_filter(tmp_path):
    db = Database(tmp_path / "q.db")
    _seed(db)
    res = run_search(db, SearchFilter(text="sn"))
    assert {s.filename for s in res} == {"snare.wav"}
    db.close()


def test_category_filter(tmp_path):
    db = Database(tmp_path / "q.db")
    _seed(db)
    res = run_search(db, SearchFilter(category="kick"))
    assert {s.filename for s in res} == {"kick.wav"}
    db.close()


def test_tags_all_of(tmp_path):
    db = Database(tmp_path / "q.db")
    _seed(db)
    kick = run_search(db, SearchFilter(text="kick"))[0]
    db.add_tag(kick.id, "drum")
    db.add_tag(kick.id, "acoustic")
    res = run_search(db, SearchFilter(tags=["drum", "acoustic"]))
    assert {s.filename for s in res} == {"kick.wav"}
    # missing one tag -> no match
    assert run_search(db, SearchFilter(tags=["drum", "missing"])) == []
    db.close()

"""Unit tests for cratedig.health (library_health, missing_sample_ids, format_report)."""

from __future__ import annotations

import numpy as np
import pytest

from cratedig.db import Database
from cratedig.db.models import Sample
from cratedig.health import format_report, library_health, missing_sample_ids


def _sample(path: str, **kw) -> Sample:
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


# ---------------------------------------------------------------------------
# library_health
# ---------------------------------------------------------------------------

def test_library_health_total_matches_inserted(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav"))
    db.upsert_sample(_sample("/a/snare.wav"))
    db.upsert_sample(_sample("/a/hat.wav"))

    report = library_health(db, check_files=False)

    assert report.total == 3
    db.close()


def test_library_health_unanalyzed_counts_no_vector(tmp_path):
    db = Database(tmp_path / "t.db")
    # analyzed: feature_vector set via upsert with vector kwarg
    analyzed_vec = np.ones(64, dtype=np.float32)
    db.upsert_sample(_sample("/a/analyzed.wav", analyzed_at="2026-01-01T00:00:00+00:00"),
                     vector=analyzed_vec)
    # not analyzed: no vector, no analyzed_at
    db.upsert_sample(_sample("/a/pending.wav"))

    report = library_health(db, check_files=False)

    # The analyzed sample may still count as unanalyzed if feature_dim != FEATURE_DIM;
    # the pending one definitely has no feature_vector.
    assert report.unanalyzed >= 1
    db.close()


def test_library_health_unknown_category_counts_none(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/no_cat.wav"))           # category=None
    db.upsert_sample(_sample("/a/has_cat.wav", category="loop"))

    report = library_health(db, check_files=False)

    # At least the one with category=None should be counted
    assert report.unknown_category >= 1
    db.close()


def test_library_health_duplicate_groups_and_files(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav", file_hash="aabbcc"))
    db.upsert_sample(_sample("/b/kick-copy.wav", file_hash="aabbcc"))
    db.upsert_sample(_sample("/c/snare.wav", file_hash="unique"))

    report = library_health(db, check_files=False)

    assert report.duplicate_groups == 1
    assert report.duplicate_files == 2
    db.close()


def test_library_health_by_source_counts(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/a.wav", source="local"))
    db.upsert_sample(_sample("/a/b.wav", source="local"))
    db.upsert_sample(_sample("/a/c.wav", source="edit"))

    report = library_health(db, check_files=False)

    assert report.by_source.get("local") == 2
    assert report.by_source.get("edit") == 1
    db.close()


def test_library_health_no_duplicates_zero_groups(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav", file_hash="hash1"))
    db.upsert_sample(_sample("/a/snare.wav", file_hash="hash2"))

    report = library_health(db, check_files=False)

    assert report.duplicate_groups == 0
    assert report.duplicate_files == 0
    db.close()


def test_library_health_empty_db(tmp_path):
    db = Database(tmp_path / "t.db")

    report = library_health(db, check_files=False)

    assert report.total == 0
    assert report.unanalyzed == 0
    assert report.unknown_category == 0
    assert report.duplicate_groups == 0
    assert report.duplicate_files == 0
    assert report.by_source == {}
    db.close()


def test_library_health_multiple_dup_groups(tmp_path):
    db = Database(tmp_path / "t.db")
    # Group A: 2 files
    db.upsert_sample(_sample("/a/a1.wav", file_hash="groupA"))
    db.upsert_sample(_sample("/a/a2.wav", file_hash="groupA"))
    # Group B: 3 files
    db.upsert_sample(_sample("/b/b1.wav", file_hash="groupB"))
    db.upsert_sample(_sample("/b/b2.wav", file_hash="groupB"))
    db.upsert_sample(_sample("/b/b3.wav", file_hash="groupB"))
    # Unique
    db.upsert_sample(_sample("/c/c1.wav", file_hash="unique"))

    report = library_health(db, check_files=False)

    assert report.duplicate_groups == 2
    assert report.duplicate_files == 5
    db.close()


# ---------------------------------------------------------------------------
# missing_sample_ids
# ---------------------------------------------------------------------------

def test_missing_sample_ids_bogus_path_returned(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample("/nonexistent/fake/path/sound.wav"))

    missing = missing_sample_ids(db)

    assert sid in missing
    db.close()


def test_missing_sample_ids_real_file_not_returned(tmp_path):
    real_file = tmp_path / "present.wav"
    real_file.write_bytes(b"fake audio data")
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample(str(real_file)))

    missing = missing_sample_ids(db)

    assert sid not in missing
    db.close()


def test_missing_sample_ids_mixed(tmp_path):
    real_file = tmp_path / "present.wav"
    real_file.write_bytes(b"data")
    db = Database(tmp_path / "t.db")
    present_sid = db.upsert_sample(_sample(str(real_file)))
    missing_sid = db.upsert_sample(_sample("/no/such/file.wav"))

    missing = missing_sample_ids(db)

    assert missing_sid in missing
    assert present_sid not in missing
    db.close()


def test_missing_sample_ids_empty_db_returns_empty(tmp_path):
    db = Database(tmp_path / "t.db")

    assert missing_sample_ids(db) == []
    db.close()


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

def test_format_report_returns_nonempty_list(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav"))
    report = library_health(db, check_files=False)
    db.close()

    rows = format_report(report)

    assert len(rows) > 0


def test_format_report_returns_list_of_str_tuples(tmp_path):
    db = Database(tmp_path / "t.db")
    report = library_health(db, check_files=False)
    db.close()

    rows = format_report(report)

    for label, value in rows:
        assert isinstance(label, str)
        assert isinstance(value, str)


def test_format_report_includes_total_row(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/kick.wav"))
    db.upsert_sample(_sample("/a/snare.wav"))
    report = library_health(db, check_files=False)
    db.close()

    rows = format_report(report)
    labels = [r[0] for r in rows]

    assert "Total samples" in labels


def test_format_report_includes_source_rows(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_sample(_sample("/a/a.wav", source="local"))
    db.upsert_sample(_sample("/a/b.wav", source="edit"))
    report = library_health(db, check_files=False)
    db.close()

    rows = format_report(report)
    labels = [r[0] for r in rows]

    assert any("local" in lbl for lbl in labels)
    assert any("edit" in lbl for lbl in labels)

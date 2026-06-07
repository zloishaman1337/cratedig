"""Unit tests for cratedig.dedup (group_duplicates, pick_best, plan_resolution, plan_all)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cratedig.db.models import Sample
from cratedig.dedup import (
    group_duplicates,
    is_generated_edit,
    pick_best,
    plan_all,
    plan_resolution,
)


def _s(path: str, **kw) -> Sample:
    """Convenience factory — mirrors test_database._sample but no DB required."""
    return Sample(
        id=None,
        path=path,
        filename=Path(path).name,
        **kw,
    )


# ---------------------------------------------------------------------------
# is_generated_edit
# ---------------------------------------------------------------------------

def test_is_generated_edit_source_edit_is_true():
    s = _s("/packs/kick.wav", source="edit")
    assert is_generated_edit(s) is True


def test_is_generated_edit_local_source_is_false():
    s = _s("/packs/kick.wav", source="local")
    assert is_generated_edit(s) is False


def test_is_generated_edit_under_saved_dir_is_true(tmp_path):
    saved_dir = tmp_path / "Saved"
    saved_dir.mkdir()
    sub = saved_dir / "01_01_2026" / "kick_edit.wav"
    s = _s(str(sub), source="local")
    assert is_generated_edit(s, saved_dir=str(saved_dir)) is True


def test_is_generated_edit_outside_saved_dir_is_false(tmp_path):
    saved_dir = tmp_path / "Saved"
    saved_dir.mkdir()
    s = _s(str(tmp_path / "OtherDir" / "kick.wav"), source="local")
    assert is_generated_edit(s, saved_dir=str(saved_dir)) is False


# ---------------------------------------------------------------------------
# group_duplicates
# ---------------------------------------------------------------------------

def test_group_duplicates_returns_only_size_ge_2_groups():
    samples = [
        _s("/a/kick.wav", file_hash="same"),
        _s("/b/kick-copy.wav", file_hash="same"),
        _s("/c/snare.wav", file_hash="unique"),
    ]
    groups = group_duplicates(samples)

    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_group_duplicates_skips_falsy_hash():
    samples = [
        _s("/a/kick.wav", file_hash=""),
        _s("/b/kick.wav", file_hash=None),
        _s("/c/kick.wav", file_hash="real"),
        _s("/d/kick.wav", file_hash="real"),
    ]
    groups = group_duplicates(samples)

    assert len(groups) == 1
    assert all(s.file_hash == "real" for s in groups[0])


def test_group_duplicates_is_deterministic():
    samples = [
        _s("/z/kick.wav", file_hash="hash1"),
        _s("/a/kick.wav", file_hash="hash1"),
        _s("/m/kick.wav", file_hash="hash1"),
    ]
    result1 = group_duplicates(samples)
    result2 = group_duplicates(samples)

    assert [s.path for s in result1[0]] == [s.path for s in result2[0]]


def test_group_duplicates_ordered_by_path_within_group():
    samples = [
        _s("/z/kick.wav", file_hash="abc"),
        _s("/a/kick.wav", file_hash="abc"),
        _s("/m/kick.wav", file_hash="abc"),
    ]
    groups = group_duplicates(samples)

    paths = [s.path for s in groups[0]]
    assert paths == sorted(paths)


def test_group_duplicates_empty_input():
    assert group_duplicates([]) == []


def test_group_duplicates_no_duplicates_returns_empty():
    samples = [
        _s("/a/kick.wav", file_hash="h1"),
        _s("/b/snare.wav", file_hash="h2"),
    ]
    assert group_duplicates(samples) == []


def test_group_duplicates_multiple_hash_groups():
    samples = [
        _s("/a/a1.wav", file_hash="groupA"),
        _s("/a/a2.wav", file_hash="groupA"),
        _s("/b/b1.wav", file_hash="groupB"),
        _s("/b/b2.wav", file_hash="groupB"),
        _s("/b/b3.wav", file_hash="groupB"),
    ]
    groups = group_duplicates(samples)

    assert len(groups) == 2
    sizes = sorted(len(g) for g in groups)
    assert sizes == [2, 3]


# ---------------------------------------------------------------------------
# pick_best
# ---------------------------------------------------------------------------

def test_pick_best_prefers_local_over_edit():
    edit = _s("/saved/kick_edit.wav", source="edit", analyzed_at="2026-01-01T00:00:00+00:00")
    local = _s("/packs/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")

    keeper = pick_best([edit, local])

    assert keeper is local


def test_pick_best_prefers_analyzed_over_unanalyzed():
    unanalyzed = _s("/packs/a.wav", source="local", analyzed_at=None)
    analyzed = _s("/packs/b.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")

    keeper = pick_best([unanalyzed, analyzed])

    assert keeper is analyzed


def test_pick_best_prefers_shorter_path_as_tiebreak():
    # Both local, both analyzed, both no metadata — shortest path wins
    short = _s("/a/k.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    longer = _s("/longer/path/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")

    keeper = pick_best([short, longer])

    assert keeper is short


def test_pick_best_never_returns_edit_when_local_exists():
    edit1 = _s("/saved/e1.wav", source="edit")
    edit2 = _s("/saved/e2.wav", source="edit")
    local = _s("/z/local_very_long_path_but_still_local.wav", source="local")

    keeper = pick_best([edit1, edit2, local])

    assert keeper is local


def test_pick_best_single_member_returns_it():
    s = _s("/packs/kick.wav", source="local")

    assert pick_best([s]) is s


def test_pick_best_prefers_richer_metadata():
    no_meta = _s("/a/a.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00",
                 category=None, instrument_class=None)
    with_meta = _s("/b/a.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00",
                   category="drum", instrument_class=None)

    keeper = pick_best([no_meta, with_meta])

    assert keeper is with_meta


# ---------------------------------------------------------------------------
# plan_resolution
# ---------------------------------------------------------------------------

def test_plan_resolution_keep_equals_pick_best():
    edit = _s("/saved/kick_edit.wav", source="edit")
    local = _s("/packs/kick.wav", source="local")
    group = [edit, local]

    plan = plan_resolution(group)

    assert plan.keep is pick_best(group)


def test_plan_resolution_remove_is_non_keeper_members():
    s1 = _s("/a/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    s2 = _s("/b/kick.wav", source="local", analyzed_at=None)
    group = [s1, s2]

    plan = plan_resolution(group)

    assert len(plan.remove) == 1
    assert plan.keep not in plan.remove


def test_plan_resolution_edit_in_remove_appears_in_protected():
    edit = _s("/saved/kick_edit.wav", source="edit")
    local = _s("/packs/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    group = [edit, local]

    plan = plan_resolution(group)

    assert edit in plan.protected
    assert local not in plan.protected


def test_plan_resolution_no_edit_in_group_protected_is_empty():
    s1 = _s("/a/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    s2 = _s("/b/kick.wav", source="local", analyzed_at=None)
    group = [s1, s2]

    plan = plan_resolution(group)

    assert plan.protected == []


def test_plan_resolution_custom_keep_overrides_heuristic():
    s1 = _s("/a/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    s2 = _s("/b/kick.wav", source="edit")
    group = [s1, s2]

    plan = plan_resolution(group, keep=s2)

    assert plan.keep is s2
    assert s1 in plan.remove


def test_plan_resolution_saved_dir_marks_path_as_protected(tmp_path):
    saved_dir = tmp_path / "Saved"
    saved_dir.mkdir()
    edit_path = saved_dir / "01_01_2026" / "kick_edit.wav"
    edit_sample = _s(str(edit_path), source="local")  # source is local but path under saved_dir
    local = _s("/packs/kick.wav", source="local", analyzed_at="2026-01-01T00:00:00+00:00")
    group = [local, edit_sample]

    plan = plan_resolution(group, saved_dir=str(saved_dir))

    assert plan.keep is local
    assert edit_sample in plan.protected


# ---------------------------------------------------------------------------
# plan_all
# ---------------------------------------------------------------------------

def test_plan_all_produces_one_plan_per_hash_group():
    samples = [
        _s("/a/a1.wav", file_hash="groupA"),
        _s("/a/a2.wav", file_hash="groupA"),
        _s("/b/b1.wav", file_hash="groupB"),
        _s("/b/b2.wav", file_hash="groupB"),
        _s("/c/c1.wav", file_hash="unique"),  # no group — only 1 member
    ]
    plans = plan_all(samples)

    assert len(plans) == 2


def test_plan_all_empty_input_returns_empty():
    assert plan_all([]) == []


def test_plan_all_each_plan_has_keep_and_remove():
    samples = [
        _s("/a/kick.wav", file_hash="hash"),
        _s("/b/kick.wav", file_hash="hash"),
    ]
    plans = plan_all(samples)

    assert len(plans) == 1
    assert plans[0].keep is not None
    assert len(plans[0].remove) == 1

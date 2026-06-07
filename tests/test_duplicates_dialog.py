"""Unit tests for cratedig.gui.duplicates_dialog.DuplicatesDialog (TDD — these are FAILING tests)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cratedig.db.models import Sample
from cratedig.dedup import group_duplicates, plan_resolution


def _s(id_: int | None, path: str, file_hash: str | None = None, source: str = "local", **kw) -> Sample:
    """Convenience factory for Sample objects — mirrors test_dedup._s pattern.

    Args:
        id_: sample.id (distinct int or None)
        path: file path
        file_hash: file_hash for grouping duplicates
        source: defaults to "local"; use "edit" for generated edits
        **kw: passed to Sample() (analyzed_at, category, instrument_class, etc.)
    """
    return Sample(
        id=id_,
        path=path,
        filename=Path(path).name,
        file_hash=file_hash,
        source=source,
        **kw,
    )


class TestDuplicatesDialog:
    """Tests for DuplicatesDialog widget (logic, not rendering)."""

    def _app(self):
        """Set up QApplication for PySide6 tests — matches test_gui_logic pattern."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_group_count_equals_dedup_group_duplicates_length(self):
        """group_count property matches len(dedup.group_duplicates(samples))."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        # Build: 2 hash groups (sizes 2 and 3) + 1 unique (not a duplicate)
        samples = [
            _s(1, "/a/kick_orig.wav", file_hash="hash_a"),
            _s(2, "/a/kick_copy.wav", file_hash="hash_a"),
            _s(3, "/b/snare1.wav", file_hash="hash_b"),
            _s(4, "/b/snare2.wav", file_hash="hash_b"),
            _s(5, "/b/snare3.wav", file_hash="hash_b"),
            _s(6, "/c/unique_tom.wav", file_hash="hash_c"),  # only 1 member, no group
        ]

        dialog = DuplicatesDialog(samples)

        expected_groups = group_duplicates(samples)
        assert dialog.group_count == len(expected_groups)
        assert dialog.group_count == 2  # only hash_a (size 2) and hash_b (size 3) form groups

    def test_default_keeper_id_equals_pick_best(self):
        """Default keeper_id(gi) equals pick_best(group).id for each group."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        # Build one group: one analyzed (should win), one unanalyzed
        analyzed = _s(10, "/packs/kick.wav", file_hash="grp1", analyzed_at="2026-01-01T00:00:00+00:00")
        unanalyzed = _s(11, "/temp/kick_copy.wav", file_hash="grp1", analyzed_at=None)
        samples = [analyzed, unanalyzed]

        dialog = DuplicatesDialog(samples)

        groups = group_duplicates(samples)
        for gi in range(len(groups)):
            from cratedig.dedup import pick_best
            expected_keeper = pick_best(groups[gi])
            assert dialog.keeper_id(gi) == expected_keeper.id

    def test_set_keeper_changes_keeper_and_plan(self):
        """set_keeper(gi, sample_id) changes the keeper; plan_for_group reflects new keeper."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(20, "/a/kick.wav", file_hash="h1", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(21, "/b/kick.wav", file_hash="h1", analyzed_at=None)
        samples = [s1, s2]

        dialog = DuplicatesDialog(samples)

        # Initially, pick_best should choose s1 (analyzed)
        assert dialog.keeper_id(0) == 20

        # Override to choose s2
        dialog.set_keeper(0, 21)
        assert dialog.keeper_id(0) == 21

        # plan_for_group should reflect new keeper
        plan = dialog.plan_for_group(0)
        assert plan.keep.id == 21
        assert 20 in [s.id for s in plan.remove]

    def test_plan_for_group_protected_contains_only_generated_edits(self, tmp_path):
        """plan_for_group().protected lists exactly the edit members in remove."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()

        # Build group: local keeper + edit that should be removed + another local
        keeper = _s(30, "/packs/kick.wav", file_hash="grp", source="local",
                   analyzed_at="2026-01-01T00:00:00+00:00")
        edit_to_remove = _s(31, str(saved_dir / "kick_edit.wav"), file_hash="grp",
                           source="edit", analyzed_at=None)
        other_local = _s(32, "/packs/kick_alt.wav", file_hash="grp", source="local",
                        analyzed_at=None)
        samples = [keeper, edit_to_remove, other_local]

        dialog = DuplicatesDialog(samples, saved_dir=str(saved_dir))

        # Keeper should be the fully analyzed one
        assert dialog.keeper_id(0) == 30

        plan = dialog.plan_for_group(0)
        assert plan.keep.id == 30

        # protected should contain only the edit
        assert len(plan.protected) == 1
        assert plan.protected[0].id == 31

        # remove should have both non-keeper members
        remove_ids = {s.id for s in plan.remove}
        assert remove_ids == {31, 32}

    def test_plan_for_group_with_under_saved_dir_path(self, tmp_path):
        """plan_for_group correctly identifies samples under saved_dir as protected (path-based)."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        saved_dir = tmp_path / "SavedEdits"
        saved_dir.mkdir()

        # Build: local keeper + local under saved_dir (should be protected)
        keeper = _s(40, "/packs/snare.wav", file_hash="h", source="local",
                   analyzed_at="2026-01-01T00:00:00+00:00")
        under_saved = _s(41, str(saved_dir / "snare_copy.wav"), file_hash="h",
                        source="local", analyzed_at=None)
        samples = [keeper, under_saved]

        dialog = DuplicatesDialog(samples, saved_dir=str(saved_dir))

        plan = dialog.plan_for_group(0)
        assert plan.keep.id == 40

        # under_saved should be in protected even though source="local"
        assert plan.protected[0].id == 41
        assert under_saved in plan.protected

    def test_is_resolved_starts_false_becomes_true_after_perform_resolution(self):
        """is_resolved(gi) is False until _perform_resolution(gi) is called."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(50, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(51, "/b/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2]

        dialog = DuplicatesDialog(samples)

        # Should start unresolved
        assert dialog.is_resolved(0) is False

        # Perform resolution
        dialog._perform_resolution(0)

        # Should now be resolved
        assert dialog.is_resolved(0) is True

    def test_perform_resolution_emits_delete_requested_for_all_remove_members(self):
        """_perform_resolution(gi) emits delete_requested(id) for each member in plan.remove."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(60, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(61, "/b/kick.wav", file_hash="h", analyzed_at=None)
        s3 = _s(62, "/c/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2, s3]

        dialog = DuplicatesDialog(samples)

        # Collect emitted delete_requested signals
        emitted_ids = []
        dialog.delete_requested.connect(lambda id_: emitted_ids.append(id_))

        # Perform resolution on group 0
        dialog._perform_resolution(0)

        # Should emit for s2 and s3 (not s1, which is keeper)
        plan = dialog.plan_for_group(0)
        remove_ids = {s.id for s in plan.remove}

        assert set(emitted_ids) == remove_ids
        assert 60 not in emitted_ids  # keeper should not be deleted

    def test_perform_resolution_does_not_emit_delete_for_keeper(self):
        """_perform_resolution(gi) does NOT emit delete_requested for the keeper."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        keeper = _s(70, "/packs/kick.wav", file_hash="h",
                   analyzed_at="2026-01-01T00:00:00+00:00")
        other = _s(71, "/temp/kick.wav", file_hash="h", analyzed_at=None)
        samples = [keeper, other]

        dialog = DuplicatesDialog(samples)

        emitted_ids = []
        dialog.delete_requested.connect(lambda id_: emitted_ids.append(id_))

        dialog._perform_resolution(0)

        assert 70 not in emitted_ids
        assert 71 in emitted_ids

    def test_reveal_requested_signal_exists_and_accepts_str(self):
        """reveal_requested is a real Signal that emits str (sample path)."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(80, "/packs/sample.wav", file_hash="h")
        samples = [s1]

        dialog = DuplicatesDialog(samples)

        # Collect emitted paths
        collected_paths = []
        dialog.reveal_requested.connect(lambda path: collected_paths.append(path))

        # Manually emit
        test_path = "/some/file.wav"
        dialog.reveal_requested.emit(test_path)

        # Assert collector got it
        assert test_path in collected_paths

    def test_delete_requested_signal_exists_and_accepts_int(self):
        """delete_requested is a real Signal that emits int (sample id)."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(90, "/packs/sample.wav", file_hash="h")
        samples = [s1]

        dialog = DuplicatesDialog(samples)

        # Collect emitted ids
        collected_ids = []
        dialog.delete_requested.connect(lambda id_: collected_ids.append(id_))

        # Manually emit
        dialog.delete_requested.emit(42)

        # Assert collector got it
        assert 42 in collected_ids

    def test_perform_resolution_emits_in_correct_order(self):
        """_perform_resolution(gi) emits all delete_requested signals before marking resolved."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(100, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(101, "/b/kick.wav", file_hash="h", analyzed_at=None)
        s3 = _s(102, "/c/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2, s3]

        dialog = DuplicatesDialog(samples)

        emitted_ids = []
        resolved_during_emission = []

        def on_delete(id_):
            emitted_ids.append(id_)
            # Check if already marked resolved at emission time
            resolved_during_emission.append(dialog.is_resolved(0))

        dialog.delete_requested.connect(on_delete)

        dialog._perform_resolution(0)

        # All emissions should have happened while still unresolved
        assert all(not resolved for resolved in resolved_during_emission)
        # Only after all are emitted should it be resolved
        assert dialog.is_resolved(0) is True

    def test_group_count_with_empty_samples(self):
        """group_count is 0 when no samples or no duplicates exist."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        dialog = DuplicatesDialog([])

        assert dialog.group_count == 0

    def test_group_count_with_no_duplicates(self):
        """group_count is 0 when all samples have unique hashes."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        samples = [
            _s(110, "/a/kick.wav", file_hash="h1"),
            _s(111, "/b/snare.wav", file_hash="h2"),
            _s(112, "/c/tom.wav", file_hash="h3"),
        ]

        dialog = DuplicatesDialog(samples)

        assert dialog.group_count == 0

    def test_keeper_id_with_custom_keep_override(self):
        """keeper_id(gi) reflects set_keeper override and remains stable across plan_for_group calls."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(120, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(121, "/b/kick.wav", file_hash="h", analyzed_at=None)
        s3 = _s(122, "/c/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2, s3]

        dialog = DuplicatesDialog(samples)

        # Override to s2
        dialog.set_keeper(0, 121)

        # Check multiple calls return same keeper
        assert dialog.keeper_id(0) == 121
        assert dialog.plan_for_group(0).keep.id == 121
        assert dialog.keeper_id(0) == 121  # stable

    def test_plan_for_group_respects_set_keeper_in_remove_list(self):
        """plan_for_group(gi).remove excludes the chosen keeper, even if not pick_best."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        # s1 would be picked by heuristic
        s1 = _s(130, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        # s2 is less preferred but we force it as keeper
        s2 = _s(131, "/b/kick.wav", file_hash="h", analyzed_at=None)
        s3 = _s(132, "/c/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2, s3]

        dialog = DuplicatesDialog(samples)
        dialog.set_keeper(0, 131)

        plan = dialog.plan_for_group(0)

        # Keeper should be s2
        assert plan.keep.id == 131

        # Remove should be s1 and s3
        remove_ids = {s.id for s in plan.remove}
        assert 131 not in remove_ids
        assert remove_ids == {130, 132}

    def test_perform_resolution_with_protected_members(self, tmp_path):
        """_perform_resolution emits delete_requested even for protected members."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()

        keeper = _s(140, "/packs/kick.wav", file_hash="h",
                   analyzed_at="2026-01-01T00:00:00+00:00")
        edit = _s(141, str(saved_dir / "kick_edit.wav"), file_hash="h",
                 source="edit", analyzed_at=None)
        samples = [keeper, edit]

        dialog = DuplicatesDialog(samples, saved_dir=str(saved_dir))

        emitted_ids = []
        dialog.delete_requested.connect(lambda id_: emitted_ids.append(id_))

        dialog._perform_resolution(0)

        # Protected members should still be deleted
        assert 141 in emitted_ids
        assert 140 not in emitted_ids

    def test_multiple_groups_independence(self):
        """Multiple groups are independent; resolving one doesn't affect others."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        # Group 1: hash_a (size 2)
        s1 = _s(150, "/a/kick.wav", file_hash="hash_a", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(151, "/a/kick2.wav", file_hash="hash_a", analyzed_at=None)

        # Group 2: hash_b (size 2)
        s3 = _s(152, "/b/snare.wav", file_hash="hash_b", analyzed_at="2026-01-01T00:00:00+00:00")
        s4 = _s(153, "/b/snare2.wav", file_hash="hash_b", analyzed_at=None)

        samples = [s1, s2, s3, s4]

        dialog = DuplicatesDialog(samples)

        assert dialog.group_count == 2

        # Resolve group 0
        dialog._perform_resolution(0)

        assert dialog.is_resolved(0) is True
        assert dialog.is_resolved(1) is False

    def test_set_keeper_multiple_times_uses_latest(self):
        """Calling set_keeper multiple times uses the most recent value."""
        self._app()
        from cratedig.gui.duplicates_dialog import DuplicatesDialog

        s1 = _s(160, "/a/kick.wav", file_hash="h", analyzed_at="2026-01-01T00:00:00+00:00")
        s2 = _s(161, "/b/kick.wav", file_hash="h", analyzed_at=None)
        s3 = _s(162, "/c/kick.wav", file_hash="h", analyzed_at=None)
        samples = [s1, s2, s3]

        dialog = DuplicatesDialog(samples)

        dialog.set_keeper(0, 161)
        assert dialog.keeper_id(0) == 161

        dialog.set_keeper(0, 162)
        assert dialog.keeper_id(0) == 162

        plan = dialog.plan_for_group(0)
        assert plan.keep.id == 162

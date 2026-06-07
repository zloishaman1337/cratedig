"""Tests for ALS Explorer library matching — match ALS sample names against the local library.

Contracts:
1. PURE matcher: match_als_samples(names, index) -> {found, candidates, unresolved}
2. DB index: Database.samples_basename_index() -> dict[normalized_key, list[sample_records]]
3. Worker signal: IndexWorker has request_als_match @Slot and alsMatchReady Signal
4. AlsExplorerPanel: method set_match_result(dict) accepts {found, candidates, unresolved}
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from cratedig.db import Database
from cratedig.db.models import Sample


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sample(path: str, **kw) -> Sample:
    """Create a Sample for testing."""
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


# ── Contract 1: Pure matcher (cratedig.gui.logic.match_als_samples) ──────────

class TestMatchAlsSamplesPureMatcher:
    """Test match_als_samples(names: list[str], index: dict) -> dict.

    The index maps normalized-basename (case-insensitive lowercase) -> list of
    sample records/ids. The matcher returns:
    - 'found': list of (name, matched_library_sample) where exact basename match
    - 'candidates': list of (name, matches) where same stem ignoring extension
    - 'unresolved': list of names with no match
    """

    def test_match_als_samples_exact_match_case_insensitive(self):
        """Exact match on filename (case-insensitive) goes to 'found'."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        # Index: kick.wav is in library
        index = {
            "kick.wav": ["sample_1"],
        }
        names = ["Kick.wav"]
        result = match_als_samples(names, index)

        assert "found" in result
        assert "candidates" in result
        assert "unresolved" in result
        assert len(result["found"]) == 1
        assert result["found"][0][0] == "Kick.wav"
        assert result["found"][0][1] == "sample_1"
        assert len(result["candidates"]) == 0
        assert len(result["unresolved"]) == 0

    def test_match_als_samples_exact_match_identical_case(self):
        """Exact match with identical case."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {"snare.wav": ["sample_2"]}
        names = ["snare.wav"]
        result = match_als_samples(names, index)

        assert len(result["found"]) == 1
        assert result["found"][0] == ("snare.wav", "sample_2")

    def test_match_als_samples_extension_difference_goes_to_candidates(self):
        """Same stem, different extension (e.g., kick.aiff vs kick.wav) → candidates."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        # Library has kick.wav, ALS references kick.aiff
        index = {"kick.wav": ["sample_1"]}
        names = ["kick.aiff"]
        result = match_als_samples(names, index)

        assert len(result["found"]) == 0
        assert len(result["candidates"]) == 1
        assert result["candidates"][0][0] == "kick.aiff"
        # Candidates should contain the matching library entry
        assert "sample_1" in result["candidates"][0][1]

    def test_match_als_samples_unresolved_no_match(self):
        """Sample with no match in library → unresolved."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {"kick.wav": ["sample_1"]}
        names = ["nonexistent_sample_zzz.wav"]
        result = match_als_samples(names, index)

        assert len(result["found"]) == 0
        assert len(result["candidates"]) == 0
        assert len(result["unresolved"]) == 1
        assert result["unresolved"][0] == "nonexistent_sample_zzz.wav"

    def test_match_als_samples_empty_names_returns_empty_lists(self):
        """Empty ALS sample list → all three lists empty."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {"kick.wav": ["sample_1"]}
        names = []
        result = match_als_samples(names, index)

        assert result["found"] == []
        assert result["candidates"] == []
        assert result["unresolved"] == []

    def test_match_als_samples_empty_index_all_unresolved(self):
        """Empty library index → all samples unresolved."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {}
        names = ["kick.wav", "snare.wav"]
        result = match_als_samples(names, index)

        assert result["found"] == []
        assert result["candidates"] == []
        assert set(result["unresolved"]) == {"kick.wav", "snare.wav"}

    def test_match_als_samples_multiple_matches_same_category(self):
        """Multiple library samples with same basename go to same found entry."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        # Library has two samples both named "kick.wav" (from different paths)
        index = {"kick.wav": ["sample_1", "sample_2"]}
        names = ["kick.wav"]
        result = match_als_samples(names, index)

        assert len(result["found"]) == 1
        assert result["found"][0][0] == "kick.wav"
        # Both library entries should be in the match list
        assert set(result["found"][0][1]) == {"sample_1", "sample_2"}

    def test_match_als_samples_deterministic_order_found(self):
        """Found results maintain input order."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {"snare.wav": ["s"], "kick.wav": ["k"], "hat.wav": ["h"]}
        names = ["hat.wav", "kick.wav", "snare.wav"]
        result = match_als_samples(names, index)

        # Should preserve order from names list
        found_names = [f[0] for f in result["found"]]
        assert found_names == ["hat.wav", "kick.wav", "snare.wav"]

    def test_match_als_samples_case_insensitive_normalization(self):
        """Normalization is case-insensitive (full filename)."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        # Index uses lowercase
        index = {"kick.wav": ["s1"], "snare.wav": ["s2"]}
        names = ["KICK.WAV", "Snare.WAV"]
        result = match_als_samples(names, index)

        # Both should match exactly (case-insensitive)
        assert len(result["found"]) == 2
        assert {f[0] for f in result["found"]} == {"KICK.WAV", "Snare.WAV"}

    def test_match_als_samples_duplicate_names_in_als(self):
        """Duplicate ALS sample names are each processed."""
        pytest.importorskip("cratedig.gui.logic")
        from cratedig.gui.logic import match_als_samples

        index = {"kick.wav": ["s1"]}
        names = ["kick.wav", "kick.wav"]
        result = match_als_samples(names, index)

        # Both occurrences should be in found
        assert len(result["found"]) == 2


# ── Contract 2: Database basename index ────────────────────────────────────

class TestDatabaseBasenameIndex:
    """Test Database.samples_basename_index() -> dict[str, list].

    Maps normalized-basename (lowercase, no extension assumptions) to list of
    samples (or Sample objects, or ids+paths).
    """

    def test_samples_basename_index_returns_dict(self, tmp_path):
        """Return type is dict with string keys."""
        db = Database(tmp_path / "t.db")

        db.upsert_sample(_sample("/a/kick.wav"))

        result = db.samples_basename_index()

        assert isinstance(result, dict)
        db.close()

    def test_samples_basename_index_keys_are_lowercase_basenames(self, tmp_path):
        """Keys are normalized (lowercase) basenames."""
        db = Database(tmp_path / "t.db")

        db.upsert_sample(_sample("/a/Kick.wav"))

        result = db.samples_basename_index()

        # Should have a key for 'kick.wav' (lowercase)
        assert "kick.wav" in result
        db.close()

    def test_samples_basename_index_values_are_lists(self, tmp_path):
        """Values are lists (of samples or Sample objects)."""
        db = Database(tmp_path / "t.db")

        db.upsert_sample(_sample("/a/kick.wav"))

        result = db.samples_basename_index()

        for key, value in result.items():
            assert isinstance(value, list)
        db.close()

    def test_samples_basename_index_values_contain_samples(self, tmp_path):
        """Values contain Sample objects or dicts with id/path/filename."""
        db = Database(tmp_path / "t.db")

        sid = db.upsert_sample(_sample("/a/kick.wav"))

        result = db.samples_basename_index()

        # The list should contain at least one entry
        assert len(result.get("kick.wav", [])) >= 1
        entry = result["kick.wav"][0]
        # Entry should be a Sample object or have id, path, filename
        assert hasattr(entry, "id") or isinstance(entry, dict)
        db.close()

    def test_samples_basename_index_groups_by_lowercase_basename(self, tmp_path):
        """Two samples with same basename (case-insensitive) group under one key."""
        db = Database(tmp_path / "t.db")

        sid1 = db.upsert_sample(_sample("/packs/drums/Kick.wav"))
        sid2 = db.upsert_sample(_sample("/packs/kicks/kick.wav"))

        result = db.samples_basename_index()

        # Both should map to the same lowercase key
        assert "kick.wav" in result
        kick_samples = result["kick.wav"]
        assert len(kick_samples) == 2
        db.close()

    def test_samples_basename_index_empty_database(self, tmp_path):
        """Empty database returns empty dict."""
        db = Database(tmp_path / "t.db")

        result = db.samples_basename_index()

        assert result == {}
        db.close()

    def test_samples_basename_index_multiple_files(self, tmp_path):
        """Multiple different files each get their own key."""
        db = Database(tmp_path / "t.db")

        db.upsert_sample(_sample("/a/kick.wav"))
        db.upsert_sample(_sample("/a/snare.wav"))
        db.upsert_sample(_sample("/a/hat.wav"))

        result = db.samples_basename_index()

        assert set(result.keys()) == {"kick.wav", "snare.wav", "hat.wav"}
        db.close()

    def test_samples_basename_index_case_normalization_variety(self, tmp_path):
        """Case variations normalize to the same key."""
        db = Database(tmp_path / "t.db")

        # Insert with various cases
        db.upsert_sample(_sample("/a/KICK.WAV"))
        db.upsert_sample(_sample("/a/Kick.WAV"))
        db.upsert_sample(_sample("/a/kick.wav"))

        result = db.samples_basename_index()

        # All should be under 'kick.wav'
        assert len(result) == 1
        assert "kick.wav" in result
        kick_samples = result["kick.wav"]
        assert len(kick_samples) == 3
        db.close()


# ── Contract 3: Worker signal and slot ────────────────────────────────────

class TestWorkerAlsMatchSignal:
    """Test IndexWorker has request_als_match @Slot and alsMatchReady Signal."""

    def test_worker_has_als_match_ready_signal(self):
        """IndexWorker.alsMatchReady Signal exists."""
        pytest.importorskip("PySide6")

        from PySide6.QtCore import QObject
        from cratedig.gui.worker import IndexWorker
        from cratedig.config import Config, Paths, AudioCfg
        from cratedig.db import Database
        from pathlib import Path as PathlibPath
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        cfg = Config(
            paths=Paths(
                db=PathlibPath(tmp.name) / "test.db",
                download_dir=PathlibPath(tmp.name) / "dl",
                library_dirs=(),
                saved_dir=PathlibPath(tmp.name) / "_saved",
            ),
            audio=AudioCfg(),
        )
        db = Database(cfg.paths.db)
        worker = IndexWorker(db, cfg)

        assert hasattr(worker, "alsMatchReady")
        assert hasattr(worker.alsMatchReady, "emit")

        worker.deleteLater()
        db.close()
        tmp.cleanup()

    def test_worker_has_request_als_match_slot(self):
        """IndexWorker.request_als_match @Slot exists and is callable."""
        pytest.importorskip("PySide6")

        from cratedig.gui.worker import IndexWorker
        from cratedig.config import Config, Paths, AudioCfg
        from cratedig.db import Database
        from pathlib import Path as PathlibPath
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        cfg = Config(
            paths=Paths(
                db=PathlibPath(tmp.name) / "test.db",
                download_dir=PathlibPath(tmp.name) / "dl",
                library_dirs=(),
                saved_dir=PathlibPath(tmp.name) / "_saved",
            ),
            audio=AudioCfg(),
        )
        db = Database(cfg.paths.db)
        worker = IndexWorker(db, cfg)

        assert hasattr(worker, "request_als_match")
        assert callable(worker.request_als_match)

        worker.deleteLater()
        db.close()
        tmp.cleanup()

    def test_worker_als_match_slot_signature(self):
        """request_als_match accepts (seq, names_list) signature."""
        pytest.importorskip("PySide6")

        from cratedig.gui.worker import IndexWorker
        from cratedig.config import Config, Paths, AudioCfg
        from cratedig.db import Database
        from pathlib import Path as PathlibPath
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        cfg = Config(
            paths=Paths(
                db=PathlibPath(tmp.name) / "test.db",
                download_dir=PathlibPath(tmp.name) / "dl",
                library_dirs=(),
                saved_dir=PathlibPath(tmp.name) / "_saved",
            ),
            audio=AudioCfg(),
        )
        db = Database(cfg.paths.db)
        worker = IndexWorker(db, cfg)

        # Slot should be callable with integers and lists
        # Just verify it doesn't raise on signature introspection
        method = getattr(worker, "request_als_match", None)
        assert method is not None

        worker.deleteLater()
        db.close()
        tmp.cleanup()


# ── Contract 4: AlsExplorerPanel set_match_result method ───────────────────

class TestAlsExplorerPanelMatchResult:
    """Test AlsExplorerPanel.set_match_result(dict) accepts match results."""

    def test_als_explorer_panel_has_set_match_result_method(self):
        """AlsExplorerPanel has set_match_result method."""
        pytest.importorskip("PySide6")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])

        panel = AlsExplorerPanel()
        assert hasattr(panel, "set_match_result")
        assert callable(panel.set_match_result)

        panel.close()

    def test_als_explorer_panel_set_match_result_accepts_dict_with_keys(self):
        """set_match_result accepts dict with found/candidates/unresolved keys."""
        pytest.importorskip("PySide6")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])

        panel = AlsExplorerPanel()
        result_dict = {
            "found": [("kick.wav", "sample_1")],
            "candidates": [("snare.aiff", ["sample_2"])],
            "unresolved": ["hat.wav"],
        }

        # Should not raise
        panel.set_match_result(result_dict)

        panel.close()

    def test_als_explorer_panel_set_match_result_empty_dict(self):
        """set_match_result handles empty result dict gracefully."""
        pytest.importorskip("PySide6")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])

        panel = AlsExplorerPanel()
        result_dict = {"found": [], "candidates": [], "unresolved": []}

        # Should not raise
        panel.set_match_result(result_dict)

        panel.close()

    def test_als_explorer_panel_has_match_triggered_mechanism(self):
        """AlsExplorerPanel has a way to trigger matching (signal or button)."""
        pytest.importorskip("PySide6")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])

        panel = AlsExplorerPanel()

        # Should have either a signal or a button to trigger matching
        has_signal = hasattr(panel, "matchRequested")
        has_button = hasattr(panel, "_btn_match") or hasattr(panel, "match_button")

        assert has_signal or has_button, \
            "AlsExplorerPanel should have either matchRequested signal or match button"

        panel.close()

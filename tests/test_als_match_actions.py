"""Tests for ALS Explorer Library Match tab action signals and emitters.

CONTRACT FOR DEVELOPER:
========================
AlsExplorerPanel must gain three signals and three helper methods for normalizing
found-entry shapes and emitting signals.

Signals (PySide6.QtCore.Signal):
  - reveal_requested: emits str (sample path)
  - add_to_crate_requested: emits (object, int) where object is Sample, int is crate_id
  - create_crate_requested: emits object (Sample)

Helper methods (should normalize entry shape and emit):
  - _emit_reveal_for(entry) -> emits reveal_requested with sample.path (str)
  - _emit_add_to_crate_for(entry, crate_id) -> emits add_to_crate_requested with (sample, crate_id)
  - _emit_create_crate_for(entry) -> emits create_crate_requested with sample

Entry shape normalization:
  When entry is a list of Samples, use the PRIMARY (first) Sample.
  When entry is a single Sample, use that Sample directly.
  The emitted Sample path on reveal must be sample.path (str).
  The emitted Sample object on add/create must be the Sample instance itself.

Tests drive:
  1. Signal existence and arity (slots can connect and receive correct types)
  2. Entry shape normalization (single Sample vs list of Samples)
  3. Correct data emission (paths as strings, Sample objects in add/create)
"""

from __future__ import annotations

import os
import pytest
from pathlib import Path


def _make_sample(sample_id: int, path: str) -> object:
    """Create a Sample for testing.

    Import and construct without hard-importing Sample to avoid Qt dependency
    at module load time.
    """
    from cratedig.db.models import Sample
    filename = Path(path).name
    return Sample(id=sample_id, path=path, filename=filename)


class TestAlsExplorerPanelSignals:
    """Test that AlsExplorerPanel has the required signals with correct arity."""

    def test_reveal_requested_signal_exists(self):
        """AlsExplorerPanel has reveal_requested Signal."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        assert hasattr(panel, "reveal_requested"), \
            "AlsExplorerPanel must have reveal_requested Signal"
        assert hasattr(panel.reveal_requested, "emit"), \
            "reveal_requested must be a Signal (have emit method)"

        panel.close()

    def test_add_to_crate_requested_signal_exists(self):
        """AlsExplorerPanel has add_to_crate_requested Signal."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        assert hasattr(panel, "add_to_crate_requested"), \
            "AlsExplorerPanel must have add_to_crate_requested Signal"
        assert hasattr(panel.add_to_crate_requested, "emit"), \
            "add_to_crate_requested must be a Signal (have emit method)"

        panel.close()

    def test_create_crate_requested_signal_exists(self):
        """AlsExplorerPanel has create_crate_requested Signal."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        assert hasattr(panel, "create_crate_requested"), \
            "AlsExplorerPanel must have create_crate_requested Signal"
        assert hasattr(panel.create_crate_requested, "emit"), \
            "create_crate_requested must be a Signal (have emit method)"

        panel.close()


class TestRevealRequestedSignal:
    """Test reveal_requested signal emission with sample path (str)."""

    def test_emit_reveal_for_single_sample_emits_path(self):
        """_emit_reveal_for with single Sample emits sample.path (str)."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create a sample entry
        sample = _make_sample(1, "/packs/drums/kick.wav")

        # Connect slot to capture emission
        received = []
        def on_reveal(path: str) -> None:
            received.append(path)

        panel.reveal_requested.connect(on_reveal)

        # Emit via helper method
        assert hasattr(panel, "_emit_reveal_for"), \
            "AlsExplorerPanel must have _emit_reveal_for(entry) helper method"
        panel._emit_reveal_for(sample)

        # Verify emission
        assert len(received) == 1, "reveal_requested should emit exactly once"
        assert received[0] == "/packs/drums/kick.wav", \
            "reveal_requested should emit the sample.path as string"
        assert isinstance(received[0], str), \
            "emitted value must be str, not Sample object"

        panel.close()

    def test_emit_reveal_for_list_of_samples_emits_first_path(self):
        """_emit_reveal_for with list[Sample] emits first sample's path."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create a list of samples
        sample1 = _make_sample(1, "/packs/drums/kick_v1.wav")
        sample2 = _make_sample(2, "/packs/drums/kick_v2.wav")
        entries = [sample1, sample2]

        # Connect slot
        received = []
        def on_reveal(path: str) -> None:
            received.append(path)

        panel.reveal_requested.connect(on_reveal)

        # Emit via helper
        panel._emit_reveal_for(entries)

        # Should emit first sample's path only
        assert len(received) == 1, "reveal_requested should emit exactly once"
        assert received[0] == "/packs/drums/kick_v1.wav", \
            "should emit first sample in list"

        panel.close()


class TestAddToCrateRequestedSignal:
    """Test add_to_crate_requested signal emission with (Sample, crate_id)."""

    def test_emit_add_to_crate_for_single_sample(self):
        """_emit_add_to_crate_for with single Sample emits (sample, crate_id)."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel
        from cratedig.db.models import Sample

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create a sample entry
        sample = _make_sample(1, "/packs/drums/kick.wav")
        crate_id = 42

        # Connect slot
        received = []
        def on_add_to_crate(sample_obj: object, c_id: int) -> None:
            received.append((sample_obj, c_id))

        panel.add_to_crate_requested.connect(on_add_to_crate)

        # Emit via helper
        assert hasattr(panel, "_emit_add_to_crate_for"), \
            "AlsExplorerPanel must have _emit_add_to_crate_for(entry, crate_id) helper"
        panel._emit_add_to_crate_for(sample, crate_id)

        # Verify emission
        assert len(received) == 1, "should emit exactly once"
        emitted_sample, emitted_crate_id = received[0]
        assert isinstance(emitted_sample, Sample), \
            "first arg should be Sample object"
        assert emitted_sample.path == "/packs/drums/kick.wav", \
            "should emit the correct Sample"
        assert emitted_crate_id == 42, \
            "second arg should be the crate_id (int)"
        assert isinstance(emitted_crate_id, int), \
            "second arg must be int, not other type"

        panel.close()

    def test_emit_add_to_crate_for_list_of_samples_uses_first(self):
        """_emit_add_to_crate_for with list[Sample] uses first sample."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel
        from cratedig.db.models import Sample

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create list of samples
        sample1 = _make_sample(1, "/packs/drums/kick_v1.wav")
        sample2 = _make_sample(2, "/packs/drums/kick_v2.wav")
        entries = [sample1, sample2]
        crate_id = 99

        # Connect slot
        received = []
        def on_add_to_crate(sample_obj: object, c_id: int) -> None:
            received.append((sample_obj, c_id))

        panel.add_to_crate_requested.connect(on_add_to_crate)

        # Emit via helper
        panel._emit_add_to_crate_for(entries, crate_id)

        # Should use first sample
        assert len(received) == 1, "should emit exactly once"
        emitted_sample, emitted_crate_id = received[0]
        assert isinstance(emitted_sample, Sample), "should emit Sample object"
        assert emitted_sample.path == "/packs/drums/kick_v1.wav", \
            "should use first sample in list"
        assert emitted_crate_id == 99, "should emit correct crate_id"

        panel.close()


class TestCreateCrateRequestedSignal:
    """Test create_crate_requested signal emission with Sample object."""

    def test_emit_create_crate_for_single_sample(self):
        """_emit_create_crate_for with single Sample emits sample object."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel
        from cratedig.db.models import Sample

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create a sample entry
        sample = _make_sample(1, "/packs/drums/kick.wav")

        # Connect slot
        received = []
        def on_create_crate(sample_obj: object) -> None:
            received.append(sample_obj)

        panel.create_crate_requested.connect(on_create_crate)

        # Emit via helper
        assert hasattr(panel, "_emit_create_crate_for"), \
            "AlsExplorerPanel must have _emit_create_crate_for(entry) helper"
        panel._emit_create_crate_for(sample)

        # Verify emission
        assert len(received) == 1, "should emit exactly once"
        emitted_sample = received[0]
        assert isinstance(emitted_sample, Sample), \
            "should emit Sample object, not path string"
        assert emitted_sample.path == "/packs/drums/kick.wav", \
            "should emit the correct Sample"

        panel.close()

    def test_emit_create_crate_for_list_of_samples_uses_first(self):
        """_emit_create_crate_for with list[Sample] uses first sample."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel
        from cratedig.db.models import Sample

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create list of samples
        sample1 = _make_sample(1, "/packs/drums/kick_v1.wav")
        sample2 = _make_sample(2, "/packs/drums/kick_v2.wav")
        entries = [sample1, sample2]

        # Connect slot
        received = []
        def on_create_crate(sample_obj: object) -> None:
            received.append(sample_obj)

        panel.create_crate_requested.connect(on_create_crate)

        # Emit via helper
        panel._emit_create_crate_for(entries)

        # Should use first sample
        assert len(received) == 1, "should emit exactly once"
        emitted_sample = received[0]
        assert isinstance(emitted_sample, Sample), "should emit Sample"
        assert emitted_sample.path == "/packs/drums/kick_v1.wav", \
            "should use first sample in list"

        panel.close()


class TestSetMatchResultIntegration:
    """Test that set_match_result populates found entries with proper shape."""

    def test_set_match_result_found_entries_can_be_emitted(self):
        """After set_match_result, found entry shapes can be passed to emit helpers."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create match result with single-sample found entry
        sample = _make_sample(1, "/packs/drums/kick.wav")
        result = {
            "found": [("kick.wav", sample)],
            "candidates": [],
            "unresolved": [],
        }

        # Should not raise
        panel.set_match_result(result)

        # Entry shape should work with emit helpers
        name, entry = result["found"][0]

        # Reveal should emit the path
        received_reveal = []
        panel.reveal_requested.connect(lambda p: received_reveal.append(p))
        panel._emit_reveal_for(entry)
        assert len(received_reveal) == 1
        assert isinstance(received_reveal[0], str)

        panel.close()

    def test_set_match_result_found_entries_with_list_samples(self):
        """When found entry is list[Sample], emit helpers use first."""
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication
        from cratedig.gui.als_explorer import AlsExplorerPanel
        from cratedig.db.models import Sample

        app = QApplication.instance() or QApplication([])
        panel = AlsExplorerPanel()

        # Create match result with list-of-samples found entry
        samples = [
            _make_sample(1, "/packs/drums/kick_v1.wav"),
            _make_sample(2, "/packs/drums/kick_v2.wav"),
        ]
        result = {
            "found": [("kick.wav", samples)],
            "candidates": [],
            "unresolved": [],
        }

        panel.set_match_result(result)

        name, entry = result["found"][0]

        # Reveal should use first sample
        received_reveal = []
        panel.reveal_requested.connect(lambda p: received_reveal.append(p))
        panel._emit_reveal_for(entry)

        assert len(received_reveal) == 1
        assert received_reveal[0] == "/packs/drums/kick_v1.wav"

        # Add to crate should use first sample
        received_add = []
        panel.add_to_crate_requested.connect(
            lambda s, c_id: received_add.append((s, c_id))
        )
        panel._emit_add_to_crate_for(entry, 10)

        assert len(received_add) == 1
        emitted_sample, emitted_crate_id = received_add[0]
        assert isinstance(emitted_sample, Sample)
        assert emitted_sample.path == "/packs/drums/kick_v1.wav"

        # Create crate should use first sample
        received_create = []
        panel.create_crate_requested.connect(lambda s: received_create.append(s))
        panel._emit_create_crate_for(entry)

        assert len(received_create) == 1
        emitted_sample = received_create[0]
        assert isinstance(emitted_sample, Sample)
        assert emitted_sample.path == "/packs/drums/kick_v1.wav"

        panel.close()

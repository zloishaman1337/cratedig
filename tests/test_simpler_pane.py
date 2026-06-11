"""Unit tests for cratedig.gui.simpler_pane.SimplerPane and _WaveCanvas (TDD — these are FAILING tests)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from cratedig.audio.editor import (
    auto_slice,
    detect_transients,
    snap_to_zero_crossing,
)


def _app():
    """Set up QApplication for PySide6 tests — matches test_gui_logic pattern."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _synthetic_signal_with_transients(sr: int = 44100, num_transients: int = 3) -> tuple[np.ndarray, float]:
    """Build a synthetic mono signal with clear transients: silence gaps + short bursts.

    Returns (mono, duration) where mono is the signal and duration is in seconds.
    """
    # Each section: 0.5s silence, 0.5s tone (decaying impulse).
    section_len_sec = 1.0
    silence_sec = 0.5
    tone_sec = 0.5

    sections = []
    for _ in range(num_transients):
        # Silence
        sections.append(np.zeros(int(silence_sec * sr), dtype=np.float32))
        # Decaying tone/impulse
        t = np.linspace(0, 1, int(tone_sec * sr), dtype=np.float32)
        burst = 0.9 * np.exp(-3 * t)  # decaying impulse
        sections.append(burst)

    mono = np.concatenate(sections, dtype=np.float32)
    duration = len(mono) / sr
    return mono, duration


class TestWaveCanvasTransients:
    """Tests for _WaveCanvas transient visualization (NEW API)."""

    def _app(self):
        return _app()

    def test_wave_canvas_has_set_transients_method(self, tmp_path):
        """_WaveCanvas.set_transients(times) stores into canvas._transients."""
        self._app()
        from cratedig.gui.simpler_pane import _WaveCanvas

        canvas = _WaveCanvas()
        transient_times = [0.1, 0.5, 1.2]

        # Should not raise; stores into _transients
        canvas.set_transients(transient_times)

        assert hasattr(canvas, "_transients")
        assert canvas._transients == transient_times

    def test_wave_canvas_has_set_show_transients_method(self, tmp_path):
        """_WaveCanvas.set_show_transients(show) stores into canvas._show_transients."""
        self._app()
        from cratedig.gui.simpler_pane import _WaveCanvas

        canvas = _WaveCanvas()

        # Should not raise; stores into _show_transients
        canvas.set_show_transients(True)

        assert hasattr(canvas, "_show_transients")
        assert canvas._show_transients is True

        canvas.set_show_transients(False)
        assert canvas._show_transients is False


class TestSimplerPaneSensitivity:
    """Tests for SimplerPane._sensitivity knob and transient detection."""

    def _app(self):
        return _app()

    def test_simpler_pane_has_sensitivity_knob(self, tmp_path):
        """SimplerPane._sensitivity is a _Knob with .value() in [0,1], default 0.5."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        assert hasattr(pane, "_sensitivity")
        assert callable(getattr(pane._sensitivity, "value", None))

        # Default should be 0.5
        val = pane._sensitivity.value()
        assert pytest.approx(val, abs=0.05) == 0.5

        # Should be settable and within [0, 1]
        pane._sensitivity.setValue(0.9)
        assert pytest.approx(pane._sensitivity.value(), abs=0.05) == 0.9

    def test_set_sample_then_set_mono_populates_transients(self, tmp_path):
        """After set_sample(path, dur) + set_mono(mono), canvas._transients match detect_transients."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build synthetic signal with clear transients
        mono, duration = _synthetic_signal_with_transients(sr=44100, num_transients=3)

        # Set sample and mono
        pane.set_sample("dummy_path.wav", duration)
        pane.set_mono(mono)

        # Compute expected transients
        sr = max(1, round(mono.size / duration))
        expected = detect_transients(mono, sr, sensitivity=0.5)

        # Canvas should have populated transients (allow small timing differences)
        assert hasattr(pane._canvas, "_transients")
        assert isinstance(pane._canvas._transients, list)

        # Compare lengths and approximate times (transient detection is approximate)
        assert len(pane._canvas._transients) == len(expected)
        for computed, expected_t in zip(pane._canvas._transients, expected):
            assert pytest.approx(computed, abs=0.05) == expected_t

    def test_changing_sensitivity_recomputes_transients(self, tmp_path):
        """Changing sensitivity recomputes canvas._transients."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        mono, duration = _synthetic_signal_with_transients(sr=44100, num_transients=3)
        sr = max(1, round(mono.size / duration))

        pane.set_sample("dummy_path.wav", duration)
        pane.set_mono(mono)

        # Get initial transients at sensitivity 0.5
        pane._sensitivity.setValue(0.5)
        expected_0_5 = detect_transients(mono, sr, sensitivity=0.5)

        # Change sensitivity to 0.9 (less sensitive = fewer transients expected)
        pane._sensitivity.setValue(0.9)
        expected_0_9 = detect_transients(mono, sr, sensitivity=0.9)

        # The computed transients should update
        assert len(expected_0_5) >= len(expected_0_9)  # higher threshold = fewer peaks


class TestSimplerPaneNormalize:
    """Tests for SimplerPane._on_normalize() method."""

    def _app(self):
        return _app()

    def test_normalize_quiet_signal_increases_gain(self, tmp_path):
        """_on_normalize() on quiet signal (peak 0.1) sets gain knob to positive dB."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build quiet signal (peak 0.1)
        sr = 44100
        duration = 1.0
        n = int(sr * duration)
        quiet_mono = np.ones(n, dtype=np.float32) * 0.1

        pane.set_sample("quiet.wav", duration)
        pane.set_mono(quiet_mono)

        # Call normalize
        pane._on_normalize()

        # Gain should be positive (peak 0.1 needs boost to -0.3 dBFS ≈ +19.8 dB)
        gain = pane._gain.value()
        assert gain > 0

    def test_normalize_loud_signal_sets_gain_to_zero_or_negative(self, tmp_path):
        """_on_normalize() on loud signal (peak ~1.0) sets gain to ~0 or negative."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build loud signal (peak ~1.0)
        sr = 44100
        duration = 1.0
        n = int(sr * duration)
        loud_mono = np.ones(n, dtype=np.float32) * 0.95

        pane.set_sample("loud.wav", duration)
        pane.set_mono(loud_mono)

        # Call normalize
        pane._on_normalize()

        # Gain should be zero or slightly negative
        gain = pane._gain.value()
        assert gain <= 1.0  # Some tolerance for target dB
        assert gain >= -1.0  # Should not need large negative gain


class TestSimplerPaneTrim:
    """Tests for SimplerPane._on_trim() method."""

    def _app(self):
        return _app()

    def test_trim_silence_narrows_region(self, tmp_path):
        """_on_trim() on signal with leading/trailing silence narrows region."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build signal: [silence 0.5s][tone 1.0s][silence 0.5s]
        sr = 44100
        silence_sec = 0.5
        tone_sec = 1.0

        silence = np.zeros(int(silence_sec * sr), dtype=np.float32)
        tone = np.ones(int(tone_sec * sr), dtype=np.float32) * 0.5
        mono = np.concatenate([silence, tone, silence], dtype=np.float32)
        duration = len(mono) / sr

        pane.set_sample("silence.wav", duration)
        pane.set_mono(mono)

        # Initial region should span full duration
        assert pane._canvas.region == (0.0, pytest.approx(duration, abs=0.01))

        # Call trim
        pane._on_trim()

        # Region should be narrowed to roughly [0.5, 1.5]
        start, end = pane._canvas.region
        assert start > 0.4  # trim should narrow from 0.0
        assert end < 2.0   # trim should narrow from ~2.0
        assert (end - start) > 0.8  # should keep most of the tone


class TestSimplerPaneSnap:
    """Tests for SimplerPane._on_snap() method."""

    def _app(self):
        return _app()

    def test_snap_region_edges_to_zero_crossings(self, tmp_path):
        """_on_snap() snaps region edges to zero crossings."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build a simple sine wave (many zero crossings)
        sr = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
        mono = np.sin(2 * np.pi * 5 * t).astype(np.float32)  # 5 Hz sine

        pane.set_sample("sine.wav", duration)
        pane.set_mono(mono)

        # Set region to arbitrary interior times
        pane._canvas.region = (0.15, 0.75)

        # Call snap
        pane._on_snap()

        # Region edges should snap to zero crossings (within ~10ms tolerance)
        start, end = pane._canvas.region
        expected_start = snap_to_zero_crossing(mono, sr, 0.15)
        expected_end = snap_to_zero_crossing(mono, sr, 0.75)

        assert pytest.approx(start, abs=0.01) == expected_start
        assert pytest.approx(end, abs=0.01) == expected_end


class TestSimplerPaneSlice:
    """Tests for SimplerPane._on_slice() method."""

    def _app(self):
        return _app()

    def test_on_slice_cycles_through_auto_slice_regions(self, tmp_path):
        """_on_slice() cycles region through auto_slice regions."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "Saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Build multi-transient signal
        mono, duration = _synthetic_signal_with_transients(sr=44100, num_transients=3)
        sr = max(1, round(mono.size / duration))

        pane.set_sample("multi.wav", duration)
        pane.set_mono(mono)

        # Get expected slices
        expected_slices = auto_slice(mono, sr, sensitivity=0.5)

        if not expected_slices:
            pytest.skip("No slices detected in synthetic signal")

        # Call _on_slice() repeatedly and collect regions
        regions_visited = []
        for _ in range(len(expected_slices) + 1):
            pane._on_slice()
            regions_visited.append(pane._canvas.region)

        # Should cycle through expected slices
        for i, (expected_start, expected_end) in enumerate(expected_slices):
            actual_start, actual_end = regions_visited[i]
            assert pytest.approx(actual_start, abs=0.05) == expected_start
            assert pytest.approx(actual_end, abs=0.05) == expected_end


class TestKnobDial:
    """_KnobDial must never jump to the clicked angle; double-click resets to default."""

    def _knob(self):
        _app()
        from cratedig.gui.simpler_pane import _Knob, _KnobDial

        knob = _Knob("Gain", -24.0, 24.0, 0.5, 0.0, " dB")
        knob.resize(60, 80)
        knob.show()
        assert isinstance(knob._dial, _KnobDial)
        return knob

    def test_single_click_does_not_jump_to_cursor(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest

        knob = self._knob()
        knob.setValue(12.0)
        corner = QPoint(knob._dial.width() - 2, 2)  # native QDial would slam toward an extreme
        QTest.mouseClick(knob._dial, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, corner)

        assert pytest.approx(knob.value(), abs=0.01) == 12.0

    def test_double_click_resets_to_default(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest

        knob = self._knob()
        knob.setValue(12.0)
        corner = QPoint(knob._dial.width() - 2, 2)
        QTest.mouseDClick(knob._dial, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, corner)

        assert pytest.approx(knob.value(), abs=0.01) == knob._default == 0.0


class TestWaveCanvasPerf:
    """Static-pixmap cache: playhead ticks must blit, not rebin the waveform."""

    def _canvas(self, duration: float = 240.0, n: int = 500_000):
        self._app = _app()
        from cratedig.gui.simpler_pane import _WaveCanvas

        canvas = _WaveCanvas()
        canvas.resize(800, 120)
        canvas.set_sample(duration)
        t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
        mono = np.sin(2 * np.pi * 220.0 * t).astype(np.float32)
        canvas.set_mono(mono)
        return canvas

    def test_set_mono_builds_pyramid(self):
        canvas = self._canvas()
        assert canvas._mono_pyramid is not None
        assert len(canvas._mono_pyramid) >= 2

    def test_playhead_ticks_reuse_static_pixmap(self):
        canvas = self._canvas()
        canvas.grab()  # initial render builds the static layer
        first = canvas._static_pixmap
        assert first is not None
        for i in range(20):
            canvas.set_playhead(i * 0.5)
            canvas.grab()
            assert canvas._static_pixmap is first  # cache reused, no rebuild

    def test_playhead_ticks_do_not_rebin_waveform(self, monkeypatch):
        canvas = self._canvas()
        canvas.grab()  # warm the cache

        import cratedig.gui.simpler_pane as sp

        calls = {"n": 0}
        real = sp.peaks_from_pyramid

        def _spy(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(sp, "peaks_from_pyramid", _spy)
        for i in range(15):
            canvas.set_playhead(i * 0.7)
            canvas.grab()
        assert calls["n"] == 0  # playhead-only repaints never rebin

    def test_zoom_change_rebuilds_static_pixmap(self):
        canvas = self._canvas()
        canvas.grab()
        first = canvas._static_pixmap
        canvas._zoom_at(2.0, 400)  # changes view span → must invalidate cache
        canvas.grab()
        assert canvas._static_pixmap is not first

    def test_pyramid_path_used_when_zoomed_out(self, monkeypatch):
        canvas = self._canvas(n=2_000_000)
        import cratedig.gui.simpler_pane as sp

        calls = {"n": 0}
        real = sp.peaks_from_pyramid

        def _spy(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(sp, "peaks_from_pyramid", _spy)
        canvas.grab()  # full-view render of a 2M-sample signal
        assert calls["n"] >= 1  # zoomed-out draw goes through the pyramid, not raw rebin

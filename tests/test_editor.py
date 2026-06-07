"""Unit tests for the pure DSP sample editor (audio/editor.py)."""

from __future__ import annotations

import numpy as np
import pytest

from cratedig.audio.editor import (
    ADSR,
    apply_edit,
    auto_slice,
    detect_transients,
    normalize_peak,
    render_edit,
    snap_to_zero_crossing,
    trim_silence,
    write_wav,
)

SR = 1000


def _ramp_buf(n: int = SR) -> np.ndarray:
    """1-D buffer of 1.0s (constant) for envelope inspection."""
    return np.ones(n, dtype=np.float32)


# ---------------------------------------------------------------------------
# Existing tests (kept intact)
# ---------------------------------------------------------------------------

def test_region_crop_bounds():
    buf = np.arange(SR, dtype=np.float32)
    out = apply_edit(buf, SR, region=(0.1, 0.3))
    assert out.shape[0] == 200  # 0.2s * 1000
    assert out[0] == pytest.approx(100.0)
    assert out[-1] == pytest.approx(299.0)


def test_region_clamped_and_sorted():
    buf = _ramp_buf()
    # reversed + out-of-range region is sorted and clamped to buffer length
    out = apply_edit(buf, SR, region=(5.0, -1.0))
    assert out.shape[0] == SR


def test_reverse():
    buf = np.arange(5, dtype=np.float32)
    out = apply_edit(buf, SR, reverse=True)
    assert np.array_equal(out, buf[::-1])


def test_gain_db():
    buf = _ramp_buf(10)
    out = apply_edit(buf, SR, gain_db=6.0)
    assert out[0] == pytest.approx(10.0 ** (6.0 / 20.0), rel=1e-4)


def test_gain_zero_is_noop():
    buf = np.linspace(-1, 1, 50, dtype=np.float32)
    out = apply_edit(buf, SR, gain_db=0.0)
    assert np.allclose(out, buf)


def test_fade_in_ramp():
    buf = _ramp_buf(SR)
    out = apply_edit(buf, SR, fade_in=0.1)  # 100 frames ramp 0→1
    assert out[0] == pytest.approx(0.0)
    assert out[99] == pytest.approx(1.0, abs=1e-3)
    assert out[100] == pytest.approx(1.0)


def test_fade_out_ramp():
    buf = _ramp_buf(SR)
    out = apply_edit(buf, SR, fade_out=0.1)  # last 100 frames ramp 1→0
    assert out[-1] == pytest.approx(0.0)
    assert out[0] == pytest.approx(1.0)


def test_adsr_shape():
    buf = _ramp_buf(SR)
    adsr = ADSR(attack=0.1, decay=0.1, sustain=0.5, release=0.1)
    out = apply_edit(buf, SR, adsr=adsr)
    assert out[0] == pytest.approx(0.0)            # attack start
    assert out[99] == pytest.approx(1.0, abs=1e-2)  # attack peak
    assert out[-1] == pytest.approx(0.0)           # release end
    # sustain region in the middle sits at the sustain level
    assert out[500] == pytest.approx(0.5, abs=1e-2)


def test_adsr_inactive_default():
    buf = _ramp_buf(20)
    out = apply_edit(buf, SR, adsr=ADSR())  # all-default → no-op
    assert np.allclose(out, buf)


def test_stereo_preserved():
    buf = np.ones((SR, 2), dtype=np.float32)
    out = apply_edit(buf, SR, fade_in=0.1, gain_db=0.0)
    assert out.shape == (SR, 2)
    assert out[0, 0] == pytest.approx(0.0)
    assert out[0, 1] == pytest.approx(0.0)
    assert out[-1, 0] == pytest.approx(1.0)


def test_empty_buffer():
    assert apply_edit(np.empty(0, dtype=np.float32), SR).size == 0


def test_chain_order_region_then_reverse():
    buf = np.arange(10, dtype=np.float32)
    out = apply_edit(buf, SR, region=(0.0, 0.005), reverse=True)
    # region keeps frames [0,5), reverse flips → [4,3,2,1,0]
    assert np.array_equal(out, np.array([4, 3, 2, 1, 0], dtype=np.float32))


def test_write_and_render_roundtrip(tmp_path):
    sf = pytest.importorskip("soundfile")
    buf = np.linspace(-0.5, 0.5, 200, dtype=np.float32)
    dest = tmp_path / "out.wav"
    written = write_wav(buf, SR, dest)
    assert written == dest and dest.is_file()

    edited, sr = render_edit(dest, region=(0.0, 0.1), reverse=True)
    assert sr == SR
    assert edited.shape[0] == 100


def test_write_creates_parent(tmp_path):
    pytest.importorskip("soundfile")
    dest = tmp_path / "nested" / "deep" / "out.wav"
    write_wav(np.zeros(10, dtype=np.float32), SR, dest)
    assert dest.is_file()


# ---------------------------------------------------------------------------
# detect_transients
# ---------------------------------------------------------------------------

def _impulse_signal(sr: int, times: list[float], total_sec: float = 2.0) -> np.ndarray:
    """Silence with a unit impulse at each listed time (in seconds)."""
    n = int(sr * total_sec)
    sig = np.zeros(n, dtype=np.float32)
    for t in times:
        idx = int(round(t * sr))
        if 0 <= idx < n:
            sig[idx] = 1.0
    return sig


def test_detect_transients_finds_n_impulses():
    sr = 22050
    impulse_times = [0.2, 0.5, 0.8, 1.2]
    sig = _impulse_signal(sr, impulse_times, total_sec=1.5)

    onsets = detect_transients(sig, sr, sensitivity=0.3)

    # Should find approximately the right number of onsets
    assert len(onsets) == len(impulse_times)


def test_detect_transients_onset_times_near_impulses():
    sr = 22050
    impulse_times = [0.3, 0.7, 1.1]
    sig = _impulse_signal(sr, impulse_times, total_sec=1.5)

    onsets = detect_transients(sig, sr, sensitivity=0.3)

    assert len(onsets) == len(impulse_times)
    for expected, got in zip(impulse_times, onsets):
        assert abs(got - expected) < 0.05, f"onset {got:.3f} too far from expected {expected:.3f}"


def test_detect_transients_empty_signal_returns_empty():
    assert detect_transients(np.array([], dtype=np.float32), 22050) == []


def test_detect_transients_zero_signal_returns_empty():
    sig = np.zeros(22050, dtype=np.float32)
    assert detect_transients(sig, 22050) == []


def test_detect_transients_is_deterministic():
    sr = 22050
    sig = _impulse_signal(sr, [0.2, 0.6, 1.0], total_sec=1.5)

    onsets1 = detect_transients(sig, sr)
    onsets2 = detect_transients(sig, sr)

    assert onsets1 == onsets2


def test_detect_transients_returns_ascending_times():
    sr = 22050
    sig = _impulse_signal(sr, [0.1, 0.4, 0.8], total_sec=1.2)

    onsets = detect_transients(sig, sr, sensitivity=0.3)

    assert onsets == sorted(onsets)


# ---------------------------------------------------------------------------
# normalize_peak
# ---------------------------------------------------------------------------

def test_normalize_peak_hits_target_db():
    buf = np.array([0.1, -0.5, 0.3, 0.2], dtype=np.float32)
    target_db = -0.3
    out = normalize_peak(buf, target_db=target_db)

    expected_peak = 10.0 ** (target_db / 20.0)
    assert float(np.max(np.abs(out))) == pytest.approx(expected_peak, rel=1e-5)


def test_normalize_peak_silent_buffer_unchanged():
    buf = np.zeros(100, dtype=np.float32)
    out = normalize_peak(buf, target_db=-0.3)

    assert np.allclose(out, buf)


def test_normalize_peak_preserves_stereo_shape():
    buf = np.random.default_rng(42).random((512, 2)).astype(np.float32) * 0.5
    out = normalize_peak(buf, target_db=-1.0)

    assert out.shape == (512, 2)
    expected_peak = 10.0 ** (-1.0 / 20.0)
    assert float(np.max(np.abs(out))) == pytest.approx(expected_peak, rel=1e-5)


def test_normalize_peak_empty_buffer():
    buf = np.empty(0, dtype=np.float32)
    out = normalize_peak(buf)

    assert out.size == 0


def test_normalize_peak_returns_float32():
    buf = np.ones(10, dtype=np.float64)
    out = normalize_peak(buf)

    assert out.dtype == np.float32


# ---------------------------------------------------------------------------
# trim_silence
# ---------------------------------------------------------------------------

def _silence_tone_silence(sr: int, sil_sec: float = 0.2, tone_sec: float = 0.5) -> np.ndarray:
    """Build: silence + 440 Hz tone + silence."""
    sil = np.zeros(int(sr * sil_sec), dtype=np.float32)
    t = np.linspace(0, tone_sec, int(sr * tone_sec), endpoint=False, dtype=np.float32)
    tone = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    return np.concatenate([sil, tone, sil])


def test_trim_silence_trims_leading_and_trailing():
    sr = 22050
    buf = _silence_tone_silence(sr)

    trimmed, start_sec, end_sec = trim_silence(buf, sr)

    assert len(trimmed) < len(buf)
    assert start_sec > 0.0
    assert end_sec < len(buf) / sr


def test_trim_silence_all_silence_returns_empty():
    sr = 22050
    buf = np.zeros(sr, dtype=np.float32)

    trimmed, start_sec, end_sec = trim_silence(buf, sr)

    assert trimmed.size == 0
    assert start_sec == 0.0
    assert end_sec == 0.0


def test_trim_silence_empty_input_returns_empty():
    trimmed, start_sec, end_sec = trim_silence(np.empty(0, dtype=np.float32), 22050)

    assert trimmed.size == 0
    assert start_sec == 0.0
    assert end_sec == 0.0


def test_trim_silence_stereo_shape_preserved():
    sr = 22050
    sil = np.zeros((int(sr * 0.1), 2), dtype=np.float32)
    t = np.linspace(0, 0.3, int(sr * 0.3), endpoint=False, dtype=np.float32)
    tone = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    tone_stereo = np.column_stack([tone, tone])
    buf = np.concatenate([sil, tone_stereo, sil], axis=0)

    trimmed, start_sec, end_sec = trim_silence(buf, sr)

    assert trimmed.ndim == 2
    assert trimmed.shape[1] == 2
    assert trimmed.shape[0] < buf.shape[0]


# ---------------------------------------------------------------------------
# snap_to_zero_crossing
# ---------------------------------------------------------------------------

def test_snap_to_zero_crossing_finds_crossing():
    sr = 44100
    freq = 440.0
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    sine = np.sin(2 * np.pi * freq * t).astype(np.float32)

    # The sine crosses zero at integer multiples of 1/(2*freq).
    true_crossing = 1.0 / (2.0 * freq)  # first zero crossing after t=0 (ascending)
    t_query = true_crossing + 0.0005  # slightly off

    snapped = snap_to_zero_crossing(sine, sr, t_query, window_sec=0.005)

    assert abs(snapped - true_crossing) < abs(t_query - true_crossing) or abs(snapped - true_crossing) < 0.001


def test_snap_to_zero_crossing_no_crossing_in_window_returns_t():
    # DC signal — no zero crossings anywhere
    sr = 22050
    dc = np.ones(sr, dtype=np.float32)

    t = 0.5
    result = snap_to_zero_crossing(dc, sr, t, window_sec=0.005)

    # No crossing found; result is the clamped t
    assert result == pytest.approx(t, abs=1.0 / sr)


def test_snap_to_zero_crossing_empty_signal_returns_t():
    result = snap_to_zero_crossing(np.array([], dtype=np.float32), 22050, 0.5)

    assert result == 0.5


def test_snap_to_zero_crossing_result_within_window():
    sr = 44100
    freq = 440.0
    t_arr = np.linspace(0, 2.0, sr * 2, endpoint=False, dtype=np.float32)
    sine = np.sin(2 * np.pi * freq * t_arr).astype(np.float32)

    t_query = 0.7
    window = 0.005
    snapped = snap_to_zero_crossing(sine, sr, t_query, window_sec=window)

    assert abs(snapped - t_query) <= window + 1.0 / sr


# ---------------------------------------------------------------------------
# auto_slice
# ---------------------------------------------------------------------------

def test_auto_slice_three_impulses_returns_three_slices():
    sr = 22050
    sig = _impulse_signal(sr, [0.2, 0.5, 0.8], total_sec=1.2)

    slices = auto_slice(sig, sr, sensitivity=0.3)

    assert len(slices) == 3


def test_auto_slice_last_slice_ends_at_duration():
    sr = 22050
    total = 1.2
    sig = _impulse_signal(sr, [0.2, 0.6], total_sec=total)

    slices = auto_slice(sig, sr, sensitivity=0.3)

    assert slices[-1][1] == pytest.approx(total, abs=0.02)


def test_auto_slice_flat_signal_returns_single_full_slice():
    sr = 22050
    sig = np.ones(sr, dtype=np.float32)  # no transients
    duration = float(len(sig)) / sr

    slices = auto_slice(sig, sr)

    assert slices == [(0.0, duration)]


def test_auto_slice_empty_signal_returns_empty():
    assert auto_slice(np.empty(0, dtype=np.float32), 22050) == []


def test_auto_slice_slices_cover_full_duration():
    sr = 22050
    total = 1.5
    sig = _impulse_signal(sr, [0.3, 0.7, 1.1], total_sec=total)

    slices = auto_slice(sig, sr, sensitivity=0.3)

    # Each start == previous end
    for i in range(1, len(slices)):
        assert slices[i][0] == pytest.approx(slices[i - 1][1], abs=0.02)


# ---------------------------------------------------------------------------
# BUG A: fade_envelope overlap tests (failing)
# ---------------------------------------------------------------------------
# These tests demonstrate the bug in _fade_envelope where fade_in and fade_out
# can overlap when their sum exceeds the buffer length, causing both ramps to
# compound-attenuate the middle samples.


def test_fade_overlap_no_compound_attenuation_in_middle():
    """Bug A: fade_in+fade_out>n causes middle samples to be attenuated by both ramps.

    When fade_in=0.08 and fade_out=0.08 on a 0.1s buffer (100 frames @ SR=1000),
    both ramps try to occupy 80 frames. They overlap in the middle, and the
    multiply-in-place operation on line 73 causes compound attenuation.

    After the fix (fo = min(fo, n - fi)), fade_out gets clamped to 20 frames,
    so there's no overlap. The key assertion: no sample should be the product of
    both ramps (i.e., attenuated below a single fade ramp).
    """
    N = 100  # 0.1 seconds at SR=1000
    buf = _ramp_buf(N)
    fade_in_sec = 0.08   # 80 frames
    fade_out_sec = 0.08  # would be 80 frames, but should clamp to N - 80 = 20

    out = apply_edit(buf, SR, fade_in=fade_in_sec, fade_out=fade_out_sec)

    # fade-in region (first 80 frames) follows a single 0->1 ramp; the bug
    # multiplied the fade-out ramp in here too, pulling these values down.
    for i in range(80):
        assert out[i] == pytest.approx(i / 79.0, abs=1e-2), \
            f"FAIL: fade-in frame {i} {out[i]:.4f} not single ramp i/79 (overlap bug)"
    # boundary reaches full level (start of the 20-frame fade-out), not double-attenuated
    assert out[79] == pytest.approx(1.0, abs=1e-3)
    assert out[80] == pytest.approx(1.0, abs=1e-3)
    # fade-out tail is monotonically non-increasing (single ramp, no compounding)
    for i in range(81, 100):
        assert out[i] <= out[i - 1] + 1e-6


def test_fade_overlap_tail_not_dipped():
    """Bug A: when fi+fo>n, the tail should not dip toward 0 due to compound attenuation.

    Currently, the bug causes the tail to dip because both the end of the fade_in
    ramp and the start of the fade_out ramp overlap and multiply together.
    Frame 80 should be ~1.0 (start of fade_out), but with overlap it's much lower.
    """
    N = 100
    buf = _ramp_buf(N)
    fade_in_sec = 0.08
    fade_out_sec = 0.08

    out = apply_edit(buf, SR, fade_in=fade_in_sec, fade_out=fade_out_sec)

    # This assertion will fail (red) with the current bug:
    # Frame 80 should be at least 0.5 (no overlap attenuation).
    assert out[80] > 0.5, \
        f"FAIL: frame 80 {out[80]:.4f} should be > 0.5 (no overlap attenuation)"


def test_fade_in_consumes_whole_buffer_forces_fade_out_to_zero():
    """Bug A edge case: when fade_in fills the entire buffer, fade_out must be 0.

    After the fix (fo = min(fo, n - fi)), if fi == n, then fo = 0, so the buffer
    is only attenuated by the fade_in ramp, and the tail stays at 1.0.
    """
    N = 100
    buf = _ramp_buf(N)
    fade_in_sec = 0.1    # Exactly 100 frames, fills the whole buffer
    fade_out_sec = 0.05  # Would be 50 frames, but should clamp to 0

    out = apply_edit(buf, SR, fade_in=fade_in_sec, fade_out=fade_out_sec)

    # With the fix: out[-1] should be close to 1.0 (end of fade_in ramp)
    # With the bug: out[-1] would be much lower due to overlap
    # This test should FAIL (red) with the current code:
    assert out[-1] == pytest.approx(1.0, abs=1e-3), \
        f"FAIL: with fi==n and fix applied, fade_out should be 0, so out[-1] ~= 1.0; got {out[-1]:.4f}"

    # All samples should follow the fade_in ramp (0→1), no dip at the tail.
    # linspace(0,1,N) is endpoint-inclusive, so frame i == i/(N-1).
    for i in range(N):
        expected = float(i) / (N - 1)
        assert out[i] == pytest.approx(expected, abs=1e-3), \
            f"FAIL: frame {i} should follow fade-in ramp; got {out[i]:.4f}, expected {expected:.4f}"

"""Pure DSP sample editor: region/reverse/gain/fade/ADSR rendering.

No Qt, no ffmpeg. numpy + soundfile only, so every transform is unit-testable
on synthetic buffers. The GUI Simpler pane renders edits through here, writes a
temp WAV, and plays that (ffplay cannot play a numpy buffer).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ADSR:
    """Attack/Decay/Release in seconds; sustain is a 0..1 level."""

    attack: float = 0.0
    decay: float = 0.0
    sustain: float = 1.0
    release: float = 0.0

    @property
    def active(self) -> bool:
        return self.attack > 0 or self.decay > 0 or self.release > 0 or self.sustain != 1.0


def _ramp(n: int, start: float, stop: float) -> np.ndarray:
    if n <= 0:
        return np.empty(0, dtype=np.float32)
    return np.linspace(start, stop, n, dtype=np.float32)


def _adsr_envelope(n: int, sr: int, adsr: ADSR) -> np.ndarray:
    """Build an n-frame ADSR gain envelope.

    Attack rises 0→1, decay falls 1→sustain, sustain holds, release falls
    sustain→0 at the tail. Stage frame counts are clamped so they never exceed n
    (release wins the tail, then attack, then decay; sustain fills the rest).
    """
    env = np.full(n, float(adsr.sustain), dtype=np.float32)
    if n <= 0:
        return env

    a_n = min(n, int(round(adsr.attack * sr)))
    r_n = min(n - a_n, int(round(adsr.release * sr)))
    d_n = min(n - a_n - r_n, int(round(adsr.decay * sr)))

    pos = 0
    if a_n > 0:
        env[pos:pos + a_n] = _ramp(a_n, 0.0, 1.0)
        pos += a_n
    if d_n > 0:
        env[pos:pos + d_n] = _ramp(d_n, 1.0, adsr.sustain)
        pos += d_n
    # sustain region stays at adsr.sustain (already filled)
    if r_n > 0:
        env[n - r_n:] = _ramp(r_n, adsr.sustain, 0.0)
    return env


def _fade_envelope(n: int, sr: int, fade_in: float, fade_out: float) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    if n <= 0:
        return env
    fi = min(n, int(round(fade_in * sr)))
    fo = min(n - fi, int(round(fade_out * sr)))
    if fi > 0:
        env[:fi] = _ramp(fi, 0.0, 1.0)
    if fo > 0:
        env[n - fo:] *= _ramp(fo, 1.0, 0.0)
    return env


def _apply_gain_env(audio: np.ndarray, env: np.ndarray) -> np.ndarray:
    """Multiply a (frames,) envelope across a mono or (frames, channels) buffer."""
    if audio.ndim == 1:
        return audio * env
    return audio * env[:, None]


def apply_edit(
    audio: np.ndarray,
    sr: int,
    region: tuple[float, float] | None = None,
    *,
    reverse: bool = False,
    gain_db: float = 0.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    adsr: ADSR | None = None,
) -> np.ndarray:
    """Apply the edit chain to a float buffer and return a new float32 buffer.

    Order: region crop → reverse → gain → fade in/out → ADSR. `audio` may be 1-D
    mono or 2-D (frames, channels); the shape is preserved.
    """
    buf = np.asarray(audio, dtype=np.float32)
    if buf.size == 0:
        return buf.copy()

    n_frames = buf.shape[0]
    if region is not None:
        start_sec, end_sec = sorted(region)
        a = max(0, min(n_frames, int(round(start_sec * sr))))
        b = max(a, min(n_frames, int(round(end_sec * sr))))
        buf = buf[a:b]
    buf = np.array(buf, dtype=np.float32, copy=True)

    if buf.shape[0] == 0:
        return buf

    if reverse:
        buf = buf[::-1]

    if gain_db != 0.0:
        buf = buf * np.float32(10.0 ** (gain_db / 20.0))

    n = buf.shape[0]
    if fade_in > 0 or fade_out > 0:
        buf = _apply_gain_env(buf, _fade_envelope(n, sr, fade_in, fade_out))

    if adsr is not None and adsr.active:
        buf = _apply_gain_env(buf, _adsr_envelope(n, sr, adsr))

    return np.ascontiguousarray(buf, dtype=np.float32)


def render_edit(
    path: str | Path,
    region: tuple[float, float] | None = None,
    *,
    reverse: bool = False,
    gain_db: float = 0.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    adsr: ADSR | None = None,
) -> tuple[np.ndarray, int]:
    """Read `path` with soundfile and apply the edit chain. Returns (buffer, sr)."""
    import soundfile as sf

    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    edited = apply_edit(
        audio,
        sr,
        region,
        reverse=reverse,
        gain_db=gain_db,
        fade_in=fade_in,
        fade_out=fade_out,
        adsr=adsr,
    )
    return edited, int(sr)


def default_export_name(src_path: str | Path) -> str:
    """Timestamped export filename for an edit of `src_path` (e.g. kick_edit_142530.wav)."""
    from datetime import datetime

    return f"{Path(src_path).stem}_edit_{datetime.now().strftime('%H%M%S')}.wav"


def dated_export_dir(saved_dir: str | Path) -> Path:
    """Return today's Saved subfolder using DD_MM_YYYY."""
    from datetime import datetime

    return Path(saved_dir) / datetime.now().strftime("%d_%m_%Y")


def write_wav(buffer: np.ndarray, sr: int, dest: str | Path) -> Path:
    """Write a float buffer to `dest` as a WAV; create parent dirs. Returns dest."""
    import soundfile as sf

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dest), np.asarray(buffer, dtype=np.float32), sr)
    return dest


# ---------------------------------------------------------------------------
# Analysis / processing helpers for Simpler pane
# ---------------------------------------------------------------------------

def _frames_rms(mono: np.ndarray, hop: int, win: int) -> np.ndarray:
    """Return per-frame RMS for a 1-D float32 signal using strided views."""
    n = len(mono)
    if n == 0 or hop <= 0 or win <= 0:
        return np.empty(0, dtype=np.float32)
    # Pad so the last frame is complete.
    pad = win - 1
    padded = np.pad(mono, (0, pad), mode="constant")
    n_frames = (n + hop - 1) // hop
    shape = (n_frames, win)
    strides = (padded.strides[0] * hop, padded.strides[0])
    frames = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
    return np.sqrt(np.mean(frames ** 2, axis=1)).astype(np.float32)


def detect_transients(
    mono: np.ndarray,
    sr: int,
    *,
    sensitivity: float = 0.5,
    min_gap_sec: float = 0.03,
) -> list[float]:
    """Return transient onset times in seconds (ascending).

    Algorithm: frame the signal with ~10 ms hop / ~20 ms window, compute per-frame
    RMS, take the positive first-difference (spectral-flux proxy), then pick peaks
    above `mean + sensitivity * std` of that novelty curve; enforce `min_gap_sec`
    between accepted peaks.
    """
    mono = np.asarray(mono, dtype=np.float32)
    if mono.ndim != 1 or mono.size == 0 or sr <= 0:
        return []

    hop = max(1, int(round(0.010 * sr)))
    win = max(2, int(round(0.020 * sr)))

    rms = _frames_rms(mono, hop, win)
    if rms.size < 2:
        return []

    # Positive first-difference novelty function.
    novelty = np.diff(rms, prepend=rms[0])
    novelty = np.maximum(novelty, 0.0)

    mean_n = float(np.mean(novelty))
    std_n = float(np.std(novelty))
    threshold = mean_n + sensitivity * std_n

    if threshold <= 0.0 or float(np.max(novelty)) <= 0.0:
        return []

    min_gap_frames = max(1, int(round(min_gap_sec * sr / hop)))

    onsets: list[float] = []
    last_frame = -min_gap_frames
    for i, val in enumerate(novelty):
        if val > threshold and (i - last_frame) >= min_gap_frames:
            onsets.append(float(i * hop) / sr)
            last_frame = i

    return onsets


def normalize_peak(buf: np.ndarray, target_db: float = -0.3) -> np.ndarray:
    """Peak-normalize `buf` so the loudest sample hits `target_db` dBFS.

    Algorithm: find global max-abs, scale linearly. Silent buffers returned as-is.
    Preserves shape; always returns float32.
    """
    buf = np.asarray(buf, dtype=np.float32)
    if buf.size == 0:
        return buf.copy()

    peak = float(np.max(np.abs(buf)))
    if peak < 1e-9:
        return buf.copy()

    target_linear = 10.0 ** (target_db / 20.0)
    return (buf * np.float32(target_linear / peak))


def trim_silence(
    buf: np.ndarray,
    sr: int,
    *,
    threshold_db: float = -40.0,
    pad_sec: float = 0.0,
) -> tuple[np.ndarray, float, float]:
    """Trim leading/trailing silence from `buf`.

    Algorithm: compare per-sample absolute value against `peak * 10**(threshold_db/20)`;
    find first and last sample above that floor; optionally keep `pad_sec` of extra
    audio on each side (clamped to buffer bounds).

    Returns `(trimmed_buf, start_sec, end_sec)` relative to the original buffer.
    All-silent or empty buffer → `(empty_array, 0.0, 0.0)`.
    Works on 1-D mono or 2-D (frames, channels).
    """
    buf = np.asarray(buf, dtype=np.float32)
    empty = np.empty(0, dtype=np.float32)

    if buf.size == 0 or sr <= 0:
        return empty, 0.0, 0.0

    abs_buf = np.abs(buf) if buf.ndim == 1 else np.max(np.abs(buf), axis=1)
    peak = float(np.max(abs_buf))
    if peak < 1e-9:
        return np.empty((0,) + buf.shape[1:], dtype=np.float32), 0.0, 0.0

    floor = peak * (10.0 ** (threshold_db / 20.0))
    above = np.where(abs_buf >= floor)[0]
    if above.size == 0:
        return np.empty((0,) + buf.shape[1:], dtype=np.float32), 0.0, 0.0

    n_frames = buf.shape[0]
    pad_frames = max(0, int(round(pad_sec * sr)))
    start_idx = max(0, int(above[0]) - pad_frames)
    end_idx = min(n_frames, int(above[-1]) + 1 + pad_frames)

    trimmed = np.array(buf[start_idx:end_idx], dtype=np.float32, copy=True)
    return trimmed, float(start_idx) / sr, float(end_idx) / sr


def snap_to_zero_crossing(
    mono: np.ndarray,
    sr: int,
    t: float,
    *,
    window_sec: float = 0.005,
) -> float:
    """Return the time (seconds) of the nearest zero crossing to `t` within ±`window_sec`.

    Algorithm: inspect sign changes (np.diff of np.sign) in the search window; pick
    the crossing whose sample index is closest to the target sample. Returns `t`
    unchanged if no crossing found or input is invalid. Clamps result to [0, duration].
    """
    mono = np.asarray(mono, dtype=np.float32)
    if mono.ndim != 1 or mono.size == 0 or sr <= 0:
        return t

    n = mono.size
    duration = float(n) / sr
    t_clamped = max(0.0, min(duration, t))

    center = int(round(t_clamped * sr))
    half = max(1, int(round(window_sec * sr)))
    lo = max(0, center - half)
    hi = min(n - 1, center + half)

    if lo >= hi:
        return t_clamped

    segment = mono[lo : hi + 1]
    signs = np.sign(segment)
    # Zero-valued samples count as crossings too (sign == 0 → transition point).
    crossings = np.where(np.diff(signs) != 0)[0]
    if crossings.size == 0:
        return t_clamped

    # Each crossing index i means the crossing is between lo+i and lo+i+1; use lo+i.
    crossing_samples = crossings + lo
    nearest_idx = int(crossing_samples[np.argmin(np.abs(crossing_samples - center))])
    return float(nearest_idx) / sr


def auto_slice(
    mono: np.ndarray,
    sr: int,
    *,
    sensitivity: float = 0.5,
    min_gap_sec: float = 0.03,
) -> list[tuple[float, float]]:
    """Build slice regions (start_sec, end_sec) from detected transients.

    Algorithm: delegate to `detect_transients`; zip consecutive onset times into
    (start, end) pairs where each slice runs from one transient to the next, and the
    final slice runs to the end of the buffer. If no transients are found and the
    signal is non-empty, returns a single full-length slice [(0.0, duration)].
    Empty/invalid input → [].
    """
    mono = np.asarray(mono, dtype=np.float32)
    if mono.ndim != 1 or mono.size == 0 or sr <= 0:
        return []

    duration = float(mono.size) / sr
    onsets = detect_transients(mono, sr, sensitivity=sensitivity, min_gap_sec=min_gap_sec)

    if not onsets:
        return [(0.0, duration)]

    boundaries = onsets + [duration]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

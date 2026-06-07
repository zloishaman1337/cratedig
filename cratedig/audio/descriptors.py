"""Pure DSP heuristics for sample character tags."""

# tape / vinyl tags are deliberately omitted — they require ML classification.

from __future__ import annotations

import numpy as np


def _clean_mono(y_mono: np.ndarray) -> np.ndarray:
    y = np.asarray(y_mono, dtype=np.float32).reshape(-1)
    if y.size == 0:
        return y
    return np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)


def _spectrum(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    if y.size < 2 or sr <= 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    window = np.hanning(y.size).astype(np.float32)
    mag = np.abs(np.fft.rfft(y * window)).astype(np.float32)
    freqs = np.fft.rfftfreq(y.size, d=1.0 / sr).astype(np.float32)
    return freqs, mag


def _band_ratio(freqs: np.ndarray, mag: np.ndarray, low: float, high: float) -> float:
    total = float(np.sum(mag) + 1e-9)
    if total <= 1e-9:
        return 0.0
    mask = (freqs >= low) & (freqs < high)
    return float(np.sum(mag[mask]) / total)


def _rolloff(freqs: np.ndarray, mag: np.ndarray, pct: float) -> float:
    total = float(np.sum(mag))
    if total <= 1e-9 or freqs.size == 0:
        return 0.0
    idx = int(np.searchsorted(np.cumsum(mag), total * pct))
    idx = min(idx, freqs.size - 1)
    nyquist = max(float(freqs[-1]), 1.0)
    return float(freqs[idx] / nyquist)


def _flatness(mag: np.ndarray) -> float:
    data = mag.astype(np.float64) + 1e-9
    if data.size == 0:
        return 0.0
    return float(np.exp(np.mean(np.log(data))) / np.mean(data))


def _late_ratio(y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    split = max(1, int(y.size * 0.65))
    early = y[:split]
    late = y[split:]
    early_rms = float(np.sqrt(np.mean(np.square(early)) + 1e-12))
    late_rms = float(np.sqrt(np.mean(np.square(late)) + 1e-12)) if late.size else 0.0
    return late_rms / max(early_rms, 1e-9)


def _decay_position(y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    env = np.abs(y)
    peak = float(env.max())
    if peak <= 1e-9:
        return 0.0
    threshold = peak * 0.1
    above = np.flatnonzero(env >= threshold)
    if above.size == 0:
        return 0.0
    return float(above[-1] / max(1, y.size - 1))


def _stereo_correlation(y_stereo: np.ndarray | None) -> float | None:
    if y_stereo is None:
        return None
    data = np.asarray(y_stereo, dtype=np.float32)
    if data.ndim != 2:
        return None
    if data.shape[0] == 2:
        left, right = data[0], data[1]
    elif data.shape[1] == 2:
        left, right = data[:, 0], data[:, 1]
    else:
        return None
    n = min(left.size, right.size)
    if n < 2:
        return None
    left = left[:n] - float(np.mean(left[:n]))
    right = right[:n] - float(np.mean(right[:n]))
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-9:
        return None
    return float(np.dot(left, right) / denom)


def _crest_factor(y: np.ndarray) -> float:
    """Peak-to-RMS ratio; high value = strong transient."""
    if y.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(y)) + 1e-12))
    peak = float(np.max(np.abs(y)))
    return peak / max(rms, 1e-9)


def _attack_time(y: np.ndarray, sr: int) -> float:
    """Normalized position of the peak (0=instant, 1=end); low = fast attack."""
    if y.size == 0 or sr <= 0:
        return 0.0
    peak_idx = int(np.argmax(np.abs(y)))
    return float(peak_idx / max(1, y.size - 1))


def _band_flatness(freqs: np.ndarray, mag: np.ndarray, low: float, high: float) -> float:
    """Spectral flatness restricted to a frequency band."""
    if freqs.size == 0:
        return 0.0
    mask = (freqs >= low) & (freqs < high)
    band = mag[mask]
    if band.size == 0:
        return 0.0
    return _flatness(band)


def derive_character_tags(
    y_mono: np.ndarray,
    y_stereo: np.ndarray | None,
    sr: int,
    scalars: dict[str, float] | None = None,
) -> list[str]:
    """Return deterministic character tags from a mono signal plus optional stereo.

    The thresholds are intentionally conservative: they prefer a few useful tags
    over noisy over-labeling. Genre-like tags stay filename/manual-only.
    """
    y = _clean_mono(y_mono)
    if y.size == 0 or sr <= 0:
        return []

    scalars = dict(scalars or {})
    duration = float(scalars.get("duration", y.size / sr))
    freqs, mag = _spectrum(y, sr)
    rolloff95 = float(scalars.get("rolloff95", _rolloff(freqs, mag, 0.95)))
    centroid = float(
        scalars.get(
            "centroid",
            float(np.sum(freqs * mag) / max(float(np.sum(mag)), 1e-9) / max(sr / 2.0, 1.0))
            if mag.size
            else 0.0,
        )
    )
    flatness = float(scalars.get("flatness", _flatness(mag)))
    late_ratio = float(scalars.get("late_ratio", _late_ratio(y)))
    decay = float(scalars.get("decay", _decay_position(y)))
    bass_ratio = float(scalars.get("bass_ratio", _band_ratio(freqs, mag, 25.0, 140.0)))
    sub_ratio = float(scalars.get("sub_ratio", _band_ratio(freqs, mag, 35.0, 90.0)))
    high_ratio = float(scalars.get("high_ratio", _band_ratio(freqs, mag, 6000.0, sr / 2.0)))
    zcr = float(scalars.get("zcr", np.mean(np.abs(np.diff(np.signbit(y))))))

    # New derived scalars (no scalars.get override needed — callers supply these
    # via the existing scalars dict if precomputed).
    crest = float(scalars.get("crest", _crest_factor(y)))
    attack = float(scalars.get("attack", _attack_time(y, sr)))
    mid_ratio = float(scalars.get("mid_ratio", _band_ratio(freqs, mag, 150.0, 500.0)))
    mid_band_ratio = float(scalars.get("mid_band_ratio", _band_ratio(freqs, mag, 500.0, 5000.0)))
    very_high_ratio = float(scalars.get("very_high_ratio", _band_ratio(freqs, mag, 10000.0, sr / 2.0)))
    mid_flatness = float(scalars.get("mid_flatness", _band_flatness(freqs, mag, 500.0, 5000.0)))
    high_flatness = float(scalars.get("high_flatness", _band_flatness(freqs, mag, 6000.0, sr / 2.0)))
    very_high_flatness = float(scalars.get("very_high_flatness", _band_flatness(freqs, mag, 10000.0, sr / 2.0)))

    tags: list[str] = []

    # --- existing tags (thresholds unchanged) ---
    if centroid >= 0.42 or rolloff95 >= 0.72 or high_ratio >= 0.18:
        tags.append("bright")
    if centroid <= 0.16 and rolloff95 <= 0.36:
        tags.append("dark")
    if bass_ratio >= 0.55 and decay >= 0.45:
        tags.append("boomy")
    if duration < 0.4 or decay < 0.18:
        tags.append("short")
    if late_ratio < 0.08 and duration >= 0.08:
        tags.append("dry")
    if late_ratio >= 0.28 and decay >= 0.45:
        tags.append("reverb")
    if flatness >= 0.32 or zcr >= 0.22:
        tags.append("dirty")

    corr = _stereo_correlation(y_stereo)
    if corr is not None and corr < 0.35:
        tags.append("wide")

    if sub_ratio >= 0.42 and duration >= 0.45 and decay >= 0.5:
        tags.append("808")
    if rolloff95 <= 0.38 and flatness >= 0.12:
        tags.append("lofi")

    # --- new tags ---

    # punchy vs soft are mutually exclusive (crest factor + attack time)
    if crest >= 6.0 and attack <= 0.08:
        tags.append("punchy")
    elif crest <= 2.5 and attack >= 0.25:
        tags.append("soft")

    # clicky: very short + dominant high energy (sharp transient click)
    if duration < 0.06 and high_ratio >= 0.30 and crest >= 5.0:
        tags.append("clicky")

    # subby vs thin are mutually exclusive (low-end energy)
    if sub_ratio >= 0.35 and mid_band_ratio <= 0.12 and high_ratio <= 0.08:
        tags.append("subby")
    elif bass_ratio <= 0.06 and sub_ratio <= 0.04:
        tags.append("thin")

    # noisy: stronger thresholds than dirty to avoid overlap
    if flatness >= 0.55 and zcr >= 0.30:
        tags.append("noisy")

    # clean: tonal, low noise floor, moderate transient
    if flatness <= 0.08 and zcr <= 0.08 and 2.0 <= crest <= 12.0:
        tags.append("clean")

    # crunchy: high mid-band distortion + high flatness in mids
    if mid_band_ratio >= 0.30 and mid_flatness >= 0.40:
        tags.append("crunchy")

    # metallic: high inharmonic high-frequency partials
    if high_flatness >= 0.45 and centroid >= 0.35:
        tags.append("metallic")

    # tonal: strong harmonic content (low overall flatness)
    if flatness <= 0.06:
        tags.append("tonal")

    # percussive: short decay + fast attack + broadband energy
    if decay <= 0.35 and attack <= 0.10 and mid_band_ratio >= 0.20 and high_ratio >= 0.10:
        tags.append("percussive")

    # long-tail vs tight are mutually exclusive (sustain / decay character)
    if decay >= 0.75 and duration >= 1.5:
        tags.append("long-tail")
    elif decay <= 0.25 and late_ratio <= 0.06:
        tags.append("tight")

    # muddy: strong low-mid energy with little high end
    if mid_ratio >= 0.30 and high_ratio <= 0.06:
        tags.append("muddy")

    # airy: strong very-high energy with low noise (harmonic shimmer)
    if very_high_ratio >= 0.12 and very_high_flatness <= 0.25:
        tags.append("airy")

    # mono: very high stereo correlation (complements existing wide)
    if corr is not None and corr > 0.97 and "wide" not in tags:
        tags.append("mono")

    return list(dict.fromkeys(tags))

"""Descriptor extraction: BPM, musical key, loudness, plus the feature vector.

All librosa-based. Each function degrades to None on failure so indexing of a
large folder is never aborted by one bad file.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np

from .features import extract_features
from .playback import render_waveform

# Krumhansl-Schmuckler key profiles (major / minor), correlated against the
# averaged chroma to estimate musical key.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class Descriptors:
    bpm: float | None = None
    musical_key: str | None = None
    key_scale: str | None = None
    loudness_lufs: float | None = None
    waveform_preview: str | None = None
    vector: np.ndarray | None = None


def _require_librosa():
    try:
        import librosa
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Audio analysis needs librosa. Install: pip install 'cratedig[analysis]'"
        ) from e
    return librosa


def estimate_key(chroma_mean: np.ndarray) -> tuple[str, str]:
    """Return (note, scale) by correlating chroma with key profiles."""
    best = (-2.0, "C", "major")
    for shift in range(12):
        rolled = np.roll(chroma_mean, -shift)
        maj = float(np.corrcoef(rolled, _MAJOR)[0, 1])
        minr = float(np.corrcoef(rolled, _MINOR)[0, 1])
        if maj > best[0]:
            best = (maj, _NOTES[shift], "major")
        if minr > best[0]:
            best = (minr, _NOTES[shift], "minor")
    return best[1], best[2]


def analyze(path: str, sr: int = 22050) -> Descriptors:
    """Full descriptor pass for one file. Best-effort; never raises on content."""
    librosa = _require_librosa()
    d = Descriptors()
    try:
        y, sr = librosa.load(path, sr=sr, mono=True)
    except Exception:
        return d
    if y.size == 0:
        return d
    d.waveform_preview = render_waveform(y, width=28)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"n_fft=.*too large.*")

        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            d.bpm = round(float(np.atleast_1d(tempo)[0]), 2)
        except Exception:
            pass

        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
            d.musical_key, d.key_scale = estimate_key(chroma)
        except Exception:
            pass

        try:
            rms = librosa.feature.rms(y=y)
            d.loudness_lufs = round(float(20 * np.log10(np.mean(rms) + 1e-9)), 2)
        except Exception:
            pass

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"n_fft=.*too large.*")
        try:
            d.vector = extract_features(path, sr=sr)
        except Exception:
            pass

    return d

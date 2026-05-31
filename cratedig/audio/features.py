"""Feature-vector extraction for similarity search.

Vector = mean+std of MFCCs (13) + chroma (12) + spectral centroid/bandwidth/
rolloff + zero-crossing rate. Compact, content-based, no GPU. librosa required.
"""

from __future__ import annotations

import numpy as np

# 13 MFCC + 12 chroma + 4 scalar descriptors, each as (mean, std).
FEATURE_DIM = (13 + 12 + 4) * 2  # 58


def _require_librosa():
    try:
        import librosa  # noqa: F401
    except ImportError as e:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Audio analysis needs librosa. Install: pip install 'cratedig[analysis]'"
        ) from e
    import librosa
    return librosa


def extract_features(path: str, sr: int = 22050) -> np.ndarray:
    """Return an L2-normalized float32 feature vector of length FEATURE_DIM."""
    librosa = _require_librosa()
    y, sr = librosa.load(path, sr=sr, mono=True)
    if y.size == 0:
        return np.zeros(FEATURE_DIM, dtype=np.float32)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y)

    parts = []
    for feat in (mfcc, chroma, centroid, bandwidth, rolloff, zcr):
        parts.append(feat.mean(axis=1))
        parts.append(feat.std(axis=1))
    vec = np.concatenate(parts).astype(np.float32)

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec

"""Feature-vector extraction for acoustic similarity search.

The vector is intentionally closer to sample-browser matching than to broad
music tagging: it combines timbre, spectral shape, noisiness, amplitude envelope,
pitch/chroma, and duration. Each block is normalized before weighted
concatenation so one descriptor family cannot dominate the whole score.
"""

from __future__ import annotations

import numpy as np

MEL_BANDS = 40
MFCCS = 20
ENVELOPE_BINS = 24
SCALAR_COUNT = 11
FEATURE_DIM = (
    MEL_BANDS * 2
    + MFCCS * 2
    + 7 * 2  # spectral contrast bands
    + 12 * 2  # chroma
    + ENVELOPE_BINS
    + SCALAR_COUNT
)

# Named feature sub-blocks → (start, end) slices into the FEATURE_DIM vector.
# Order MUST match the concatenation in extract_features().
_b0 = 0
_b1 = _b0 + MEL_BANDS * 2      # logmel
_b2 = _b1 + MFCCS * 2          # mfcc
_b3 = _b2 + 7 * 2               # spectral contrast
_b4 = _b3 + 12 * 2              # chroma
_b5 = _b4 + ENVELOPE_BINS       # envelope
_b6 = _b5 + SCALAR_COUNT        # scalars (== FEATURE_DIM)

assert _b6 == FEATURE_DIM, f"ASPECT_BLOCKS boundary mismatch: {_b6} != {FEATURE_DIM}"

ASPECT_BLOCKS: dict[str, tuple[int, int]] = {
    "Overall":   (_b0, _b6),
    "Spectrum":  (_b0, _b1),    # log-mel spectrum shape
    "Timbre":    (_b1, _b3),    # mfcc + spectral contrast
    "Pitch":     (_b3, _b4),    # chroma
    "Amplitude": (_b4, _b6),    # envelope + scalar dynamics
}
ASPECTS: tuple[str, ...] = ("Overall", "Spectrum", "Timbre", "Pitch", "Amplitude")


def _require_librosa():
    try:
        import librosa  # noqa: F401
    except ImportError as e:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Audio analysis needs librosa. Install: pip install 'cratedig[analysis]'"
        ) from e
    import librosa
    return librosa


def _stats(feat: np.ndarray) -> np.ndarray:
    data = np.asarray(feat, dtype=np.float32)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.size == 0:
        return np.zeros(data.shape[0] * 2, dtype=np.float32)
    return np.concatenate([data.mean(axis=1), data.std(axis=1)]).astype(np.float32)


def _block(vec: np.ndarray, weight: float) -> np.ndarray:
    out = np.nan_to_num(np.asarray(vec, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    norm = float(np.linalg.norm(out))
    if norm > 1e-9:
        out = out / norm
    return out * weight


def _curve(values: np.ndarray, bins: int) -> np.ndarray:
    data = np.asarray(values, dtype=np.float32).reshape(-1)
    if data.size == 0:
        return np.zeros(bins, dtype=np.float32)
    if data.size == 1:
        return np.full(bins, float(data[0]), dtype=np.float32)
    src = np.linspace(0.0, 1.0, data.size, dtype=np.float32)
    dst = np.linspace(0.0, 1.0, bins, dtype=np.float32)
    return np.interp(dst, src, data).astype(np.float32)


def _scalar_features(librosa, y: np.ndarray, sr: int, rms: np.ndarray) -> np.ndarray:
    abs_y = np.abs(y)
    peak = float(abs_y.max()) if abs_y.size else 0.0
    rms_mean = float(np.sqrt(np.mean(np.square(y)) + 1e-12))
    crest = peak / max(rms_mean, 1e-9)
    duration = float(y.size) / float(sr) if sr else 0.0
    attack = int(np.argmax(abs_y)) / max(1, abs_y.size - 1) if abs_y.size else 0.0

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    rolloff85 = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)
    rolloff95 = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.95)
    zcr = librosa.feature.zero_crossing_rate(y)
    flatness = librosa.feature.spectral_flatness(y=y)

    nyquist = max(1.0, sr / 2.0)
    return np.array(
        [
            np.log1p(duration) / 8.0,
            np.log1p(crest) / 4.0,
            peak,
            rms_mean,
            float(rms.std()) / max(float(rms.mean()), 1e-9) if rms.size else 0.0,
            attack,
            float(np.mean(centroid)) / nyquist,
            float(np.mean(bandwidth)) / nyquist,
            float(np.mean(rolloff85)) / nyquist,
            float(np.mean(rolloff95)) / nyquist,
            float(np.mean(zcr) + np.mean(flatness)),
        ],
        dtype=np.float32,
    )


def extract_features(path: str, sr: int = 22050, y: np.ndarray | None = None) -> np.ndarray:
    """Return a weighted, L2-normalized float32 vector of length FEATURE_DIM.

    Pass `y` (mono float samples already decoded at `sr`) to skip re-decoding the
    file — the analyzer reuses the buffer it loaded for BPM/key/loudness.
    """
    librosa = _require_librosa()
    if y is None:
        y, sr = librosa.load(path, sr=sr, mono=True)
    else:
        y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        return np.zeros(FEATURE_DIM, dtype=np.float32)

    y = librosa.util.normalize(y.astype(np.float32))
    rms = librosa.feature.rms(y=y)[0]
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=MEL_BANDS, power=2.0)
    logmel = librosa.power_to_db(mel, ref=np.max)
    mfcc = librosa.feature.mfcc(S=logmel, n_mfcc=MFCCS)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    envelope = _curve(librosa.power_to_db(rms**2 + 1e-12, ref=np.max), ENVELOPE_BINS)
    scalars = _scalar_features(librosa, y, sr, rms)

    parts = [
        _block(_stats(logmel), 1.35),
        _block(_stats(mfcc), 1.15),
        _block(_stats(contrast), 0.95),
        _block(_stats(chroma), 0.65),
        _block(envelope, 1.05),
        _block(scalars, 0.85),
    ]
    vec = np.concatenate(parts).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec

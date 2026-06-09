"""Playback and waveform helpers for the TUI.

Uses ffmpeg/ffplay executables instead of Python audio backends so downloaded
mp3/wav/flac files all follow the same path.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import hashlib
import subprocess
from pathlib import Path

import numpy as np

from ..paths import ffmpeg_path, ffplay_path


def level_gain_db(ref_loudness: float, target_loudness: float) -> float:
    """Return the dB gain to apply to target so its RMS level matches ref.

    Formula: 20 * log10(ref / target).  Both arguments must be > 0.
    """
    if ref_loudness <= 0:
        raise ValueError(f"ref_loudness must be positive, got {ref_loudness!r}")
    if target_loudness <= 0:
        raise ValueError(f"target_loudness must be positive, got {target_loudness!r}")
    return float(20.0 * math.log10(ref_loudness / target_loudness))


BLOCKS = " ▁▂▃▄▅▆▇█"
WAVEFORM_EMPTY = "·"
WAVEFORM_PEAK = "█"
WAVEFORM_BODY = "┃"
WAVEFORM_RMS = "░"
WAVEFORM_CENTER = "─"
WAVEFORM_PLAYHEAD = "│"
WAVEFORM_SELECTION = "▒"


@dataclass(frozen=True)
class WaveformData:
    """Min/max/RMS envelope used by the TUI waveform renderer."""

    peaks: np.ndarray  # channels x bins x (min, max)
    rms: np.ndarray  # channels x bins
    duration_sec: float
    sample_rate: int
    channels: int

    @property
    def bins(self) -> int:
        return int(self.peaks.shape[1]) if self.peaks.ndim == 3 else 0


def render_waveform(samples: np.ndarray, width: int = 80) -> str:
    """Render a compact one-line waveform from mono float samples."""
    if width <= 0 or samples.size == 0:
        return ""

    data = np.asarray(samples, dtype=np.float32)
    data = data[np.isfinite(data)]
    if data.size == 0:
        return ""

    peaks = []
    for chunk in np.array_split(np.abs(data), min(width, data.size)):
        peaks.append(float(chunk.max()) if chunk.size else 0.0)

    max_peak = max(peaks) if peaks else 0.0
    if max_peak <= 0:
        return BLOCKS[1] * len(peaks)

    levels = len(BLOCKS) - 1
    return "".join(BLOCKS[min(levels, int(round((p / max_peak) * levels)))] for p in peaks)


def _envelope(samples: np.ndarray, *, bins: int, channels: int, sample_rate: int) -> WaveformData:
    if bins <= 0 or channels <= 0 or sample_rate <= 0:
        empty = np.zeros((1, 0, 2), dtype=np.float32)
        return WaveformData(empty, np.zeros((1, 0), dtype=np.float32), 0.0, sample_rate, 1)

    frames = samples.size // channels
    if frames <= 0:
        empty = np.zeros((channels, 0, 2), dtype=np.float32)
        return WaveformData(empty, np.zeros((channels, 0), dtype=np.float32), 0.0, sample_rate, channels)

    audio = samples[: frames * channels].reshape(frames, channels)
    bin_count = min(bins, frames)
    peaks = np.zeros((channels, bin_count, 2), dtype=np.float32)
    rms = np.zeros((channels, bin_count), dtype=np.float32)

    for i, chunk in enumerate(np.array_split(audio, bin_count, axis=0)):
        if chunk.size == 0:
            continue
        peaks[:, i, 0] = np.min(chunk, axis=0)
        peaks[:, i, 1] = np.max(chunk, axis=0)
        rms[:, i] = np.sqrt(np.mean(np.square(chunk), axis=0))

    duration_sec = frames / float(sample_rate)
    return WaveformData(peaks, rms, duration_sec, sample_rate, channels)


def decode_waveform_mono_samples(
    path: str | Path,
    *,
    sample_rate: int = 44100,
    max_seconds: int | None = None,
) -> np.ndarray:
    """Decode audio to a mono float32 buffer for high-resolution GUI drawing."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return _decode_waveform_mono_samples_soundfile(path)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
    ]
    if max_seconds is not None:
        cmd += ["-t", str(max_seconds)]
    cmd += [
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "ffmpeg failed to decode audio")
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    return np.ascontiguousarray(samples[np.isfinite(samples)], dtype=np.float32)


def mono_preview_cache_path(
    cache_dir: str | Path,
    file_hash: str,
    *,
    sample_rate: int = 44100,
) -> Path:
    """Return the cache path for a decoded mono preview."""
    return Path(cache_dir) / f"mono_{sample_rate}_{file_hash}.npy"


def load_mono_preview_cache(
    cache_dir: str | Path,
    file_hash: str | None,
    *,
    sample_rate: int = 44100,
) -> np.ndarray | None:
    """Load a cached mono preview, returning None when it is absent/invalid."""
    if not file_hash:
        return None
    path = mono_preview_cache_path(cache_dir, file_hash, sample_rate=sample_rate)
    try:
        data = np.load(path, allow_pickle=False)
    except Exception:
        return None
    if data.dtype != np.float32:
        data = data.astype(np.float32)
    return np.ascontiguousarray(data[np.isfinite(data)], dtype=np.float32)


def save_mono_preview_cache(
    samples: np.ndarray,
    cache_dir: str | Path,
    file_hash: str,
    *,
    sample_rate: int = 44100,
) -> Path:
    """Persist decoded mono preview samples to the cache."""
    dest = mono_preview_cache_path(cache_dir, file_hash, sample_rate=sample_rate)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.npy")
    clean = np.ascontiguousarray(np.asarray(samples, dtype=np.float32), dtype=np.float32)
    with tmp.open("wb") as fh:
        np.save(fh, clean, allow_pickle=False)
    tmp.replace(dest)
    return dest


def ensure_mono_preview_cache(
    path: str | Path,
    cache_dir: str | Path,
    *,
    file_hash: str | None = None,
    sample_rate: int = 44100,
) -> Path:
    """Decode and persist the exact mono preview used by the GUI waveform."""
    if file_hash is None:
        h = hashlib.sha1()
        with Path(path).open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        file_hash = h.hexdigest()
    dest = mono_preview_cache_path(cache_dir, file_hash, sample_rate=sample_rate)
    if dest.is_file():
        return dest
    samples = decode_waveform_mono_samples(path, sample_rate=sample_rate)
    return save_mono_preview_cache(samples, cache_dir, file_hash, sample_rate=sample_rate)


def _decode_waveform_mono_samples_soundfile(path: str | Path) -> np.ndarray:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("ffmpeg not found on PATH") from exc

    try:
        audio, _source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RuntimeError(f"ffmpeg not found on PATH and soundfile could not decode audio: {exc}") from exc
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = mono[np.isfinite(mono)]
    return np.ascontiguousarray(mono, dtype=np.float32)


def decode_waveform_data(
    path: str | Path,
    *,
    bins: int = 4096,
    sample_rate: int = 11025,
    channels: int = 2,
    max_seconds: int | None = None,
) -> WaveformData:
    """Decode audio through ffmpeg and build a full-file min/max/RMS envelope."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return _decode_waveform_data_soundfile(path, bins=bins, channels=channels)

    channel_count = max(1, min(2, channels))
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
    ]
    if max_seconds is not None:
        cmd += ["-t", str(max_seconds)]
    cmd += [
        "-f",
        "f32le",
        "-ac",
        str(channel_count),
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "ffmpeg failed to decode audio")

    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    samples = samples[np.isfinite(samples)]
    return _envelope(samples, bins=bins, channels=channel_count, sample_rate=sample_rate)


def _decode_waveform_data_soundfile(
    path: str | Path,
    *,
    bins: int,
    channels: int,
) -> WaveformData:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("ffmpeg not found on PATH") from exc

    try:
        audio, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RuntimeError(f"ffmpeg not found on PATH and soundfile could not decode audio: {exc}") from exc

    channel_count = max(1, min(2, channels, audio.shape[1]))
    audio = audio[:, :channel_count]
    return _envelope(audio.reshape(-1), bins=bins, channels=channel_count, sample_rate=int(source_rate))


def _time_to_bin(data: WaveformData, seconds: float) -> int:
    if data.duration_sec <= 0 or data.bins <= 0:
        return 0
    ratio = max(0.0, min(1.0, seconds / data.duration_sec))
    return min(data.bins - 1, int(round(ratio * (data.bins - 1))))


def render_waveform_panel(
    data: WaveformData,
    *,
    width: int = 80,
    lane_height: int = 5,
    zoom: float = 1.0,
    offset: float = 0.0,
    playhead_sec: float = 0.0,
    selection: tuple[float, float] | None = None,
) -> str:
    """Render a DAW-like text waveform with peak, RMS, playhead, and selection."""
    if width <= 0 or lane_height < 3 or data.bins <= 0:
        return ""

    visible = max(1, min(data.bins, int(round(data.bins / max(1.0, zoom)))))
    start = max(0, min(data.bins - visible, int(round(offset * max(0, data.bins - visible)))))
    stop = start + visible
    columns = min(width, visible)
    center = lane_height // 2
    amp_rows = max(1, center)
    max_amp = float(np.max(np.abs(data.peaks[:, start:stop, :]))) if stop > start else 0.0
    if max_amp <= 1e-9:
        max_amp = 1.0

    play_bin = _time_to_bin(data, playhead_sec)
    play_col = int((play_bin - start) / max(1, visible) * columns) if start <= play_bin < stop else -1
    sel_cols: set[int] = set()
    if selection:
        a, b = sorted(selection)
        sel_start = _time_to_bin(data, a)
        sel_stop = _time_to_bin(data, b)
        for col in range(columns):
            c_start = start + int(col * visible / columns)
            c_stop = start + int((col + 1) * visible / columns)
            if c_start <= sel_stop and c_stop >= sel_start:
                sel_cols.add(col)

    lines: list[str] = []
    channels = min(data.channels, data.peaks.shape[0])
    for ch in range(channels):
        lane = [[WAVEFORM_EMPTY for _ in range(columns)] for _ in range(lane_height)]
        for col in range(columns):
            b0 = start + int(col * visible / columns)
            b1 = start + max(1, int((col + 1) * visible / columns))
            chunk_peak = data.peaks[ch, b0:b1]
            chunk_rms = data.rms[ch, b0:b1]
            if chunk_peak.size == 0:
                continue

            lo = float(np.min(chunk_peak[:, 0])) / max_amp
            hi = float(np.max(chunk_peak[:, 1])) / max_amp
            rms = float(np.max(chunk_rms)) / max_amp if chunk_rms.size else 0.0
            top = center - int(round(max(0.0, hi) * amp_rows))
            bottom = center + int(round(max(0.0, -lo) * amp_rows))
            rms_top = center - int(round(rms * amp_rows))
            rms_bottom = center + int(round(rms * amp_rows))

            if col in sel_cols:
                for row in range(lane_height):
                    lane[row][col] = WAVEFORM_SELECTION
            lane[center][col] = WAVEFORM_CENTER
            for row in range(max(0, top), min(lane_height, bottom + 1)):
                lane[row][col] = WAVEFORM_BODY
            for row in range(max(0, rms_top), min(lane_height, rms_bottom + 1)):
                lane[row][col] = WAVEFORM_RMS
            if 0 <= top < lane_height:
                lane[top][col] = WAVEFORM_PEAK
            if 0 <= bottom < lane_height:
                lane[bottom][col] = WAVEFORM_PEAK
            if col == play_col:
                for row in range(lane_height):
                    lane[row][col] = WAVEFORM_PLAYHEAD

        prefix = "L " if channels > 1 and ch == 0 else "R " if channels > 1 else "M "
        lines.extend(prefix + "".join(row) for row in lane)

    start_sec = data.duration_sec * (start / data.bins)
    stop_sec = data.duration_sec * (stop / data.bins)
    lines.append(f"{_fmt_time(start_sec)}-{_fmt_time(stop_sec)} / {_fmt_time(data.duration_sec)}  zoom {zoom:.1f}x")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}:{secs:04.1f}"


def decode_waveform(path: str | Path, *, width: int = 80, max_seconds: int = 45) -> str:
    """Decode a short mono preview with ffmpeg and render it as text."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-t",
        str(max_seconds),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        "8000",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "ffmpeg failed to decode audio")
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    return render_waveform(samples, width=width)


class AudioPlayer:
    """Tiny ffplay process wrapper."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if not self.is_playing():
            self._proc = None
            return
        assert self._proc is not None
        self._proc.terminate()
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=2)
        self._proc = None

    def play(
        self,
        target: str | Path,
        *,
        start_sec: float | None = None,
        duration_sec: float | None = None,
        loop: bool = False,
        gain_db: float | None = None,
    ) -> None:
        ffplay = ffplay_path()
        if not ffplay:
            raise RuntimeError("ffplay not found on PATH")
        self.stop()
        cmd = [ffplay, "-nodisp", "-autoexit", "-loglevel", "error"]
        if start_sec is not None and start_sec > 0:
            cmd += ["-ss", f"{start_sec:.3f}"]
        if duration_sec is not None and duration_sec > 0:
            cmd += ["-t", f"{duration_sec:.3f}"]
        if loop:
            cmd += ["-loop", "0"]
        if gain_db is not None and gain_db != 0.0:
            cmd += ["-af", f"volume={gain_db}dB"]
        cmd.append(str(target))
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def toggle(self, target: str | Path) -> bool:
        """Toggle playback. Returns True when playback was started."""
        if self.is_playing():
            self.stop()
            return False
        self.play(target)
        return True

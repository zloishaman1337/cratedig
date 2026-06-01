"""Background worker: all blocking DB/filesystem/ffmpeg work runs here."""

from __future__ import annotations

from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from ..config import Config
from ..db.database import Database
from ..tui.browser import build_folder_tree


class IndexWorker(QObject):
    """Runs all blocking operations on a QThread; results are emitted as signals."""

    # outbound signals
    treeReady = Signal(object, object, object)  # (nodes_dict, favorites_list[Sample], samples)
    progress = Signal(str, int, int)            # (phase, done, total)
    peaksReady = Signal(int, object)            # (seq, mono_ndarray)
    failed = Signal(str, str)                   # (context, message)

    def __init__(self, db: Database, cfg: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._cfg = cfg

    @Slot()
    def request_reload(self) -> None:
        """Load all samples, build folder tree, and resolve favorites."""
        try:
            with self._db.lock:
                samples = self._db.all_samples()
                fav_rows = self._db.list_favorites("sample")

            nodes = build_folder_tree(samples, self._cfg.paths.library_dirs)

            # Resolve favorite dicts (kind='sample', ref=str(sample_id)) to Sample objects.
            # We call get_sample for each, which takes db.lock internally.
            favorites: list = []
            for row in fav_rows:
                try:
                    sid = int(row["ref"])
                except (ValueError, KeyError):
                    continue
                s = self._db.get_sample(sid)
                if s is not None:
                    favorites.append(s)

            self.treeReady.emit(nodes, favorites, samples)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("reload", str(exc))

    @Slot()
    def request_scan_analyze(self) -> None:
        """Scan libraries, analyze pending, then reload the tree."""
        from .. import index as indexer

        try:
            def scan_progress(path: Path, count: int) -> None:
                self.progress.emit("scan", count, 0)

            with self._db.lock:
                pass  # ensure connection is accessible
            indexer.scan_libraries(self._db, self._cfg, scan_progress)

            def analyze_progress(done: int, total: int) -> None:
                self.progress.emit("analyze", done, total)

            indexer.analyze_pending(self._db, self._cfg, analyze_progress)
            self.progress.emit("analyze", 0, 0)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("scan_analyze", str(exc))
            return

        # Auto-reload tree after scan+analyze
        self.request_reload()

    @Slot(int, str, int)
    def request_peaks(self, seq: int, path: str, width: int) -> None:
        """Decode waveform for path, reduce to mono, compute peaks, emit result."""
        from ..audio.playback import decode_waveform_data

        try:
            waveform_data = decode_waveform_data(path, bins=max(width * 4, 4096), channels=2)
            # Average channels to produce mono 1-D float32 array
            peaks_arr = waveform_data.peaks  # channels x bins x 2
            if peaks_arr.ndim != 3 or peaks_arr.shape[1] == 0:
                self.failed.emit("peaks", "invalid peaks shape")
                return
            # Per-bin amplitude: max(|min|, |max|) per channel, then average channels
            mono = np.maximum(
                np.abs(peaks_arr[:, :, 0]), np.abs(peaks_arr[:, :, 1])
            ).mean(axis=0).astype(np.float32)

            self.peaksReady.emit(seq, mono)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("peaks", str(exc))

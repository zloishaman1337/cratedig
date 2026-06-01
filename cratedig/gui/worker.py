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
    searchReady = Signal(int, object, str)      # (seq, hits_list[SearchHit], used_backend)
    downloadDone = Signal(bool, str)            # (ok, message)
    failed = Signal(str, str)                   # (context, message)

    def __init__(self, db: Database, cfg: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._cfg = cfg
        self._dm = None  # lazy DownloadManager (imports source backends)

    def _manager(self):
        """Lazily build the DownloadManager (backend imports are heavyweight)."""
        if self._dm is None:
            from ..sources import DownloadManager

            self._dm = DownloadManager(self._db, self._cfg)
        return self._dm

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

    @Slot(int)
    def request_toggle_favorite(self, sample_id: int) -> None:
        """Toggle a sample's favorite state in the DB, then reload the tree."""
        try:
            self._db.toggle_favorite("sample", str(sample_id))
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("toggle_favorite", str(exc))

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
            # Signed per-bin envelope: average channels, keep min (negative) and
            # max (positive) separate, then interleave so compute_peaks re-bins
            # into a symmetric min/max waveform instead of a top-half-only one.
            lo = peaks_arr[:, :, 0].mean(axis=0)  # signed minima (≤ 0)
            hi = peaks_arr[:, :, 1].mean(axis=0)  # signed maxima (≥ 0)
            mono = np.empty(lo.size * 2, dtype=np.float32)
            mono[0::2] = lo
            mono[1::2] = hi

            self.peaksReady.emit(seq, mono)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("peaks", str(exc))

    @Slot(int, str, str, int)
    def request_search(self, seq: int, query: str, mode: str, limit: int) -> None:
        """Search source backends for a query; emit hits tagged with seq."""
        try:
            hits, used = self._manager().search(query, mode=mode, limit=limit)
            self.searchReady.emit(seq, hits, used)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("search", str(exc))

    @Slot(object)
    def request_download(self, hit) -> None:
        """Download a chosen SearchHit, auto-index it, then reload the tree."""
        try:
            def progress(detail: str) -> None:
                self.progress.emit(f"download: {detail}", 0, 0)

            res = self._manager().fetch_hit(hit, auto_index=True, progress=progress)
            if res.ok:
                self.downloadDone.emit(True, f"downloaded [{res.source}] → {res.path}")
                self.request_reload()  # surface the new sample in the tree
            else:
                self.downloadDone.emit(False, f"FAILED [{res.source}] {res.error}")
        except Exception as exc:  # noqa: BLE001
            self.downloadDone.emit(False, f"download failed: {exc}")

"""Main application window: wires panes, worker, and player together."""

from __future__ import annotations

from PySide6.QtCore import QMetaObject, QThread, Qt, Q_ARG
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStatusBar,
    QToolBar,
)

from ..config import Config
from ..db.database import Database
from .logic import tree_rows
from .player import Player
from .sample_table import SampleTable
from .tree_pane import TreePane
from .waveform_pane import WaveformPane
from .worker import IndexWorker


class MainWindow(QMainWindow):
    def __init__(self, db: Database, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("cratedig")
        self.resize(1200, 700)

        self._cfg = cfg
        self._player = Player()
        self._nodes: dict = {}
        self._favorites: list = []
        self._favorites_by_id: dict = {}
        self._current_sample = None
        self._current_seq = 0

        # --- build panes ---
        self._tree_pane = TreePane()
        self._sample_table = SampleTable()
        self._waveform_pane = WaveformPane()

        # --- playback buttons ---
        play_btn = QPushButton("Play")
        stop_btn = QPushButton("Stop")
        play_btn.setEnabled(False)
        self._play_btn = play_btn
        self._stop_btn = stop_btn
        play_btn.clicked.connect(self._on_play)
        stop_btn.clicked.connect(self._on_stop)

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.addWidget(play_btn)
        btn_layout.addWidget(stop_btn)
        btn_layout.addStretch()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._waveform_pane, stretch=1)
        right_layout.addWidget(btn_bar)

        # --- splitter layout ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree_pane)
        splitter.addWidget(self._sample_table)
        splitter.addWidget(right_panel)
        splitter.setSizes([220, 500, 380])
        self.setCentralWidget(splitter)

        # --- toolbar ---
        toolbar = QToolBar("Actions")
        self.addToolBar(toolbar)
        scan_action = toolbar.addAction("Scan")
        analyze_action = toolbar.addAction("Analyze")
        scan_action.triggered.connect(self._on_scan_analyze)
        analyze_action.triggered.connect(self._on_analyze_only)

        # --- status bar ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # --- worker thread ---
        self._thread = QThread(self)
        self._worker = IndexWorker(db, cfg)
        self._worker.moveToThread(self._thread)

        self._worker.treeReady.connect(self._on_tree_ready)
        self._worker.progress.connect(self._on_progress)
        self._worker.peaksReady.connect(self._on_peaks_ready)
        self._worker.failed.connect(self._on_worker_failed)

        self._tree_pane.folder_selected.connect(self._on_folder_selected)
        self._sample_table.sample_selected.connect(self._on_sample_selected)

        self._thread.start()

        # Initial data load — invoke on worker thread via queued call
        QMetaObject.invokeMethod(self._worker, "request_reload", Qt.ConnectionType.QueuedConnection)

    # --- slots ---

    def _on_tree_ready(self, nodes: dict, favorites: list, samples: list) -> None:
        self._nodes = nodes
        self._favorites = favorites
        self._favorites_by_id = {s.id: s for s in favorites}
        rows = tree_rows(nodes, favorites)
        self._tree_pane.set_rows(rows)
        self._status_bar.showMessage(f"Loaded {len(samples)} samples", 3000)

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        if total > 0:
            self._status_bar.showMessage(f"{phase}: {done}/{total}")
        elif done > 0:
            self._status_bar.showMessage(f"{phase}: {done} processed")
        else:
            self._status_bar.showMessage(f"{phase}: done", 2000)

    def _on_peaks_ready(self, seq: int, mono) -> None:
        if seq != self._current_seq:
            return
        self._waveform_pane.set_mono(mono)

    def _on_worker_failed(self, context: str, message: str) -> None:
        self._status_bar.showMessage(f"Error [{context}]: {message}", 5000)

    def _on_folder_selected(self, key: str, is_fav: bool) -> None:
        if is_fav:
            if key.startswith("fav:"):
                # Single favorite sample — look up from cached favorites (no DB on GUI thread)
                try:
                    sid = int(key[4:])
                except ValueError:
                    return
                s = self._favorites_by_id.get(sid)
                if s is not None:
                    self._sample_table.set_samples([s])
            # key == "__favorites__" root: ignore / do not change table
            return

        node = self._nodes.get(key)
        if node is not None:
            self._sample_table.set_samples(node.samples)

    def _on_sample_selected(self, sample) -> None:
        self._current_sample = sample
        self._current_seq += 1
        self._play_btn.setEnabled(True)
        seq = self._current_seq
        w = max(self._waveform_pane.width(), 200)
        QMetaObject.invokeMethod(
            self._worker, "request_peaks", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, seq), Q_ARG(str, sample.path), Q_ARG(int, w),
        )

    def _on_play(self) -> None:
        if self._current_sample is not None:
            self._player.play(self._current_sample.path)

    def _on_stop(self) -> None:
        self._player.stop()

    def _on_scan_analyze(self) -> None:
        self._status_bar.showMessage("Scanning and analyzing…")
        QMetaObject.invokeMethod(self._worker, "request_scan_analyze", Qt.ConnectionType.QueuedConnection)

    def _on_analyze_only(self) -> None:
        self._status_bar.showMessage("Analyzing pending…")
        QMetaObject.invokeMethod(self._worker, "request_scan_analyze", Qt.ConnectionType.QueuedConnection)

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

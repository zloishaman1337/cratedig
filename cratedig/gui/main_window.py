"""Main application window: wires panes, worker, and player together."""

from __future__ import annotations

from PySide6.QtCore import QMetaObject, QThread, Qt, Q_ARG
from PySide6.QtWidgets import (
    QDockWidget,
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
from .download_pane import DownloadPane
from .logic import is_sample_favorite, tree_rows
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
        self._search_seq = 0

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
        fav_action = toolbar.addAction("★ Favorite")
        fav_action.setShortcut("F")
        fav_action.setCheckable(True)
        fav_action.setEnabled(False)
        fav_action.triggered.connect(self._on_toggle_favorite)
        self._fav_action = fav_action

        # --- download dock (hidden until toggled) ---
        self._download_pane = DownloadPane()
        self._download_dock = QDockWidget("Download", self)
        self._download_dock.setWidget(self._download_pane)
        self._download_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._download_dock)
        self._download_dock.hide()
        download_action = toolbar.addAction("Download")
        download_action.triggered.connect(self._toggle_download)

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
        self._worker.searchReady.connect(self._on_search_ready)
        self._worker.downloadDone.connect(self._on_download_done)
        self._worker.failed.connect(self._on_worker_failed)

        self._tree_pane.folder_selected.connect(self._on_folder_selected)
        self._sample_table.sample_selected.connect(self._on_sample_selected)
        self._download_pane.search_requested.connect(self._on_search_requested)
        self._download_pane.download_requested.connect(self._on_download_requested)
        self._download_pane.preview_requested.connect(self._on_preview_requested)

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
        self._sync_fav_action()
        self._status_bar.showMessage(f"Loaded {len(samples)} samples", 3000)

    def _sync_fav_action(self) -> None:
        """Enable the ★ action only for a saved sample and reflect its fav state."""
        s = self._current_sample
        enabled = s is not None and s.id is not None
        self._fav_action.setEnabled(enabled)
        self._fav_action.setChecked(enabled and is_sample_favorite(self._favorites_by_id, s.id))

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
        self._sync_fav_action()
        # Auto-preview the selected sample (matches TUI highlight-to-play).
        try:
            self._player.play(sample.path)
        except Exception as exc:  # noqa: BLE001 — playback is best-effort
            self._status_bar.showMessage(f"Playback error: {exc}", 3000)
        seq = self._current_seq
        w = max(self._waveform_pane.width(), 200)
        QMetaObject.invokeMethod(
            self._worker, "request_peaks", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, seq), Q_ARG(str, sample.path), Q_ARG(int, w),
        )

    def _toggle_download(self) -> None:
        self._download_dock.setVisible(not self._download_dock.isVisible())

    def _on_search_requested(self, query: str, mode: str) -> None:
        self._search_seq += 1
        QMetaObject.invokeMethod(
            self._worker, "request_search", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, self._search_seq), Q_ARG(str, query), Q_ARG(str, mode), Q_ARG(int, 20),
        )

    def _on_search_ready(self, seq: int, hits: list, used: str) -> None:
        if seq != self._search_seq:
            return  # stale results from a superseded query
        self._download_pane.set_results(hits, used)

    def _on_download_requested(self, hit) -> None:
        QMetaObject.invokeMethod(
            self._worker, "request_download", Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, hit),
        )

    def _on_download_done(self, ok: bool, message: str) -> None:
        self._download_pane.set_status(message)
        self._status_bar.showMessage(message, 5000)

    def _on_preview_requested(self, hit) -> None:
        url = hit.preview_url()
        if not url:
            self._download_pane.set_status("no preview available for this hit")
            return
        try:
            self._player.play(url)
        except Exception as exc:  # noqa: BLE001 — preview is best-effort
            self._download_pane.set_status(f"preview error: {exc}")

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

    def _on_toggle_favorite(self) -> None:
        if self._current_sample is None or self._current_sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        self._status_bar.showMessage(f"toggling favorite: {self._current_sample.filename}")
        QMetaObject.invokeMethod(
            self._worker, "request_toggle_favorite", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, self._current_sample.id),
        )

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

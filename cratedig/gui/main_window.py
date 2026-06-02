"""Main application window: wires panes, worker, and player together."""

from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QMetaObject, QThread, Qt, Q_ARG, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStatusBar,
    QToolBar,
)

from ..config import Config
from ..db.database import Database
from ..audio.features import ASPECTS
from .download_pane import DownloadPane
from .logic import filename_parts, is_sample_favorite, tree_rows
from .metadata_panel import MetadataPanel
from .player import Player
from .sample_table import SampleTable
from .tag_editor import TagEditor
from .tree_pane import TreePane
from .waveform_pane import WaveformPane
from .worker import IndexWorker
from .als_explorer import AlsExplorerPanel


class MainWindow(QMainWindow):
    # Cross-thread requests carrying Python objects. Queued signal connections
    # register PyObject for us; Q_ARG(object, …) does not and raises QMetaType.
    _download_requested = Signal(object)
    _similar_requested = Signal(int, int, int, object)

    def __init__(self, db: Database, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("cratedig")
        self.resize(1200, 700)

        self._cfg = cfg
        self._player = Player()
        self._nodes: dict = {}
        self._favorites: list = []
        self._favorites_by_id: dict = {}
        self._tags_by_id: dict = {}
        self._all_tags: list = []
        self._current_sample = None
        self._current_seq = 0
        self._search_seq = 0
        self._similar_seq = 0

        # --- build panes ---
        self._tree_pane = TreePane()
        self._sample_table = SampleTable()
        self._waveform_pane = WaveformPane()

        # --- Row 1: Play / Stop / ★ Favorite ---
        play_btn = QPushButton("Play")
        stop_btn = QPushButton("Stop")
        fav_btn = QPushButton("★ Favorite")
        fav_btn.setCheckable(True)
        fav_btn.setShortcut("F")
        fav_btn.setEnabled(False)
        play_btn.setEnabled(False)
        self._play_btn = play_btn
        self._stop_btn = stop_btn
        self._fav_btn = fav_btn
        play_btn.clicked.connect(self._on_play)
        stop_btn.clicked.connect(self._on_stop)
        fav_btn.clicked.connect(self._on_toggle_favorite)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(play_btn)
        row1.addWidget(stop_btn)
        row1.addWidget(fav_btn)
        row1.addStretch()

        # --- Row 2: Find similar + aspect checkboxes ---
        similar_btn = QPushButton("Find similar")
        similar_btn.setShortcut("S")
        self._similar_btn = similar_btn
        similar_btn.clicked.connect(lambda: self._on_similar(self._current_sample))

        self._aspect_boxes: dict[str, QCheckBox] = {}
        for aspect in ASPECTS:
            cb = QCheckBox(aspect)
            cb.setChecked(aspect == "Overall")
            self._aspect_boxes[aspect] = cb

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(similar_btn)
        for cb in self._aspect_boxes.values():
            row2.addWidget(cb)
        row2.addStretch()

        btn_bar = QWidget()
        btn_layout = QVBoxLayout(btn_bar)
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setSpacing(2)
        btn_layout.addLayout(row1)
        btn_layout.addLayout(row2)

        self._tag_editor = TagEditor()
        self._metadata_panel = MetadataPanel()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._waveform_pane, stretch=2)
        right_layout.addWidget(btn_bar)
        right_layout.addWidget(self._metadata_panel, stretch=0)
        right_layout.addWidget(self._tag_editor, stretch=0)

        # --- download pane (permanent bottom section) ---
        self._download_pane = DownloadPane()

        # --- splitter layout ---
        # Top row: browser | table | preview. Bottom: Download, resizable.
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self._tree_pane)
        top_splitter.addWidget(self._sample_table)
        top_splitter.addWidget(right_panel)
        top_splitter.setSizes([220, 500, 380])

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self._download_pane)
        main_splitter.setSizes([500, 200])

        # --- stacked pages: 0 = samples, 1 = Ableton (ALS) explorer ---
        self._als_panel = AlsExplorerPanel()
        self._pages = QStackedWidget()
        self._pages.addWidget(main_splitter)    # index 0 — samples
        self._pages.addWidget(self._als_panel)  # index 1 — Ableton

        # --- left sidebar navigator (always visible) ---
        self._nav_samples = QPushButton("Samples")
        self._nav_ableton = QPushButton("Ableton")
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for idx, btn in enumerate((self._nav_samples, self._nav_ableton)):
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            self._nav_group.addButton(btn, idx)
        self._nav_samples.setChecked(True)
        self._nav_group.idClicked.connect(self._pages.setCurrentIndex)

        sidebar = QWidget()
        sidebar.setFixedWidth(96)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 6, 6, 6)
        sidebar_layout.setSpacing(4)
        sidebar_layout.addWidget(self._nav_samples)
        sidebar_layout.addWidget(self._nav_ableton)
        sidebar_layout.addStretch()

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(sidebar)
        central_layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        # --- toolbar (Duplicates only; Favorite moved to btn bar) ---
        toolbar = QToolBar("Actions")
        self.addToolBar(toolbar)

        dup_action = toolbar.addAction("Duplicates")
        dup_action.setShortcut("D")
        dup_action.triggered.connect(self._on_duplicates)

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
        self._worker.similarReady.connect(self._on_similar_ready)
        self._worker.duplicatesReady.connect(self._on_duplicates_ready)
        self._worker.downloadDone.connect(self._on_download_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.metadataReady.connect(self._on_metadata_ready)

        self._tree_pane.folder_selected.connect(self._on_folder_selected)
        self._tree_pane.scan_requested.connect(self._on_scan_analyze)
        self._tree_pane.analyze_requested.connect(self._on_analyze_only)
        self._sample_table.sample_selected.connect(self._on_sample_selected)
        self._download_pane.search_requested.connect(self._on_search_requested)
        self._download_pane.download_requested.connect(self._on_download_requested)
        self._download_pane.preview_requested.connect(self._on_preview_requested)

        self._sample_table.similar_requested.connect(self._on_similar)
        self._sample_table.rename_requested.connect(self._on_rename)
        self._sample_table.move_requested.connect(self._on_move)
        self._sample_table.delete_requested.connect(self._on_delete)
        self._sample_table.reveal_requested.connect(self._on_reveal)

        # Queued signal connections marshal Python objects across the thread
        # boundary without Q_ARG(object) (which has no QMetaType here).
        self._tag_editor.tags_committed.connect(
            self._worker.request_set_tags, Qt.ConnectionType.QueuedConnection
        )
        self._download_requested.connect(
            self._worker.request_download, Qt.ConnectionType.QueuedConnection
        )
        self._similar_requested.connect(
            self._worker.request_similar, Qt.ConnectionType.QueuedConnection
        )

        self._thread.start()

        # Initial data load — invoke on worker thread via queued call
        QMetaObject.invokeMethod(self._worker, "request_reload", Qt.ConnectionType.QueuedConnection)

    # --- slots ---

    def _on_tree_ready(self, nodes: dict, favorites: list, samples: list, tags: dict, all_tags: list) -> None:
        self._nodes = nodes
        self._favorites = favorites
        self._favorites_by_id = {s.id: s for s in favorites}
        self._tags_by_id = tags
        self._all_tags = all_tags
        rows = tree_rows(nodes, favorites)
        self._tree_pane.set_rows(rows)
        self._sync_fav_btn()
        self._refresh_tag_editor()
        if self._current_sample is None:
            self._metadata_panel.clear()
        self._status_bar.showMessage(f"Loaded {len(samples)} samples", 3000)

    def _refresh_tag_editor(self) -> None:
        """Load the current sample's tags into the under-waveform editor."""
        s = self._current_sample
        if s is None or s.id is None:
            self._tag_editor.set_sample(None, [], [])
            return
        current = self._tags_by_id.get(s.id, [])
        self._tag_editor.set_sample(s, current, self._all_tags)

    def _sync_fav_btn(self) -> None:
        """Enable the ★ button only for a saved sample and reflect its fav state."""
        s = self._current_sample
        enabled = s is not None and s.id is not None
        self._fav_btn.setEnabled(enabled)
        self._fav_btn.setChecked(enabled and is_sample_favorite(self._favorites_by_id, s.id))

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
                    self._sample_table.set_samples([s], self._tags_by_id)
            # key == "__favorites__" root: ignore / do not change table
            return

        node = self._nodes.get(key)
        if node is not None:
            self._sample_table.set_samples(node.samples, self._tags_by_id)

    def _on_sample_selected(self, sample) -> None:
        self._current_sample = sample
        self._current_seq += 1
        self._play_btn.setEnabled(True)
        self._sync_fav_btn()
        self._refresh_tag_editor()
        self._metadata_panel.set_metadata(sample, None)
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
        QMetaObject.invokeMethod(
            self._worker, "request_metadata", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, seq), Q_ARG(str, sample.path),
        )

    def _on_metadata_ready(self, seq: int, embedded) -> None:
        if seq != self._current_seq:
            return
        self._metadata_panel.set_metadata(self._current_sample, embedded)

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

    def _on_similar(self, sample) -> None:
        if sample is None or sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        aspects = [name for name, box in self._aspect_boxes.items() if box.isChecked()] or ["Overall"]
        self._similar_seq += 1
        self._status_bar.showMessage(f"finding similar to {sample.filename}…")
        self._similar_requested.emit(self._similar_seq, sample.id, 30, aspects)

    def _on_similar_ready(self, seq: int, samples: list, source_id: int, scores: dict) -> None:
        if seq != self._similar_seq:
            return  # stale results from a superseded request
        if not samples:
            self._status_bar.showMessage("no vector — run Analyze first", 4000)
            return
        self._sample_table.set_samples(samples, self._tags_by_id, scores=scores, show_path=True)
        self._status_bar.showMessage(f"{len(samples)} similar to #{source_id}", 4000)

    def _on_duplicates(self) -> None:
        self._status_bar.showMessage("finding duplicates…")
        QMetaObject.invokeMethod(self._worker, "request_duplicates", Qt.ConnectionType.QueuedConnection)

    def _on_duplicates_ready(self, samples: list) -> None:
        self._sample_table.set_samples(samples, self._tags_by_id)
        if not samples:
            self._status_bar.showMessage("no duplicates found", 4000)
            return
        groups = len({s.file_hash for s in samples if s.file_hash})
        self._status_bar.showMessage(f"{len(samples)} duplicate files across {groups} hash groups", 5000)

    def _on_download_requested(self, hit) -> None:
        self._download_requested.emit(hit)

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

    def _on_rename(self, sample) -> None:
        if sample is None or sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        current_name, extension = filename_parts(sample.filename)
        new_name, ok = QInputDialog.getText(self, "Rename", f"New name ({extension} kept):", text=current_name)
        new_stem = (
            filename_parts(new_name)[0]
            if extension and new_name.lower().endswith(extension.lower())
            else new_name
        )
        if ok and new_stem and new_stem != current_name:
            QMetaObject.invokeMethod(
                self._worker, "request_rename", Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, sample.id), Q_ARG(str, new_stem),
            )

    def _on_move(self, sample) -> None:
        if sample is None or sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        dest = QFileDialog.getExistingDirectory(self, "Move to…")
        if dest:
            QMetaObject.invokeMethod(
                self._worker, "request_move", Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, sample.id), Q_ARG(str, dest),
            )

    def _on_delete(self, sample) -> None:
        if sample is None or sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        answer = QMessageBox.question(
            self,
            "Delete",
            f"Move '{sample.filename}' to the recycle bin?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            QMetaObject.invokeMethod(
                self._worker, "request_delete", Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, sample.id),
            )

    def _on_reveal(self, sample) -> None:
        if sample is None or sample.id is None:
            self._status_bar.showMessage("select a saved sample first", 3000)
            return
        path = os.path.normpath(os.path.abspath(sample.path))
        try:
            # Pass one command string so subprocess does not wrap the
            # "/select,<path with spaces>" token in quotes — that quoting makes
            # explorer ignore the path and fall back to the default folder.
            subprocess.run(f'explorer /select,"{path}"')
        except Exception:  # noqa: BLE001
            try:
                os.startfile(os.path.dirname(path))
            except Exception:  # noqa: BLE001
                pass

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

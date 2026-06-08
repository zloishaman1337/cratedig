"""Main application window: wires panes, worker, and player together."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QMetaObject, QSettings, QThread, QTimer, Qt, Q_ARG, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QStatusBar,
)

from ..config import Config
from ..db.database import Database
from ..audio.features import ASPECTS
from ..audio.editor import render_edit  # noqa: F401 — monkeypatch hook; preview renders on the worker thread
from .download_pane import DownloadPane
from ..audio.playback import level_gain_db
from .logic import ABState, filename_parts, is_sample_favorite, tree_rows
from .metadata_panel import MetadataPanel
from .player import Player
from .sample_table import SampleTable
from .settings_dialog import SettingsDialog
from .tag_editor import TagEditor
from .tree_pane import TreePane
from .simpler_pane import SimplerPane
from .worker import IndexWorker
from .als_explorer import AlsExplorerPanel
from .health_panel import HealthPanel


class MainWindow(QMainWindow):
    # Cross-thread requests carrying Python objects. Queued signal connections
    # register PyObject for us; Q_ARG(object, …) does not and raises QMetaType.
    _download_requested = Signal(object)
    _similar_requested = Signal(int, int, int, object)
    _render_requested = Signal(int, str, object)
    _preview_requested = Signal(int, str, object)
    _als_match_requested = Signal(int, object)

    def __init__(self, db: Database, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("cratedig")
        self.resize(1200, 700)

        self._cfg = cfg
        self._player = Player()
        self._nodes: dict = {}
        self._favorites: list = []
        self._favorites_by_id: dict = {}
        self._crates: list = []
        self._crate_samples_by_id: dict = {}
        self._saved_folder_samples: dict = {}
        self._tags_by_id: dict = {}
        self._all_tags: list = []
        self._current_sample = None
        self._current_tree_key: str | None = None
        self._current_tree_is_fav = False
        self._current_seq = 0
        self._preview_seq = 0
        self._preview_pending_params: dict = {}
        self._search_seq = 0
        self._similar_seq = 0
        self._preview_edit_playing = False
        self._preview_started_at = 0.0
        self._preview_duration = 0.0
        self._preview_region: tuple[float, float] = (0.0, 0.0)
        self._preview_reverse = False
        self._preview_loop = False
        self._settings = QSettings("cratedig", "cratedig")
        self._auto_preview_on_select = self._settings.value(
            "playback/auto_preview_on_select",
            True,
            type=bool,
        )
        self._settings_dialog: SettingsDialog | None = None
        self._ab_state = ABState(slot_a=None, slot_b=None, current='a')
        self._als_match_seq = 0

        # --- build panes ---
        self._tree_pane = TreePane()
        self._sample_table = SampleTable()
        self._simpler_pane = SimplerPane(cfg.paths.saved_dir)

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
        row1.setSpacing(4)
        row1.addWidget(play_btn)
        row1.addWidget(stop_btn)
        row1.addWidget(fav_btn)
        row1.addStretch()

        transport_bar = QWidget()
        transport_layout = QVBoxLayout(transport_bar)
        transport_layout.setContentsMargins(4, 2, 4, 0)
        transport_layout.setSpacing(0)
        transport_layout.addLayout(row1)

        # --- Similar search: compact block placed next to metadata ---
        similar_btn = QPushButton("Find similar")
        similar_btn.setShortcut("S")
        self._similar_btn = similar_btn
        similar_btn.clicked.connect(lambda: self._on_similar(self._current_sample))

        self._aspect_boxes: dict[str, QCheckBox] = {}
        for aspect in ASPECTS:
            cb = QCheckBox(aspect)
            cb.setChecked(aspect == "Overall")
            self._aspect_boxes[aspect] = cb

        similar_grid = QGridLayout()
        similar_grid.setContentsMargins(0, 0, 0, 0)
        similar_grid.setHorizontalSpacing(4)
        similar_grid.setVerticalSpacing(0)
        similar_grid.addWidget(similar_btn, 0, 0)
        for idx, cb in enumerate(self._aspect_boxes.values()):
            row = 0 if idx < 2 else 1
            col = idx + 1 if idx < 2 else idx - 2
            similar_grid.addWidget(cb, row, col)
        similar_grid.setColumnStretch(4, 1)

        similar_bar = QWidget()
        similar_layout = QVBoxLayout(similar_bar)
        similar_layout.setContentsMargins(4, 0, 4, 2)
        similar_layout.setSpacing(2)
        similar_layout.addStretch()
        similar_layout.addLayout(similar_grid)
        similar_layout.addStretch()

        self._tag_editor = TagEditor()
        self._metadata_panel = MetadataPanel()
        self._metadata_panel.setMaximumWidth(170)

        metadata_row = QWidget()
        metadata_layout = QHBoxLayout(metadata_row)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(4)
        metadata_layout.addWidget(self._metadata_panel, stretch=0)
        metadata_layout.addWidget(similar_bar, stretch=1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._simpler_pane, stretch=1)
        right_layout.addWidget(transport_bar, stretch=0)
        right_layout.addWidget(metadata_row, stretch=0)
        right_layout.addWidget(self._tag_editor, stretch=0)

        # --- download pane (permanent bottom section) ---
        self._download_pane = DownloadPane()

        # --- splitter layout ---
        # Top row: browser | table | preview. Bottom: Download, resizable.
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self._tree_pane)
        top_splitter.addWidget(self._sample_table)
        top_splitter.addWidget(right_panel)
        top_splitter.setSizes([220, 680, 260])

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self._download_pane)
        main_splitter.setSizes([560, 140])

        # --- stacked pages: 0 = samples, 1 = Ableton (ALS) explorer, 2 = Health ---
        self._als_panel = AlsExplorerPanel()
        self._health_panel = HealthPanel()
        self._pages = QStackedWidget()
        self._pages.addWidget(main_splitter)      # index 0 — samples
        self._pages.addWidget(self._als_panel)    # index 1 — Ableton
        self._pages.addWidget(self._health_panel) # index 2 — Health

        # --- left sidebar navigator (always visible) ---
        self._settings_btn = QPushButton("Settings")
        self._duplicates_btn = QPushButton("Duplicates")
        self._ab_toggle_btn = QPushButton("AB Toggle")
        self._nav_samples = QPushButton("Samples")
        self._nav_ableton = QPushButton("Ableton")
        self._nav_health = QPushButton("Health")
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for btn in (self._settings_btn, self._duplicates_btn, self._ab_toggle_btn):
            btn.setMinimumHeight(40)
        for idx, btn in enumerate((self._nav_samples, self._nav_ableton, self._nav_health)):
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            self._nav_group.addButton(btn, idx)
        self._nav_samples.setChecked(True)
        self._nav_group.idClicked.connect(self._on_nav_clicked)
        self._duplicates_btn.setShortcut("D")
        self._ab_toggle_btn.setShortcut("X")
        self._settings_btn.clicked.connect(self._on_settings)
        self._duplicates_btn.clicked.connect(self._on_duplicates)
        self._ab_toggle_btn.clicked.connect(self.toggle_ab_slot)

        sidebar = QWidget()
        sidebar.setFixedWidth(80)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 6, 6, 6)
        sidebar_layout.setSpacing(4)
        sidebar_layout.addWidget(self._settings_btn)
        sidebar_layout.addWidget(self._duplicates_btn)
        sidebar_layout.addWidget(self._ab_toggle_btn)
        sidebar_layout.addWidget(self._nav_samples)
        sidebar_layout.addWidget(self._nav_ableton)
        sidebar_layout.addWidget(self._nav_health)
        sidebar_layout.addStretch()

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(sidebar)
        central_layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        # --- status bar ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._operation_progress = QProgressBar()
        self._operation_progress.setFixedWidth(220)
        self._operation_progress.setTextVisible(True)
        self._operation_progress.hide()
        self._status_bar.addPermanentWidget(self._operation_progress)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._poll_preview_playback)

        # --- worker thread ---
        self._thread = QThread(self)
        self._worker = IndexWorker(db, cfg)
        self._worker.moveToThread(self._thread)

        self._worker.treeReady.connect(self._on_tree_ready)
        self._worker.progress.connect(self._on_progress)
        self._worker.peaksReady.connect(self._on_peaks_ready)
        self._worker.searchReady.connect(self._on_search_ready)
        self._worker.searchProgress.connect(self._on_search_progress)
        self._worker.similarReady.connect(self._on_similar_ready)
        self._worker.duplicatesReady.connect(self._on_duplicates_ready)
        self._worker.downloadDone.connect(self._on_download_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.metadataReady.connect(self._on_metadata_ready)
        self._worker.renderReady.connect(self._on_render_ready)
        self._worker.previewReady.connect(self._on_preview_ready)
        self._worker.stageReady.connect(self._simpler_pane.set_staged_render_path)
        self._worker.healthReady.connect(self._health_panel.set_report)
        self._worker.alsMatchReady.connect(self._on_als_match_ready)

        self._als_panel.matchRequested.connect(self._on_als_match_requested)
        self._als_match_requested.connect(
            self._worker.request_als_match, Qt.ConnectionType.QueuedConnection
        )

        self._health_panel.refresh_requested.connect(self._on_health_refresh)
        self._health_panel.remove_missing_requested.connect(self._on_remove_missing)

        self._simpler_pane.preview_requested.connect(self._on_preview_edit)
        self._simpler_pane.preview_stop_requested.connect(self._on_stop_preview_edit)
        self._simpler_pane.preview_params_changed.connect(self._on_preview_edit)
        self._simpler_pane.export_requested.connect(self._on_export_edit)
        self._simpler_pane.exported.connect(self._on_dragged_export)

        self._tree_pane.folder_selected.connect(self._on_folder_selected)
        self._tree_pane.scan_requested.connect(self._on_scan_analyze)
        self._tree_pane.analyze_requested.connect(self._on_analyze_only)
        self._sample_table.sample_selected.connect(self._on_sample_selected)
        self._download_pane.search_requested.connect(self._on_search_requested)
        self._download_pane.download_requested.connect(self._on_download_requested)
        self._download_pane.preview_requested.connect(self._on_preview_requested)
        self._download_pane.refresh_metadata_requested.connect(
            self._worker.request_refresh_metadata, Qt.ConnectionType.QueuedConnection
        )

        self._sample_table.similar_requested.connect(self._on_similar)
        self._sample_table.rename_requested.connect(self._on_rename)
        self._sample_table.move_requested.connect(self._on_move)
        self._sample_table.delete_requested.connect(self._on_delete)
        self._sample_table.reveal_requested.connect(self._on_reveal)
        self._sample_table.add_to_crate_requested.connect(self._on_add_to_crate)
        self._sample_table.create_crate_requested.connect(self._on_create_crate)
        self._sample_table.set_ab_a_requested.connect(self.set_ab_slot_a)
        self._sample_table.set_ab_b_requested.connect(self.set_ab_slot_b)

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
        self._render_requested.connect(
            self._worker.request_render, Qt.ConnectionType.QueuedConnection
        )
        self._preview_requested.connect(
            self._worker.request_preview_render, Qt.ConnectionType.QueuedConnection
        )
        self._simpler_pane.render_stage_requested.connect(
            self._worker.request_stage_render, Qt.ConnectionType.QueuedConnection
        )

        self._thread.start()

        # Initial data load — invoke on worker thread via queued call
        QMetaObject.invokeMethod(self._worker, "request_reload", Qt.ConnectionType.QueuedConnection)

    # --- slots ---

    def _on_tree_ready(
        self,
        nodes: dict,
        favorites: list,
        crates: list,
        crate_samples_by_id: dict,
        samples: list,
        tags: dict,
        all_tags: list,
    ) -> None:
        self._nodes = nodes
        self._favorites = favorites
        self._favorites_by_id = {s.id: s for s in favorites}
        self._crates = crates
        self._crate_samples_by_id = crate_samples_by_id
        saved = [s for s in samples if getattr(s, "source", None) == "edit"]
        self._tags_by_id = tags
        self._all_tags = all_tags
        self._saved_folder_samples = {}
        saved_root = self._cfg.paths.saved_dir.resolve()
        for s in saved:
            path = Path(s.path)
            parent = path.parent
            label = parent.name
            try:
                rel_parent = parent.resolve().relative_to(saved_root)
            except (OSError, ValueError):
                rel_parent = Path(label)
            if rel_parent.parts:
                label = rel_parent.parts[0]
            else:
                try:
                    label = time.strftime("%d_%m_%Y", time.localtime(path.stat().st_mtime))
                except OSError:
                    label = time.strftime("%d_%m_%Y")
            self._saved_folder_samples.setdefault(label, []).append(s)
        rows = tree_rows(nodes, favorites, crates, saved, saved_root)
        self._tree_pane.set_rows(rows)
        self._tree_pane.set_crate_paths({
            crate_id: [s.path for s in members]
            for crate_id, members in crate_samples_by_id.items()
        })
        self._sample_table.set_crates(crates)
        self._refresh_current_tree_table()
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
        self._set_operation_progress(phase, done, total)
        if total > 0:
            self._status_bar.showMessage(f"{phase}: {done}/{total}")
        elif done > 0:
            self._status_bar.showMessage(f"{phase}: {done} processed")
        else:
            self._status_bar.showMessage(f"{phase}: done", 2000)

    def _set_operation_progress(self, phase: str, done: int, total: int) -> None:
        bar = self._operation_progress
        if total > 0:
            pct = int(round(max(0, min(done, total)) / total * 100))
            bar.setRange(0, 100)
            bar.setValue(pct)
            bar.setFormat(f"{phase}: {done}/{total} ({pct}%)")
            bar.show()
            return
        if done > 0:
            bar.setRange(0, 0)
            bar.setFormat(f"{phase}: {done}")
            bar.show()
            return
        bar.setRange(0, 100)
        bar.setValue(100)
        bar.setFormat(f"{phase}: done")
        bar.show()
        QTimer.singleShot(2000, bar.hide)

    def _on_peaks_ready(self, seq: int, mono) -> None:
        if seq != self._current_seq:
            return
        self._simpler_pane.set_mono(mono)

    def _on_worker_failed(self, context: str, message: str) -> None:
        self._status_bar.showMessage(f"Error [{context}]: {message}", 5000)

    def _on_settings(self) -> None:
        if self._settings_dialog is None:
            dialog = SettingsDialog(self._auto_preview_on_select, self)
            dialog.auto_preview_changed.connect(self._set_auto_preview_on_select)
            dialog.finished.connect(lambda _result: setattr(self, "_settings_dialog", None))
            self._settings_dialog = dialog
        self._settings_dialog.set_auto_preview_enabled(self._auto_preview_on_select)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _set_auto_preview_on_select(self, enabled: bool) -> None:
        self._auto_preview_on_select = bool(enabled)
        self._settings.setValue("playback/auto_preview_on_select", self._auto_preview_on_select)

    def _on_folder_selected(self, key: str, is_fav: bool) -> None:
        self._current_tree_key = key
        self._current_tree_is_fav = is_fav
        self._set_table_for_tree_key(key, is_fav)

    def _refresh_current_tree_table(self) -> None:
        if self._current_tree_key is None:
            return
        shown = self._set_table_for_tree_key(self._current_tree_key, self._current_tree_is_fav)
        if not shown and self._current_tree_key not in {"__favorites__", "__saved__", "__crates__"}:
            self._sample_table.set_samples([], self._tags_by_id)

    def _set_table_for_tree_key(self, key: str, is_fav: bool) -> bool:
        if is_fav:
            if key.startswith("fav:"):
                # Single favorite sample — look up from cached favorites (no DB on GUI thread)
                try:
                    sid = int(key[4:])
                except ValueError:
                    return False
                s = self._favorites_by_id.get(sid)
                if s is not None:
                    self._sample_table.set_samples([s], self._tags_by_id)
                    return True
                self._sample_table.set_samples([], self._tags_by_id)
                return True
            # key == "__favorites__" root: ignore / do not change table
            return False

        if key == "__saved__":
            return False
        if key.startswith("saved-dir:"):
            self._sample_table.set_samples(
                self._saved_folder_samples.get(key[10:], []),
                self._tags_by_id,
            )
            return True

        if key.startswith("crate:"):
            try:
                crate_id = int(key[6:])
            except ValueError:
                return False
            self._sample_table.set_samples(
                self._crate_samples_by_id.get(crate_id, []),
                self._tags_by_id,
            )
            return True
        if key == "__crates__":
            return False

        node = self._nodes.get(key)
        if node is not None:
            self._sample_table.set_samples(node.samples, self._tags_by_id)
            return True
        return False

    def _on_sample_selected(self, sample) -> None:
        self._current_sample = sample
        self._current_seq += 1
        self._set_preview_edit_playing(False)
        self._play_btn.setEnabled(True)
        self._sync_fav_btn()
        self._refresh_tag_editor()
        self._metadata_panel.set_metadata(sample, None)
        self._simpler_pane.set_sample(sample.path, getattr(sample, "duration_sec", None))
        # Auto-preview the selected sample (matches TUI highlight-to-play).
        if self._auto_preview_on_select:
            try:
                self._player.play(sample.path)
            except Exception as exc:  # noqa: BLE001 — playback is best-effort
                self._status_bar.showMessage(f"Playback error: {exc}", 3000)
        seq = self._current_seq
        w = max(self._simpler_pane.width(), 200)
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

    def _on_preview_edit(self, params: dict) -> None:
        """Delegate the edit render to the worker thread; play it on previewReady."""
        if not params.get("path"):
            return
        self._player.stop()
        self._set_preview_edit_playing(False)
        self._preview_seq += 1
        self._preview_pending_params = params
        if self._can_play_preview_direct(params):
            region = params.get("region")
            start = float(region[0]) if region else None
            duration = max(0.001, float(region[1]) - float(region[0])) if region else None
            try:
                self._player.play(
                    params["path"],
                    start_sec=start,
                    duration_sec=duration,
                    loop=bool(params.get("loop")),
                )
                self._start_preview_playhead(params, duration or 0.001)
                self._set_preview_edit_playing(True)
            except Exception as exc:  # noqa: BLE001
                self._set_preview_edit_playing(False)
                self._status_bar.showMessage(f"preview error: {exc}", 4000)
            return
        self._preview_requested.emit(self._preview_seq, params["path"], params)

    @staticmethod
    def _can_play_preview_direct(params: dict) -> bool:
        """True when ffplay can audition the region without a rendered temp WAV."""
        return (
            not bool(params.get("reverse"))
            and abs(float(params.get("gain_db", 0.0))) < 1e-9
            and float(params.get("fade_in", 0.0)) <= 0.0
            and float(params.get("fade_out", 0.0)) <= 0.0
            and not params.get("adsr")
        )

    def _on_preview_ready(self, seq: int, path: str, duration: float) -> None:
        if seq != self._preview_seq:
            return
        params = self._preview_pending_params
        try:
            self._player.play(Path(path), loop=bool(params.get("loop")))
            self._start_preview_playhead(params, duration)
            self._set_preview_edit_playing(True)
        except Exception as exc:  # noqa: BLE001
            self._set_preview_edit_playing(False)
            self._status_bar.showMessage(f"preview error: {exc}", 4000)

    def _on_stop_preview_edit(self) -> None:
        self._preview_seq += 1
        self._player.stop()
        self._set_preview_edit_playing(False)

    def _set_preview_edit_playing(self, playing: bool) -> None:
        self._preview_edit_playing = playing
        self._simpler_pane.set_preview_playing(playing)
        if playing:
            self._preview_timer.start()
        else:
            self._preview_timer.stop()
            self._preview_duration = 0.0
            self._preview_region = (0.0, 0.0)
            self._preview_reverse = False
            self._preview_loop = False

    def _poll_preview_playback(self) -> None:
        if self._preview_edit_playing and not self._player.is_playing():
            self._set_preview_edit_playing(False)
            return
        if self._preview_edit_playing:
            self._update_preview_playhead()

    def _start_preview_playhead(self, params: dict, duration: float) -> None:
        region = params.get("region") or (0.0, duration)
        start, end = float(region[0]), float(region[1])
        self._preview_started_at = time.monotonic()
        self._preview_duration = max(0.001, float(duration))
        self._preview_region = (start, end)
        self._preview_reverse = bool(params.get("reverse"))
        self._preview_loop = bool(params.get("loop"))
        self._update_preview_playhead()

    def _update_preview_playhead(self) -> None:
        if self._preview_duration <= 0:
            return
        elapsed = max(0.0, time.monotonic() - self._preview_started_at)
        if self._preview_loop:
            elapsed = elapsed % self._preview_duration
        else:
            elapsed = min(self._preview_duration, elapsed)
        start, end = self._preview_region
        ratio = elapsed / self._preview_duration
        if self._preview_reverse:
            pos = end - (end - start) * ratio
        else:
            pos = start + (end - start) * ratio
        self._simpler_pane.set_preview_playhead(pos)

    def _on_export_edit(self, params: dict) -> None:
        if not params.get("path"):
            self._status_bar.showMessage("select a sample first", 3000)
            return
        self._current_seq += 1
        self._status_bar.showMessage("rendering edit…")
        self._render_requested.emit(self._current_seq, params["path"], params)

    def _on_render_ready(self, seq: int, dest: str) -> None:
        self._status_bar.showMessage(f"exported → {dest}", 5000)

    def _on_dragged_export(self, dest: str) -> None:
        """A drag-export already wrote the WAV; index the Saved folder and reload."""
        QMetaObject.invokeMethod(self._worker, "request_index_saved", Qt.ConnectionType.QueuedConnection)
        self._status_bar.showMessage(f"exported → {dest}", 5000)

    def _on_search_requested(self, query: str, mode: str) -> None:
        self._search_seq += 1
        self._download_pane.set_progress(None)
        self._download_pane.set_status("Searching…")
        QMetaObject.invokeMethod(
            self._worker, "request_search", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, self._search_seq), Q_ARG(str, query), Q_ARG(str, mode), Q_ARG(int, 20),
        )

    _SEARCH_PHASE_LABELS = {"hits": "Searching backends…", "metadata": "Enriching metadata…"}

    def _on_search_progress(self, seq: int, phase: str) -> None:
        if seq != self._search_seq:
            return
        self._download_pane.set_status(self._SEARCH_PHASE_LABELS.get(phase, phase))
        self._download_pane.set_progress(None)

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
        if not samples:
            self._status_bar.showMessage("no duplicates found", 4000)
            return
        from .duplicates_dialog import DuplicatesDialog
        dlg = DuplicatesDialog(samples, self._cfg.paths.saved_dir, parent=self)
        dlg.reveal_requested.connect(self._reveal_path)
        dlg.delete_requested.connect(self._delete_sample_id)
        dlg.show()
        self._dup_dialog = dlg

    def _on_nav_clicked(self, idx: int) -> None:
        self._pages.setCurrentIndex(idx)
        if idx == 2:  # Health page — refresh stats on open
            self._on_health_refresh()

    def _on_health_refresh(self) -> None:
        self._status_bar.showMessage("computing library health…")
        QMetaObject.invokeMethod(self._worker, "request_health", Qt.ConnectionType.QueuedConnection)

    def _on_remove_missing(self) -> None:
        answer = QMessageBox.question(
            self, "Remove missing", "Remove all missing-file rows from the database?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            QMetaObject.invokeMethod(self._worker, "request_remove_missing", Qt.ConnectionType.QueuedConnection)

    def _on_download_requested(self, hit) -> None:
        self._download_requested.emit(hit)

    def _on_download_done(self, ok: bool, message: str) -> None:
        self._download_pane.finish_download(ok, message)
        self._status_bar.showMessage(message, 5000)

    def _on_preview_requested(self, hit) -> None:
        url = hit.preview_url()
        if not url:
            self._download_pane.set_status("no preview available for this hit")
            return
        try:
            self._set_preview_edit_playing(False)
            self._player.play(url)
        except Exception as exc:  # noqa: BLE001 — preview is best-effort
            self._download_pane.set_status(f"preview error: {exc}")

    def _on_play(self) -> None:
        if self._current_sample is not None:
            self._set_preview_edit_playing(False)
            self._player.play(self._current_sample.path)

    def _on_stop(self) -> None:
        self._player.stop()
        self._set_preview_edit_playing(False)

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

    def _on_add_to_crate(self, sample, crate_id: int) -> None:
        if sample is None or sample.id is None:
            return
        QMetaObject.invokeMethod(
            self._worker,
            "request_add_to_crate",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, sample.id),
            Q_ARG(int, crate_id),
        )

    def _on_create_crate(self, sample, _name: str = "") -> None:
        if sample is None or sample.id is None:
            return
        name, ok = QInputDialog.getText(self, "New crate", "Crate name:")
        if ok and name.strip():
            QMetaObject.invokeMethod(
                self._worker,
                "request_create_crate_with_sample",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, sample.id),
                Q_ARG(str, name.strip()),
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
        try:
            Path(sample.path).resolve().relative_to(self._cfg.paths.saved_dir.resolve())
            is_in_saved_dir = True
        except (OSError, ValueError):
            is_in_saved_dir = False
        is_saved = getattr(sample, "source", None) == "edit" or is_in_saved_dir
        answer = QMessageBox.question(
            self,
            "Delete",
            (
                f"Delete saved file '{sample.filename}'?"
                if is_saved
                else f"Move '{sample.filename}' to the recycle bin?"
            ),
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
        self._reveal_path(sample.path)

    def _reveal_path(self, path: str) -> None:
        path = os.path.normpath(os.path.abspath(path))
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

    def _delete_sample_id(self, sample_id: int) -> None:
        QMetaObject.invokeMethod(
            self._worker, "request_delete", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, sample_id),
        )

    def set_ab_slot_a(self, sample_id: int | None) -> None:
        """Assign sample_id to A slot and switch playback to A."""
        self._ab_state = self._ab_state.set_a(sample_id)
        self._ab_state = ABState(slot_a=self._ab_state.slot_a, slot_b=self._ab_state.slot_b, current='a')
        self._play_ab_active()

    def set_ab_slot_b(self, sample_id: int | None) -> None:
        """Assign sample_id to B slot and switch playback to B."""
        self._ab_state = self._ab_state.set_b(sample_id)
        self._ab_state = ABState(slot_a=self._ab_state.slot_a, slot_b=self._ab_state.slot_b, current='b')
        self._play_ab_active()

    def toggle_ab_slot(self) -> None:
        """Toggle A/B and play the newly active sample (no-op when both slots empty)."""
        if self._ab_state.slot_a is None and self._ab_state.slot_b is None:
            return
        try:
            new_state, active_id = self._ab_state.toggle()
        except ValueError:
            return
        self._ab_state = new_state
        self._play_ab_active(active_id=active_id)

    def _play_ab_active(self, *, active_id: int | None = None) -> None:
        """Play the active A/B slot's file, applying loudness leveling if enabled."""
        sid = active_id if active_id is not None else self._ab_state.active_id()
        if sid is None:
            return
        # Look up file path from current sample table or cached samples.
        path: str | None = None
        loudness: float | None = None
        for samples in (
            getattr(self._sample_table, "_samples", []),
            self._favorites,
        ):
            for s in samples:
                if getattr(s, "id", None) == sid:
                    path = s.path
                    loudness = getattr(s, "loudness_lufs", None)
                    break
            if path:
                break

        if not path:
            return

        if self._player.apply_loudness_leveling and loudness is not None:
            # Determine the other slot's loudness for gain computation.
            other_slot = self._ab_state.slot_b if self._ab_state.current == 'a' else self._ab_state.slot_a
            other_loudness: float | None = None
            if other_slot is not None:
                for samples in (getattr(self._sample_table, "_samples", []), self._favorites):
                    for s in samples:
                        if getattr(s, "id", None) == other_slot:
                            other_loudness = getattr(s, "loudness_lufs", None)
                            break
                    if other_loudness is not None:
                        break
            if other_loudness is not None:
                try:
                    # Convert LUFS (negative dB) to linear amplitude proxy for level_gain_db.
                    import math as _math
                    ref_lin = _math.pow(10.0, loudness / 20.0)
                    other_lin = _math.pow(10.0, other_loudness / 20.0)
                    _gain = level_gain_db(ref_lin, other_lin)
                    # gain is informational; ffplay gain application is future work
                except (ValueError, ZeroDivisionError):
                    pass

        try:
            self._player.play(path)
        except Exception as exc:  # noqa: BLE001 — playback best-effort
            self._status_bar.showMessage(f"A/B playback error: {exc}", 3000)

    def _on_als_match_requested(self, names) -> None:
        self._als_match_seq += 1
        self._als_match_requested.emit(self._als_match_seq, names)

    def _on_als_match_ready(self, seq: int, result: dict) -> None:
        if seq != self._als_match_seq:
            return
        self._als_panel.set_match_result(result)

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

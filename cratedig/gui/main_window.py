"""Main application window: wires panes, worker, and player together."""

from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import (
    QByteArray, QEvent, QMetaObject, QSettings, QStringListModel, QThread, QTimer, Qt, Q_ARG, Signal,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QCompleter,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
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
from .logic import filename_parts, filter_samples, is_sample_favorite, tree_rows
from .metadata_panel import MetadataPanel
from .player import Player
from .sample_table import SampleTable
from .settings_dialog import SettingsDialog
from .settings_tabs import _keys
from .toast import ToastManager
from .theme import app_icon, icon
from .tag_editor import TagEditor
from .tree_pane import TreePane
from .simpler_pane import SimplerPane
from .worker import IndexWorker
from .als_explorer import AlsExplorerPanel
from .health_panel import HealthPanel
from .platform_files import reveal_in_file_manager


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
        self.setWindowIcon(app_icon())
        self.resize(1320, 760)

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
        self._als_match_actions_wired = False  # connect ALS match-row actions once
        self._similar_seq = 0
        self._preview_edit_playing = False
        self._preview_started_at = 0.0
        self._preview_duration = 0.0
        self._preview_region: tuple[float, float] = (0.0, 0.0)
        self._preview_reverse = False
        self._preview_loop = False
        self._settings = QSettings("cratedig", "cratedig")
        self._player.apply_loudness_leveling = self._settings.value(
            _keys.AB_LOUDNESS_LEVELING,
            _keys.DEFAULTS[_keys.AB_LOUDNESS_LEVELING],
            type=bool,
        )
        self._auto_preview_on_select = self._settings.value(
            _keys.AUTO_PREVIEW_ON_SELECT,
            _keys.DEFAULTS[_keys.AUTO_PREVIEW_ON_SELECT],
            type=bool,
        )
        self._settings_dialog: SettingsDialog | None = None
        self._als_match_seq = 0
        self._all_samples: list = []  # cached full sample set for client-side library filter

        # --- build panes ---
        expand_tree = self._settings.value(
            _keys.EXPAND_TREE_ON_LOAD,
            _keys.DEFAULTS[_keys.EXPAND_TREE_ON_LOAD],
            type=bool,
        )
        self._expand_tree_on_load = expand_tree
        self._tree_pane = TreePane()
        self._sample_table = SampleTable(settings=self._settings)
        self._simpler_pane = SimplerPane(cfg.paths.saved_dir)

        # --- Row 1: Play / Stop / ★ Favorite ---
        play_btn = QPushButton("Play")
        stop_btn = QPushButton("Stop")
        fav_btn = QPushButton("★ Favorite")
        play_btn.setIcon(icon("play"))
        stop_btn.setIcon(icon("stop"))
        fav_btn.setIcon(icon("favorite"))
        play_btn.setProperty("primary", True)
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
        similar_btn.setIcon(icon("search"))
        similar_btn.setShortcut("S")
        self._similar_btn = similar_btn
        similar_btn.clicked.connect(lambda: self._on_similar(self._current_sample))

        _default_aspects = self._settings.value(
            _keys.DEFAULT_SIMILAR_ASPECTS,
            _keys.DEFAULTS[_keys.DEFAULT_SIMILAR_ASPECTS],
            type=list,
        )
        self._aspect_boxes: dict[str, QCheckBox] = {}
        for aspect in ASPECTS:
            cb = QCheckBox(aspect)
            cb.setChecked(aspect in _default_aspects)
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
        metadata_row.setObjectName("Panel")
        metadata_layout = QHBoxLayout(metadata_row)
        metadata_layout.setContentsMargins(8, 6, 8, 6)
        metadata_layout.setSpacing(8)
        metadata_layout.addWidget(self._metadata_panel, stretch=0)
        metadata_layout.addWidget(similar_bar, stretch=1)

        right_panel = QWidget()
        right_panel.setObjectName("Panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._simpler_pane, stretch=1)
        right_layout.addWidget(transport_bar, stretch=0)
        right_layout.addWidget(metadata_row, stretch=0)
        right_layout.addWidget(self._tag_editor, stretch=0)

        # --- download pane (permanent bottom section) ---
        self._download_pane = DownloadPane(settings=self._settings)

        # --- library search bar (filters the cached sample set client-side) ---
        self._lib_search = QLineEdit()
        self._lib_search.setPlaceholderText("Filter library by name...")
        self._lib_search.setClearButtonEnabled(True)
        self._lib_tag_search = QLineEdit()
        self._lib_tag_search.setPlaceholderText("tags (comma/space separated)...")
        self._lib_tag_search.setClearButtonEnabled(True)
        self._lib_tag_completer = QCompleter(self)
        self._lib_tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._lib_tag_completer.setModel(QStringListModel([], self))
        self._lib_tag_search.setCompleter(self._lib_tag_completer)
        self._lib_tag_search.installEventFilter(self)

        self._lib_search_timer = QTimer(self)
        self._lib_search_timer.setSingleShot(True)
        self._lib_search_timer.setInterval(200)
        self._lib_search_timer.timeout.connect(self._apply_library_filter)
        self._lib_search.textChanged.connect(lambda _=None: self._lib_search_timer.start())
        self._lib_tag_search.textChanged.connect(lambda _=None: self._lib_search_timer.start())

        search_row = QHBoxLayout()
        search_row.setContentsMargins(8, 8, 8, 4)
        search_row.setSpacing(8)
        search_row.addWidget(self._lib_search, stretch=2)
        search_row.addWidget(self._lib_tag_search, stretch=1)

        table_container = QWidget()
        table_container.setObjectName("Panel")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
        table_layout.addLayout(search_row)
        table_layout.addWidget(self._sample_table)

        # --- splitter layout ---
        # Top row: browser | table | preview. Bottom: Download, resizable.
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.addWidget(self._tree_pane)
        self._top_splitter.addWidget(table_container)
        self._top_splitter.addWidget(right_panel)
        self._top_splitter.setSizes([220, 680, 260])

        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(self._top_splitter)
        self._main_splitter.addWidget(self._download_pane)
        self._main_splitter.setSizes([560, 140])

        # --- stacked pages: 0 = samples, 1 = Ableton (ALS) explorer, 2 = Health ---
        self._als_panel = AlsExplorerPanel()
        self._health_panel = HealthPanel()
        self._pages = QStackedWidget()
        self._pages.setObjectName("PageSurface")
        self._pages.addWidget(self._main_splitter) # index 0 — samples
        self._pages.addWidget(self._als_panel)     # index 1 — Ableton
        self._pages.addWidget(self._health_panel)  # index 2 — Health

        # --- left sidebar navigator (always visible) ---
        self._settings_btn = QPushButton("Settings")
        self._duplicates_btn = QPushButton("Duplicates")
        self._ab_compare_btn = QPushButton("A/B Compare")
        self._nav_samples = QPushButton("Samples")
        self._nav_ableton = QPushButton("Ableton")
        self._nav_health = QPushButton("Health")
        self._settings_btn.setIcon(icon("settings"))
        self._duplicates_btn.setIcon(icon("duplicates"))
        self._ab_compare_btn.setIcon(icon("compare"))
        self._nav_samples.setIcon(icon("samples"))
        self._nav_ableton.setIcon(icon("ableton"))
        self._nav_health.setIcon(icon("health"))
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for btn in (self._settings_btn, self._duplicates_btn, self._ab_compare_btn):
            btn.setMinimumHeight(38)
        for idx, btn in enumerate((self._nav_samples, self._nav_ableton, self._nav_health)):
            btn.setCheckable(True)
            btn.setMinimumHeight(38)
            self._nav_group.addButton(btn, idx)
        self._nav_samples.setChecked(True)
        self._nav_group.idClicked.connect(self._on_nav_clicked)
        self._duplicates_btn.setShortcut("D")
        self._settings_btn.clicked.connect(self._on_settings)
        self._duplicates_btn.clicked.connect(self._on_duplicates)
        self._ab_compare_btn.clicked.connect(self._open_ab_compare)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(148)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 12, 10, 10)
        sidebar_layout.setSpacing(6)
        brand = QLabel("▣ CRATEDIG")
        brand.setObjectName("SidebarTitle")
        section_tools = QLabel("Tools")
        section_tools.setObjectName("SectionTitle")
        section_library = QLabel("Workspace")
        section_library.setObjectName("SectionTitle")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(section_tools)
        sidebar_layout.addWidget(self._settings_btn)
        sidebar_layout.addWidget(self._duplicates_btn)
        sidebar_layout.addWidget(self._ab_compare_btn)
        sidebar_layout.addSpacing(10)
        sidebar_layout.addWidget(section_library)
        sidebar_layout.addWidget(self._nav_samples)
        sidebar_layout.addWidget(self._nav_ableton)
        sidebar_layout.addWidget(self._nav_health)
        sidebar_layout.addStretch()

        central = QWidget()
        central.setObjectName("AppShell")
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(sidebar)
        central_layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)
        self._toasts = ToastManager(central)

        # Restore window geometry and splitter state if prefs say so
        if self._settings.value(_keys.REMEMBER_WINDOW_GEOMETRY, _keys.DEFAULTS[_keys.REMEMBER_WINDOW_GEOMETRY], type=bool):
            geom = self._settings.value("browser/window_geometry")
            if isinstance(geom, (bytes, QByteArray)) and geom:
                self.restoreGeometry(geom if isinstance(geom, QByteArray) else QByteArray(geom))
        if self._settings.value(_keys.REMEMBER_SPLITTER_SIZES, _keys.DEFAULTS[_keys.REMEMBER_SPLITTER_SIZES], type=bool):
            top_state = self._settings.value("browser/top_splitter_state")
            if isinstance(top_state, (bytes, QByteArray)) and top_state:
                self._top_splitter.restoreState(top_state if isinstance(top_state, QByteArray) else QByteArray(top_state))
            main_state = self._settings.value("browser/main_splitter_state")
            if isinstance(main_state, (bytes, QByteArray)) and main_state:
                self._main_splitter.restoreState(main_state if isinstance(main_state, QByteArray) else QByteArray(main_state))

        # --- status bar ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.messageChanged.connect(self._on_status_message)
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
        self._download_pane.notification_requested.connect(
            lambda text: self._toasts.show(text, "ok" if "complete" in text.lower() else "error")
        )
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
        self._all_samples = samples
        self._lib_tag_completer.setModel(QStringListModel(sorted(all_tags), self))
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
        self._tree_pane.set_rows(rows, expand=self._expand_tree_on_load)
        self._tree_pane.set_crate_paths({
            crate_id: [s.path for s in members]
            for crate_id, members in crate_samples_by_id.items()
        })
        self._sample_table.set_crates(crates)
        # Restore last-used folder if pref set and no current selection
        if (
            self._current_tree_key is None
            and self._settings.value(_keys.RESTORE_LAST_FOLDER, _keys.DEFAULTS[_keys.RESTORE_LAST_FOLDER], type=bool)
        ):
            last = self._settings.value("browser/last_folder", "", type=str)
            if last:
                self._tree_pane.select_key(last)
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
            dialog = SettingsDialog(self._auto_preview_on_select, settings=self._settings, parent=self)
            dialog.auto_preview_changed.connect(self._set_auto_preview_on_select)
            dialog.preferences_changed.connect(self._on_preference_changed)
            dialog.config_written.connect(self._on_config_written)
            dialog.finished.connect(lambda _result: setattr(self, "_settings_dialog", None))
            self._settings_dialog = dialog
        self._settings_dialog.set_auto_preview_enabled(self._auto_preview_on_select)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _set_auto_preview_on_select(self, enabled: bool) -> None:
        self._auto_preview_on_select = bool(enabled)
        self._settings.setValue(_keys.AUTO_PREVIEW_ON_SELECT, self._auto_preview_on_select)

    def _on_preference_changed(self, key: str, value: object) -> None:
        if key == _keys.AUTO_PREVIEW_ON_SELECT:
            self._auto_preview_on_select = bool(value)
        elif key == _keys.AB_LOUDNESS_LEVELING:
            self._player.apply_loudness_leveling = bool(value)
        elif key == _keys.SHOW_TAGS_COLUMN:
            self._sample_table.set_tags_visible(bool(value))
        elif key == _keys.EXPAND_TREE_ON_LOAD:
            self._expand_tree_on_load = bool(value)

    def _on_config_written(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(self)
        box.setWindowTitle("Restart required")
        box.setText("Settings saved. Restart now to apply changes?")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._restart_app()
        else:
            self._toasts.show("Config saved — restart required to apply changes.", "info")

    def _restart_app(self) -> None:
        """Relaunch the app so reloaded config takes effect, then quit this instance."""
        import sys

        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication

        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, [])
        else:
            QProcess.startDetached(sys.executable, ["-m", "cratedig.gui"])
        QApplication.quit()

    def _on_folder_selected(self, key: str, is_fav: bool) -> None:
        self._current_tree_key = key
        self._current_tree_is_fav = is_fav
        self._settings.setValue("browser/last_folder", key)
        # Touch recent folders in the DB for file-system folder keys only
        if not is_fav and not key.startswith(("__", "fav:", "crate:", "saved-dir:")):
            QMetaObject.invokeMethod(
                self._worker, "request_touch_recent_folder",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, key),
            )
        self._set_table_for_tree_key(key, is_fav)

    def _refresh_current_tree_table(self) -> None:
        if self._current_tree_key is None:
            return
        shown = self._set_table_for_tree_key(self._current_tree_key, self._current_tree_is_fav)
        if not shown and self._current_tree_key not in {"__favorites__", "__saved__", "__crates__"}:
            self._sample_table.set_samples([], self._tags_by_id)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._lib_tag_search and event.type() == QEvent.Type.FocusIn:
            QTimer.singleShot(0, self._show_all_tag_completions)
        return super().eventFilter(obj, event)

    def _show_all_tag_completions(self) -> None:
        if not self._lib_tag_search.hasFocus():
            return
        if not self._lib_tag_search.text().strip():
            self._lib_tag_completer.setCompletionPrefix("")
        self._lib_tag_completer.complete()

    def _apply_library_filter(self) -> None:
        """Filter the cached sample set by name + tags; empty query restores tree view."""
        text = self._lib_search.text().strip()
        raw_tags = self._lib_tag_search.text().replace(",", " ")
        tags = [t for t in raw_tags.split() if t]
        if not text and not tags:
            self._refresh_current_tree_table()
            return
        results = filter_samples(self._all_samples, self._tags_by_id, text, tags)
        self._sample_table.set_samples(results, self._tags_by_id, show_path=True)
        self._status_bar.showMessage(f"{len(results)} match(es)", 3000)

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
        limit = self._settings.value(
            _keys.DOWNLOAD_SEARCH_LIMIT,
            _keys.DEFAULTS[_keys.DOWNLOAD_SEARCH_LIMIT],
            type=int,
        )
        QMetaObject.invokeMethod(
            self._worker, "request_search", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, self._search_seq), Q_ARG(str, query), Q_ARG(str, mode), Q_ARG(int, limit),
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
        k = self._settings.value(
            _keys.SIMILAR_RESULTS_COUNT,
            _keys.DEFAULTS[_keys.SIMILAR_RESULTS_COUNT],
            type=int,
        )
        self._similar_requested.emit(self._similar_seq, sample.id, k, aspects)

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
        existing = getattr(self, "_dup_dialog", None)
        if existing is not None and existing.isVisible():
            # Live-refresh the open dialog instead of stacking a new one.
            existing.reload(samples)
            if not samples:
                self._status_bar.showMessage("all duplicates resolved", 4000)
            return
        if not samples:
            self._status_bar.showMessage("no duplicates found", 4000)
            return
        from .duplicates_dialog import DuplicatesDialog
        dlg = DuplicatesDialog(samples, self._cfg.paths.saved_dir, parent=self)
        dlg.reveal_requested.connect(self._reveal_path)
        dlg.delete_requested.connect(self._delete_sample_id)
        dlg.group_resolved.connect(self._on_duplicates)
        dlg.show()
        self._dup_dialog = dlg

    def _open_ab_compare(self) -> None:
        from .ab_dialog import ABCompareDialog
        dlg = ABCompareDialog(
            getattr(self, "_nodes", {}),
            self._crates,
            self._worker,
            self._player,
            parent=self,
        )
        dlg.add_to_crate_requested.connect(self._on_add_to_crate)
        dlg.create_crate_requested.connect(self._on_create_crate)
        dlg.exec()

    def _on_nav_clicked(self, idx: int) -> None:
        self._pages.setCurrentIndex(idx)
        if idx == 2:  # Health page
            auto_refresh = self._settings.value(
                _keys.AUTO_REFRESH_HEALTH_ON_OPEN,
                _keys.DEFAULTS[_keys.AUTO_REFRESH_HEALTH_ON_OPEN],
                type=bool,
            )
            if auto_refresh:
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
        confirm_delete = self._settings.value(
            _keys.CONFIRM_DELETE, _keys.DEFAULTS[_keys.CONFIRM_DELETE], type=bool
        )
        if confirm_delete:
            answer = QMessageBox.question(
                self,
                "Delete",
                (
                    f"Delete saved file '{sample.filename}'?"
                    if is_saved
                    else f"Move '{sample.filename}' to the recycle bin?"
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
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
        reveal_in_file_manager(path)

    def _delete_sample_id(self, sample_id: int) -> None:
        QMetaObject.invokeMethod(
            self._worker, "request_delete", Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, sample_id),
        )

    def _on_status_message(self, text: str) -> None:
        """Route status messages to bottom-right toasts (progress excluded)."""
        if not text:
            return
        # High-frequency progress ticks stay on the bar only — no toast spam.
        if text.endswith("processed") or re.search(r"\d+/\d+\b", text):
            return
        low = text.lower()
        level = "error" if ("error" in low or "failed" in low) else "info"
        self._toasts.show(text, level)
        QTimer.singleShot(0, self._status_bar.clearMessage)

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._toasts.reposition()

    def _on_als_match_requested(self, names) -> None:
        self._als_match_seq += 1
        self._als_match_requested.emit(self._als_match_seq, names)

    def _on_als_match_ready(self, seq: int, result: dict) -> None:
        if seq != self._als_match_seq:
            return
        if not getattr(self, "_als_match_actions_wired", False):
            self._als_panel.reveal_requested.connect(self._reveal_path)
            self._als_panel.add_to_crate_requested.connect(self._on_add_to_crate)
            self._als_panel.create_crate_requested.connect(self._on_create_crate)
            self._als_match_actions_wired = True
        self._als_panel.set_crates(self._crates)
        self._als_panel.set_match_result(result)

    def closeEvent(self, event) -> None:
        # Persist window geometry and splitter state
        if self._settings.value(_keys.REMEMBER_WINDOW_GEOMETRY, _keys.DEFAULTS[_keys.REMEMBER_WINDOW_GEOMETRY], type=bool):
            self._settings.setValue("browser/window_geometry", self.saveGeometry())
        if self._settings.value(_keys.REMEMBER_SPLITTER_SIZES, _keys.DEFAULTS[_keys.REMEMBER_SPLITTER_SIZES], type=bool):
            self._settings.setValue("browser/top_splitter_state", self._top_splitter.saveState())
            self._settings.setValue("browser/main_splitter_state", self._main_splitter.saveState())
        # Persist column state
        self._sample_table.save_column_state()
        self._player.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

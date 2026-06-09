"""Preferences tab — QSettings-backed live-apply preferences."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import _keys


_ASPECTS = ["Overall", "Spectrum", "Timbre", "Pitch", "Amplitude"]


def _group_layout(box: QGroupBox) -> QVBoxLayout:
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(5)
    return layout


def _group_form(box: QGroupBox) -> QFormLayout:
    form = QFormLayout(box)
    form.setContentsMargins(12, 10, 12, 10)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(7)
    return form


class PreferencesTab(QWidget):
    """Preferences tab backed by QSettings. Writes on every widget change."""

    preference_changed = Signal(str, object)

    def __init__(self, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_playback_group())
        layout.addWidget(self._build_browser_group())
        layout.addWidget(self._build_search_group())
        layout.addWidget(self._build_safety_group())
        layout.addStretch()

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _build_playback_group(self) -> QGroupBox:
        box = QGroupBox("Playback")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        self._auto_preview = self._bool_checkbox(
            "Auto-preview on sample select", _keys.AUTO_PREVIEW_ON_SELECT
        )
        self._stop_before_preview = self._bool_checkbox(
            "Stop before preview", _keys.STOP_BEFORE_PREVIEW
        )
        self._loop_edited = self._bool_checkbox(
            "Loop edited by default", _keys.LOOP_EDITED_BY_DEFAULT
        )
        self._ab_leveling = self._bool_checkbox(
            "A/B loudness leveling", _keys.AB_LOUDNESS_LEVELING
        )
        self._preview_download = self._bool_checkbox(
            "Preview download on row select", _keys.PREVIEW_DOWNLOAD_ON_ROW_SELECT
        )

        for w in (
            self._auto_preview,
            self._stop_before_preview,
            self._loop_edited,
            self._ab_leveling,
            self._preview_download,
        ):
            layout.addWidget(w)
        return box

    def _build_browser_group(self) -> QGroupBox:
        box = QGroupBox("Browser / Table")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        self._show_tags = self._bool_checkbox("Show tags column", _keys.SHOW_TAGS_COLUMN)
        self._remember_widths = self._bool_checkbox(
            "Remember column widths", _keys.REMEMBER_COLUMN_WIDTHS
        )
        self._remember_visibility = self._bool_checkbox(
            "Remember column visibility", _keys.REMEMBER_COLUMN_VISIBILITY
        )
        self._remember_geometry = self._bool_checkbox(
            "Remember window geometry (applies on restart)",
            _keys.REMEMBER_WINDOW_GEOMETRY,
        )
        self._remember_splitters = self._bool_checkbox(
            "Remember splitter sizes (applies on restart)",
            _keys.REMEMBER_SPLITTER_SIZES,
        )
        self._expand_tree = self._bool_checkbox(
            "Expand tree on load", _keys.EXPAND_TREE_ON_LOAD
        )
        self._restore_folder = self._bool_checkbox(
            "Restore last folder (applies on restart)", _keys.RESTORE_LAST_FOLDER
        )

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        self._recent_folders_max = QSpinBox()
        self._recent_folders_max.setRange(1, 100)
        self._recent_folders_max.setValue(
            int(self._settings.value(_keys.RECENT_FOLDERS_MAX, _keys.DEFAULTS[_keys.RECENT_FOLDERS_MAX], type=int))
        )
        self._recent_folders_max.valueChanged.connect(
            lambda v: self._write(_keys.RECENT_FOLDERS_MAX, v)
        )
        form.addRow("Max recent folders:", self._recent_folders_max)

        for w in (
            self._show_tags,
            self._remember_widths,
            self._remember_visibility,
            self._remember_geometry,
            self._remember_splitters,
            self._expand_tree,
            self._restore_folder,
        ):
            layout.addWidget(w)
        layout.addLayout(form)
        return box

    def _build_search_group(self) -> QGroupBox:
        box = QGroupBox("Search / Similarity")
        box.setObjectName("SettingsGroup")
        form = _group_form(box)

        self._similar_count = QSpinBox()
        self._similar_count.setRange(1, 999)
        self._similar_count.setValue(
            int(self._settings.value(_keys.SIMILAR_RESULTS_COUNT, _keys.DEFAULTS[_keys.SIMILAR_RESULTS_COUNT], type=int))
        )
        self._similar_count.valueChanged.connect(
            lambda v: self._write(_keys.SIMILAR_RESULTS_COUNT, v)
        )
        form.addRow("Similar results count:", self._similar_count)

        self._download_limit = QSpinBox()
        self._download_limit.setRange(1, 999)
        self._download_limit.setValue(
            int(self._settings.value(_keys.DOWNLOAD_SEARCH_LIMIT, _keys.DEFAULTS[_keys.DOWNLOAD_SEARCH_LIMIT], type=int))
        )
        self._download_limit.valueChanged.connect(
            lambda v: self._write(_keys.DOWNLOAD_SEARCH_LIMIT, v)
        )
        form.addRow("Download search limit:", self._download_limit)

        self._download_mode = QComboBox()
        self._download_mode.addItems(["samples", "tracks"])
        current_mode = self._settings.value(
            _keys.DEFAULT_DOWNLOAD_MODE, _keys.DEFAULTS[_keys.DEFAULT_DOWNLOAD_MODE]
        )
        idx = self._download_mode.findText(str(current_mode))
        if idx >= 0:
            self._download_mode.setCurrentIndex(idx)
        self._download_mode.currentTextChanged.connect(
            lambda v: self._write(_keys.DEFAULT_DOWNLOAD_MODE, v)
        )
        form.addRow("Default download mode:", self._download_mode)

        aspects_widget = QWidget()
        aspects_layout = QHBoxLayout(aspects_widget)
        aspects_layout.setContentsMargins(0, 0, 0, 0)
        stored_aspects = self._settings.value(
            _keys.DEFAULT_SIMILAR_ASPECTS, _keys.DEFAULTS[_keys.DEFAULT_SIMILAR_ASPECTS]
        )
        if isinstance(stored_aspects, str):
            stored_aspects = [stored_aspects]
        self._aspect_checkboxes: dict[str, QCheckBox] = {}
        for aspect in _ASPECTS:
            cb = QCheckBox(aspect)
            cb.setChecked(aspect in stored_aspects)
            cb.toggled.connect(self._on_aspects_changed)
            self._aspect_checkboxes[aspect] = cb
            aspects_layout.addWidget(cb)
        form.addRow("Default similar aspects:", aspects_widget)

        return box

    def _build_safety_group(self) -> QGroupBox:
        box = QGroupBox("Safety")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        self._confirm_delete = self._bool_checkbox(
            "Confirm delete", _keys.CONFIRM_DELETE
        )
        self._recycle_saved = self._bool_checkbox(
            "Recycle bin for saved", _keys.RECYCLE_BIN_FOR_SAVED
        )
        self._confirm_dup = self._bool_checkbox(
            "Confirm duplicate resolver deletes", _keys.CONFIRM_DUP_RESOLVER_DELETES
        )
        self._auto_refresh_health = self._bool_checkbox(
            "Auto-refresh health on open", _keys.AUTO_REFRESH_HEALTH_ON_OPEN
        )

        for w in (
            self._confirm_delete,
            self._recycle_saved,
            self._confirm_dup,
            self._auto_refresh_health,
        ):
            layout.addWidget(w)
        return box

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _bool_checkbox(self, label: str, key: str) -> QCheckBox:
        cb = QCheckBox(label)
        default = bool(_keys.DEFAULTS[key])
        val = self._settings.value(key, default, type=bool)
        cb.setChecked(bool(val))
        cb.toggled.connect(lambda checked, k=key: self._write(k, checked))
        return cb

    def _write(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self.preference_changed.emit(key, value)

    def _on_aspects_changed(self) -> None:
        selected = [a for a, cb in self._aspect_checkboxes.items() if cb.isChecked()]
        self._write(_keys.DEFAULT_SIMILAR_ASPECTS, selected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_auto_preview_enabled(self, enabled: bool) -> None:
        """Update the auto-preview checkbox without re-emitting signals."""
        self._auto_preview.blockSignals(True)
        self._auto_preview.setChecked(bool(enabled))
        self._auto_preview.blockSignals(False)
        self._settings.setValue(_keys.AUTO_PREVIEW_ON_SELECT, bool(enabled))

    @property
    def auto_preview_checkbox(self) -> QCheckBox:
        return self._auto_preview

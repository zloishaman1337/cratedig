"""Paths tab — config_writer-backed library dirs, paths, and token editors."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from cratedig import config_writer


def _group_layout(box: QGroupBox) -> QVBoxLayout:
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)
    return layout


def _group_form(box: QGroupBox) -> QFormLayout:
    form = QFormLayout(box)
    form.setContentsMargins(12, 10, 12, 10)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(7)
    return form


def _load_display_doc():
    """Return a tomlkit document for display WITHOUT creating config.toml."""
    import tomlkit

    target = config_writer.resolve_config_path()
    if target.is_file():
        return tomlkit.parse(target.read_text(encoding="utf-8"))

    example = target.parent / config_writer.EXAMPLE_CONFIG_NAME
    if example.is_file():
        return tomlkit.parse(example.read_text(encoding="utf-8"))

    return tomlkit.parse("")


class PathsTab(QWidget):
    """Paths tab. Reads toml for display; writes only on Save."""

    config_written = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        doc = _load_display_doc()
        paths = doc.get("paths", {})
        sources = doc.get("sources", {})
        metadata = doc.get("metadata", {})
        plugins = doc.get("plugins", {})

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

        layout.addWidget(self._build_library_dirs_group(paths))
        layout.addWidget(self._build_plugin_dirs_group(plugins))
        layout.addWidget(self._build_paths_group(paths))
        layout.addWidget(self._build_tokens_group(doc))

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _build_library_dirs_group(self, paths: dict) -> QGroupBox:
        box = QGroupBox("Library Directories")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        self._dirs_list = QListWidget()
        for d in paths.get("library_dirs", []):
            self._add_dir_item(str(d))
        layout.addWidget(self._dirs_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_dir)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_dir)
        up_btn = QPushButton("Up")
        up_btn.clicked.connect(self._on_move_up)
        down_btn = QPushButton("Down")
        down_btn.clicked.connect(self._on_move_down)
        open_btn = QPushButton("Open in Explorer")
        open_btn.clicked.connect(self._on_open_dir)
        for b in (add_btn, remove_btn, up_btn, down_btn, open_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return box

    def _add_dir_item(self, path: str) -> None:
        exists = Path(path).is_dir()
        badge = "✅" if exists else "❌"
        item = QListWidgetItem(f"{badge} {path}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        self._dirs_list.addItem(item)

    def _build_plugin_dirs_group(self, plugins: dict) -> QGroupBox:
        box = QGroupBox("Plugin scan folders")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        self._plugin_dirs_list = QListWidget()
        for d in plugins.get("scan_dirs", []):
            self._add_plugin_dir_item(str(d))
        layout.addWidget(self._plugin_dirs_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_plugin_dir)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_plugin_dir)
        for b in (add_btn, remove_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return box

    def _add_plugin_dir_item(self, path: str) -> None:
        exists = Path(path).is_dir()
        badge = "✅" if exists else "❌"
        item = QListWidgetItem(f"{badge} {path}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        self._plugin_dirs_list.addItem(item)

    def _on_add_plugin_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select plugin folder")
        if path:
            self._add_plugin_dir_item(path)

    def _on_remove_plugin_dir(self) -> None:
        row = self._plugin_dirs_list.currentRow()
        if row >= 0:
            self._plugin_dirs_list.takeItem(row)

    def _build_paths_group(self, paths: dict) -> QGroupBox:
        box = QGroupBox("Paths")
        box.setObjectName("SettingsGroup")
        form = _group_form(box)

        self._download_dir = QLineEdit(str(paths.get("download_dir", "")))
        dl_row = QHBoxLayout()
        dl_row.addWidget(self._download_dir)
        dl_browse = QPushButton("Browse")
        dl_browse.clicked.connect(lambda: self._browse_dir(self._download_dir))
        dl_row.addWidget(dl_browse)
        form.addRow("Download dir:", dl_row)

        self._saved_dir = QLineEdit(str(paths.get("saved_dir", "")))
        saved_row = QHBoxLayout()
        saved_row.addWidget(self._saved_dir)
        saved_browse = QPushButton("Browse")
        saved_browse.clicked.connect(lambda: self._browse_dir(self._saved_dir))
        saved_row.addWidget(saved_browse)
        form.addRow("Saved dir:", saved_row)

        self._db_path = QLineEdit(str(paths.get("db", "")))
        self._db_path.setReadOnly(True)
        form.addRow("Database (change requires restart):", self._db_path)

        return box

    def _build_tokens_group(self, doc) -> QGroupBox:
        box = QGroupBox("API Tokens")
        box.setObjectName("SettingsGroup")
        form = _group_form(box)

        config_root = config_writer.resolve_config_path().parent

        # freesound
        fs_status = config_writer.source_token_status(doc, "freesound", config_root)
        fs_placeholder = "configured" if fs_status.configured else "not set"
        self._freesound_token = QLineEdit()
        self._freesound_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._freesound_token.setPlaceholderText(fs_placeholder)
        fs_clear = QPushButton("Clear")
        fs_clear.clicked.connect(lambda: self._freesound_token.setText("\x00clear\x00"))
        fs_row = QHBoxLayout()
        fs_row.addWidget(self._freesound_token)
        fs_row.addWidget(fs_clear)
        form.addRow("freesound token:", fs_row)

        # yandex
        yx_status = config_writer.source_token_status(doc, "yandex", config_root)
        yx_placeholder = "configured" if yx_status.configured else "not set"
        self._yandex_token = QLineEdit()
        self._yandex_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._yandex_token.setPlaceholderText(yx_placeholder)
        self._yandex_token_file = QLineEdit(
            str(doc.get("sources", {}).get("yandex", {}).get("token_file", ""))
        )
        yx_clear = QPushButton("Clear")
        yx_clear.clicked.connect(lambda: self._yandex_token.setText("\x00clear\x00"))
        yx_row = QHBoxLayout()
        yx_row.addWidget(self._yandex_token)
        yx_row.addWidget(yx_clear)
        form.addRow("yandex token:", yx_row)
        form.addRow("yandex token file:", self._yandex_token_file)

        # discogs
        discogs_token_raw = str(
            doc.get("metadata", {}).get("discogs_token", "") or ""
        ).strip()
        discogs_placeholder = "configured" if discogs_token_raw else "not set"
        self._discogs_token = QLineEdit()
        self._discogs_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._discogs_token.setPlaceholderText(discogs_placeholder)
        discogs_clear = QPushButton("Clear")
        discogs_clear.clicked.connect(lambda: self._discogs_token.setText("\x00clear\x00"))
        discogs_row = QHBoxLayout()
        discogs_row.addWidget(self._discogs_token)
        discogs_row.addWidget(discogs_clear)
        form.addRow("discogs token:", discogs_row)

        return box

    # ------------------------------------------------------------------
    # Library dir actions
    # ------------------------------------------------------------------

    def _on_add_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select directory")
        if path:
            self._add_dir_item(path)

    def _on_remove_dir(self) -> None:
        row = self._dirs_list.currentRow()
        if row >= 0:
            self._dirs_list.takeItem(row)

    def _on_move_up(self) -> None:
        row = self._dirs_list.currentRow()
        if row > 0:
            item = self._dirs_list.takeItem(row)
            self._dirs_list.insertItem(row - 1, item)
            self._dirs_list.setCurrentRow(row - 1)

    def _on_move_down(self) -> None:
        row = self._dirs_list.currentRow()
        if row >= 0 and row < self._dirs_list.count() - 1:
            item = self._dirs_list.takeItem(row)
            self._dirs_list.insertItem(row + 1, item)
            self._dirs_list.setCurrentRow(row + 1)

    def _on_open_dir(self) -> None:
        row = self._dirs_list.currentRow()
        if row < 0:
            return
        path = self._dirs_list.item(row).data(Qt.ItemDataRole.UserRole)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _browse_dir(self, line_edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select directory")
        if path:
            line_edit.setText(path)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        config_writer.ensure_config_exists()
        doc = config_writer.load_document()

        dirs = [
            self._dirs_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._dirs_list.count())
        ]
        config_writer.set_library_dirs(doc, dirs)

        plugin_dirs = [
            self._plugin_dirs_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._plugin_dirs_list.count())
        ]
        config_writer.set_plugin_scan_dirs(doc, plugin_dirs)

        dl = self._download_dir.text().strip()
        if dl:
            config_writer.set_download_dir(doc, dl)

        saved = self._saved_dir.text().strip()
        if saved:
            config_writer.set_saved_dir(doc, saved)

        # Tokens: empty field = leave unchanged; sentinel = clear
        _CLEAR = "\x00clear\x00"

        fs_token = self._freesound_token.text()
        if fs_token == _CLEAR:
            config_writer.set_source_token(doc, "freesound", "")
        elif fs_token:
            config_writer.set_source_token(doc, "freesound", fs_token)

        yx_token = self._yandex_token.text()
        if yx_token == _CLEAR:
            config_writer.set_source_token(doc, "yandex", "")
        elif yx_token:
            config_writer.set_source_token(doc, "yandex", yx_token)

        yx_tf = self._yandex_token_file.text().strip()
        config_writer.set_source_token_file(doc, "yandex", yx_tf)

        discogs_token = self._discogs_token.text()
        if discogs_token == _CLEAR:
            config_writer.set_discogs_token(doc, "")
        elif discogs_token:
            config_writer.set_discogs_token(doc, discogs_token)

        config_writer.write_document(doc)
        self.config_written.emit()

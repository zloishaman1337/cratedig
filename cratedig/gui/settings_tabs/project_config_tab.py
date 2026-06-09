"""Project Config tab — config_writer-backed audio/metadata/backend settings."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cratedig import config_writer

_KNOWN_EXTENSIONS = [".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".m4a"]


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
    """Return a tomlkit document for display WITHOUT creating config.toml.

    If config.toml exists, parse it. Otherwise parse config.example.toml.
    Never calls ensure_config_exists or write_document.
    """
    import tomlkit

    target = config_writer.resolve_config_path()
    if target.is_file():
        return tomlkit.parse(target.read_text(encoding="utf-8"))

    # Fall back to example for display values
    example = target.parent / config_writer.EXAMPLE_CONFIG_NAME
    if example.is_file():
        return tomlkit.parse(example.read_text(encoding="utf-8"))

    return tomlkit.parse("")


class ProjectConfigTab(QWidget):
    """Project config tab. Reads toml for display; writes only on Save."""

    config_written = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        doc = _load_display_doc()
        audio = doc.get("audio", {})
        metadata = doc.get("metadata", {})
        sources = doc.get("sources", {})

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

        layout.addWidget(self._build_audio_group(audio))
        layout.addWidget(self._build_metadata_group(metadata))
        layout.addWidget(self._build_backend_status_group(doc))

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _build_audio_group(self, audio: dict) -> QGroupBox:
        box = QGroupBox("Audio Extensions")
        box.setObjectName("SettingsGroup")
        layout = _group_layout(box)

        current_exts = list(audio.get("extensions", _KNOWN_EXTENSIONS))
        row = QHBoxLayout()
        self._ext_checks: dict[str, QCheckBox] = {}
        for ext in _KNOWN_EXTENSIONS:
            cb = QCheckBox(ext)
            cb.setChecked(ext in current_exts)
            self._ext_checks[ext] = cb
            row.addWidget(cb)
        layout.addLayout(row)

        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("Add extension:"))
        self._ext_extra = QLineEdit()
        self._ext_extra.setPlaceholderText(".xyz")
        extra_row.addWidget(self._ext_extra)
        layout.addLayout(extra_row)
        return box

    def _build_metadata_group(self, metadata: dict) -> QGroupBox:
        box = QGroupBox("Metadata")
        box.setObjectName("SettingsGroup")
        form = _group_form(box)

        self._cache_ttl = QSpinBox()
        self._cache_ttl.setRange(0, 3650)
        self._cache_ttl.setValue(int(metadata.get("cache_ttl_days", 30)))
        form.addRow("Cache TTL (days):", self._cache_ttl)

        self._enable_ranking = QCheckBox("Enable search ranking")
        self._enable_ranking.setChecked(bool(metadata.get("enable_search_ranking", True)))
        form.addRow("", self._enable_ranking)

        self._live_lookup = QCheckBox("Search live lookup")
        self._live_lookup.setChecked(bool(metadata.get("search_live_lookup", True)))
        form.addRow("", self._live_lookup)

        self._max_live_hits = QSpinBox()
        self._max_live_hits.setRange(0, 50)
        self._max_live_hits.setValue(int(metadata.get("search_max_live_lookup_hits", 3)))
        form.addRow("Max live lookup hits:", self._max_live_hits)

        return box

    def _build_backend_status_group(self, doc) -> QGroupBox:
        box = QGroupBox("Backend Status")
        box.setObjectName("SettingsGroup")
        layout = _group_form(box)

        config_root = config_writer.resolve_config_path().parent

        for name in ("freesound", "yandex"):
            status = config_writer.source_token_status(doc, name, config_root)
            badge = "✅" if status.configured else "❌"
            layout.addRow(f"{name}:", QLabel(f"{badge} (edit token on Paths tab)"))

        # discogs lives under [metadata].discogs_token
        discogs_token = str(doc.get("metadata", {}).get("discogs_token", "") or "").strip()
        discogs_badge = "✅" if discogs_token else "❌"
        layout.addRow("discogs:", QLabel(f"{discogs_badge} (edit token on Paths tab)"))

        return box

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        config_writer.ensure_config_exists()
        doc = config_writer.load_document()

        extensions = [ext for ext, cb in self._ext_checks.items() if cb.isChecked()]
        extra = self._ext_extra.text().strip()
        if extra:
            extensions.append(extra)
        config_writer.set_audio_extensions(doc, extensions)

        config_writer.set_metadata_cache_ttl_days(doc, self._cache_ttl.value())
        config_writer.set_metadata_enable_search_ranking(doc, self._enable_ranking.isChecked())
        config_writer.set_metadata_search_live_lookup(doc, self._live_lookup.isChecked())
        config_writer.set_metadata_search_max_live_lookup_hits(doc, self._max_live_hits.value())

        config_writer.write_document(doc)
        self.config_written.emit()

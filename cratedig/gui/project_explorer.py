"""Generic project explorer panel for binary DAW formats (Bitwig, Nuendo).

Parameterized by a parser callable + labels. Displays the recovered version,
plugin/device list (with installed ✓/✗ badges for format-known 3rd-party plugins,
reusing the Feature-1 matcher) and referenced sample files. Deliberately lighter
than the Ableton panel — these formats yield best-effort data, not full trees.
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..plugins.scanner import match_installed
from .theme import ACCENT_2, ERROR, MUTED, WARN, icon

_C_OK = ACCENT_2
_C_ERR = ERROR
_C_MUTED = MUTED
_C_VST = WARN
_THIRD_PARTY_SUFFIXES = ("[VST2]", "[VST3]", "[AU]", "[AAX]")


def _label(text: str, color: str = "", bold: bool = False, size: int = 11) -> QLabel:
    lbl = QLabel(text)
    weight = "font-weight: 700;" if bold else ""
    col = f"color: {color};" if color else ""
    lbl.setStyleSheet(f"{col}{weight}font-size: {size}px; background: transparent;")
    return lbl


def project_badge(name: str, index) -> tuple[str, str] | None:
    """Return (glyph, color) for a 3rd-party plugin's install status, or None.

    Only format-suffixed entries ([VST2]/[VST3]/…) are disk-checkable; native
    devices and suffix-less names get no badge (status unknown for these formats).
    """
    if not any(name.endswith(s) for s in _THIRD_PARTY_SUFFIXES):
        return None
    if index is None:
        return None
    clean = name.rsplit(" [", 1)[0].strip()
    return ("✓", _C_OK) if match_installed(clean, index) else ("✗", _C_ERR)


class ProjectExplorerPanel(QWidget):
    """Open + inspect one binary project file; reused for Bitwig and Nuendo."""

    pluginScanRequested = Signal(bool)

    def __init__(
        self,
        parser: Callable[[str], dict],
        title: str,
        file_filter: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._parser = parser
        self._title = title
        self._file_filter = file_filter
        self._data: dict | None = None
        self._plugin_index = None
        self._build_ui()

    # --- public API ---

    def set_plugin_index(self, index) -> None:
        self._plugin_index = index
        if self._data is not None:
            self._render(self._data)

    # --- UI ---

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 12, 8)
        hl.setSpacing(8)
        hl.addWidget(_label(self._title, bold=True, size=16))
        hl.addStretch()

        self._btn_open = QPushButton("Open project…")
        self._btn_open.setIcon(icon("samples"))
        self._btn_open.setProperty("primary", True)
        self._btn_open.setMinimumWidth(150)
        self._btn_open.clicked.connect(self._open_file)
        hl.addWidget(self._btn_open)

        self._btn_rescan = QPushButton("Rescan plugins")
        self._btn_rescan.setIcon(icon("refresh"))
        self._btn_rescan.clicked.connect(lambda: self.pluginScanRequested.emit(True))
        hl.addWidget(self._btn_rescan)
        layout.addWidget(header)

        file_bar = QWidget()
        fl = QHBoxLayout(file_bar)
        fl.setContentsMargins(16, 0, 16, 6)
        self._lbl_file = _label("No project loaded", _C_MUTED)
        self._lbl_version = _label("", _C_MUTED)
        fl.addWidget(self._lbl_file)
        fl.addStretch()
        fl.addWidget(self._lbl_version)
        layout.addWidget(file_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._placeholder_widget())
        layout.addWidget(self._scroll, stretch=1)

    def _placeholder_widget(self) -> QWidget:
        w = QWidget()
        wl = QVBoxLayout(w)
        lbl = _label("Open a project file to inspect its plugins and samples.", _C_MUTED, size=13)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addStretch()
        wl.addWidget(lbl)
        wl.addStretch()
        return w

    # --- load + render ---

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", self._file_filter)
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        try:
            data = self._parser(path)
        except Exception as exc:  # noqa: BLE001 — surface parse errors to the user
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._data = data
        self._lbl_file.setText(os.path.basename(path))
        self._lbl_version.setText(data.get("version", ""))
        self._render(data)
        self.pluginScanRequested.emit(False)

    def _render(self, data: dict) -> None:
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        il = QVBoxLayout(inner)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(2)

        plugins = data.get("plugins", [])
        samples = data.get("samples", [])

        il.addWidget(_label(f"Plugins / devices ({len(plugins)})", _C_VST, bold=True, size=13))
        if plugins:
            for i, name in enumerate(plugins):
                il.addWidget(self._plugin_row(name, i))
        else:
            il.addWidget(_label("  none detected", _C_MUTED))

        il.addSpacing(10)
        il.addWidget(_label(f"Referenced samples ({len(samples)})", ACCENT_2, bold=True, size=13))
        if samples:
            for name in samples:
                il.addWidget(_label(f"  {name}", _C_MUTED))
        else:
            il.addWidget(_label("  none detected", _C_MUTED))

        il.addStretch()
        self._scroll.setWidget(inner)

    def _plugin_row(self, name: str, i: int) -> QWidget:
        row = QFrame()
        bg = "rgba(103,213,255,0.06)" if i % 2 == 0 else "rgba(139,219,129,0.08)"
        row.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 4px; }}")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 3, 10, 3)
        is_third_party = any(name.endswith(s) for s in _THIRD_PARTY_SUFFIXES)
        name_lbl = _label(name, _C_VST if is_third_party else "", bold=True)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        rl.addWidget(name_lbl)
        badge = project_badge(name, self._plugin_index)
        if badge is not None:
            glyph, col = badge
            b = _label(glyph, col, bold=True, size=12)
            b.setFixedWidth(30)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(b)
        return row

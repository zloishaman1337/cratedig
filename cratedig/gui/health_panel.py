"""Library Health dashboard — Grafana-style stat tiles with severity highlighting.

A hidden QTableWidget mirrors `format_report` output so the data contract (and
unit tests) stay intact, while the visible UI is a grid of colour-coded tiles.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import ACCENT, ACCENT_2, ERROR, MUTED, PANEL_2, TEXT, WARN, icon

# Severity → accent colour for tiles and the overall status banner.
_OK = ACCENT_2
_WARN = WARN
_PROBLEM = ERROR
_INFO = ACCENT


class _StatTile(QFrame):
    """A single dashboard tile: big value, label, severity-coloured accent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumSize(150, 88)

        self._value = QLabel("—")
        self._value.setStyleSheet("font-size:30px;font-weight:800;background:transparent;")
        self._label = QLabel("")
        self._label.setStyleSheet(f"color:{MUTED};font-size:11px;font-weight:700;background:transparent;")
        self._label.setWordWrap(True)
        self._sub = QLabel("")
        self._sub.setStyleSheet(f"color:{MUTED};font-size:10px;background:transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        lay.addWidget(self._value)
        lay.addWidget(self._label)
        lay.addWidget(self._sub)
        lay.addStretch()

    def set_data(self, label: str, value: str, color: str, sub: str = "") -> None:
        self._value.setText(value)
        self._value.setStyleSheet(
            f"font-size:30px;font-weight:800;color:{color};background:transparent;"
        )
        self._label.setText(label.upper())
        self._sub.setText(sub)
        self._sub.setVisible(bool(sub))
        self.setStyleSheet(
            f"#Card{{border-left:4px solid {color};}}"
        )


class HealthPanel(QWidget):
    refresh_requested = Signal()
    remove_missing_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")

        self._report = None

        # --- Header: title + status banner + refresh ---
        title = QLabel("Library Health")
        title.setObjectName("SidebarTitle")
        self._status = QLabel("No data")
        self._status.setStyleSheet(
            f"color:{MUTED};font-size:13px;font-weight:800;padding:5px 12px;"
            f"border:1px solid {MUTED};border-radius:13px;background:transparent;"
        )
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setIcon(icon("refresh"))
        self._refresh_btn.setProperty("primary", True)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title)
        header.addSpacing(14)
        header.addWidget(self._status)
        header.addStretch()
        header.addWidget(self._refresh_btn)

        # --- Tile grid ---
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._tiles: list[_StatTile] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._grid_host)

        # --- Sources breakdown ---
        self._sources_label = QLabel("Sources")
        self._sources_label.setObjectName("SectionTitle")
        self._sources_row = QLabel("—")
        self._sources_row.setStyleSheet(f"color:{TEXT};font-size:12px;background:transparent;")
        self._sources_row.setWordWrap(True)

        # --- Hidden mirror table (data contract for tests/details) ---
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setVisible(False)

        # --- Footer ---
        self._remove_missing_btn = QPushButton("Remove missing files from DB")
        self._remove_missing_btn.setIcon(icon("delete"))
        self._remove_missing_btn.setProperty("danger", True)
        self._remove_missing_btn.setEnabled(False)
        self._remove_missing_btn.clicked.connect(self.remove_missing_requested.emit)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self._remove_missing_btn)
        footer.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(self._sources_label)
        layout.addWidget(self._sources_row)
        layout.addWidget(self._table)
        layout.addLayout(footer)

    # --- data ---------------------------------------------------------------
    def set_report(self, report) -> None:
        from ..health import format_report

        # Mirror table (kept for tests / raw details).
        rows = format_report(report)
        self._table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(label))
            self._table.setItem(i, 1, QTableWidgetItem(value))

        self._rebuild_tiles(report)
        self._rebuild_sources(report)
        self._rebuild_status(report)

        self._remove_missing_btn.setEnabled(getattr(report, "missing_files", 0) > 0)
        self._report = report

    # --- tiles --------------------------------------------------------------
    def _tile_specs(self, r) -> list[tuple[str, str, str, str]]:
        """Return (label, value, color, sub) per metric with severity colour."""
        def flag(n: int, problem: bool = False) -> str:
            if n <= 0:
                return _OK
            return _PROBLEM if problem else _WARN

        return [
            ("Total samples", str(r.total), _INFO, ""),
            ("Unanalyzed", str(r.unanalyzed), flag(r.unanalyzed), "no feature vector"),
            ("Unknown category", str(r.unknown_category), flag(r.unknown_category), ""),
            ("Unknown class", str(r.unknown_class), flag(r.unknown_class), ""),
            ("Missing files", str(r.missing_files), flag(r.missing_files, problem=True), "not on disk"),
            ("Duplicate groups", str(r.duplicate_groups), flag(r.duplicate_groups),
             f"{r.duplicate_files} files"),
            ("Stale metadata", str(r.stale_metadata), flag(r.stale_metadata), ""),
        ]

    def _rebuild_tiles(self, report) -> None:
        for tile in self._tiles:
            tile.setParent(None)
            tile.deleteLater()
        self._tiles = []

        specs = self._tile_specs(report)
        cols = 3
        for idx, (label, value, color, sub) in enumerate(specs):
            tile = _StatTile(self._grid_host)
            tile.set_data(label, value, color, sub)
            self._grid.addWidget(tile, idx // cols, idx % cols)
            self._tiles.append(tile)

    def _rebuild_sources(self, report) -> None:
        items = sorted(getattr(report, "by_source", {}).items())
        if not items:
            self._sources_row.setText("—")
            return
        chips = "   ".join(f"{src}: {cnt}" for src, cnt in items)
        self._sources_row.setText(chips)

    def _rebuild_status(self, report) -> None:
        problems = report.missing_files
        warnings = (
            report.unanalyzed + report.unknown_category + report.unknown_class
            + report.duplicate_groups + report.stale_metadata
        )
        if problems > 0:
            text, color = "Problems found", _PROBLEM
        elif warnings > 0:
            text, color = "Needs attention", _WARN
        else:
            text, color = "Healthy", _OK
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{color};font-size:13px;font-weight:800;padding:5px 12px;"
            f"border:1px solid {color};border-radius:13px;background:{PANEL_2};"
        )

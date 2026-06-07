"""Library Health dashboard page — read-only stats with refresh + clean-missing actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class HealthPanel(QWidget):
    refresh_requested = Signal()
    remove_missing_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._report = None

        # Header row
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Library Health"))
        header_layout.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self._refresh_btn)

        # Table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)

        # Footer row
        footer_row = QWidget()
        footer_layout = QHBoxLayout(footer_row)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self._remove_missing_btn = QPushButton("Remove missing files from DB")
        self._remove_missing_btn.setEnabled(False)
        self._remove_missing_btn.clicked.connect(self.remove_missing_requested.emit)
        footer_layout.addWidget(self._remove_missing_btn)
        footer_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(header_row)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(footer_row)

    def set_report(self, report) -> None:
        from ..health import format_report

        rows = format_report(report)
        self._table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(label))
            self._table.setItem(i, 1, QTableWidgetItem(value))
        self._remove_missing_btn.setEnabled(getattr(report, "missing_files", 0) > 0)
        self._report = report

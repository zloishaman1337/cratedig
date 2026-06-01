"""Center-panel sample list widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QHeaderView

from ..db.models import Sample

_COLUMNS = ("Filename", "BPM", "Key", "Category", "Duration")


def _fmt_duration(sec: float | None) -> str:
    if sec is None:
        return ""
    total = int(sec)
    return f"{total // 60}:{total % 60:02d}"


def _fmt_key(musical_key: str | None, key_scale: str | None) -> str:
    parts = [p for p in (musical_key, key_scale) if p]
    return " ".join(parts)


class SampleTable(QWidget):
    """Displays a list of Sample rows; emits selection events."""

    sample_selected = Signal(object)  # carries the selected Sample

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[Sample] = []
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

        self._table.currentCellChanged.connect(self._on_cell_changed)

    def set_samples(self, samples: list[Sample]) -> None:
        self._samples = list(samples)
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._samples))

        for row, s in enumerate(self._samples):
            bpm = f"{s.bpm:.1f}" if s.bpm is not None else ""
            values = (
                s.filename,
                bpm,
                _fmt_key(s.musical_key, s.key_scale),
                s.category or "",
                _fmt_duration(s.duration_sec),
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, col, item)

        self._table.blockSignals(False)

    def _on_cell_changed(self, current_row: int, _cc: int, _pr: int, _pc: int) -> None:
        if 0 <= current_row < len(self._samples):
            self.sample_selected.emit(self._samples[current_row])

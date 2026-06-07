"""Center-panel sample list widget."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QVBoxLayout,
    QHeaderView,
    QStyleOptionViewItem,
)

from ..db.models import Sample
from .logic import file_urls, filename_parts, similar_name

_COLUMNS = ("Filename", "Class", "Category", "BPM", "Key", "SR", "Tags", "Duration", "Similarity")

_SIM_COL = _COLUMNS.index("Similarity")
_FNAME_COL = _COLUMNS.index("Filename")


def _fmt_duration(sec: float | None) -> str:
    if sec is None:
        return ""
    total = int(sec)
    return f"{total // 60}:{total % 60:02d}"


def _fmt_key(musical_key: str | None, key_scale: str | None) -> str:
    parts = [p for p in (musical_key, key_scale) if p]
    return " ".join(parts)


def _fmt_sr(samplerate: int | None) -> str:
    if samplerate is None:
        return ""
    return str(samplerate)


class SimilarityBarDelegate(QStyledItemDelegate):
    """Paints a horizontal progress bar for similarity scores stored in UserRole."""

    _BAR_COLOR = QColor(80, 160, 80)
    _TRACK_COLOR = QColor(50, 50, 50)

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        v = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(v, float) or not (0 < v <= 1):
            super().paint(painter, option, index)
            return

        painter.save()
        rect = option.rect

        painter.fillRect(rect, self._TRACK_COLOR)

        bar_rect = rect.adjusted(1, 2, -1, -2)
        bar_rect.setWidth(int(bar_rect.width() * v))
        painter.fillRect(bar_rect, self._BAR_COLOR)

        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(round(v * 100))}%")
        painter.restore()


class _SampleTableWidget(QTableWidget):
    def __init__(self, selected_samples, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_samples = selected_samples

    def mimeData(self, _items) -> QMimeData:
        mime = QMimeData()
        urls = [QUrl.fromLocalFile(path) for path in file_urls(self._selected_samples())]
        mime.setUrls(urls)
        return mime


class SampleTable(QWidget):
    """Displays a list of Sample rows; emits selection events."""

    sample_selected = Signal(object)  # carries the selected Sample
    similar_requested = Signal(object)
    rename_requested = Signal(object)
    move_requested = Signal(object)
    delete_requested = Signal(object)
    reveal_requested = Signal(object)
    add_to_crate_requested = Signal(object, int)
    create_crate_requested = Signal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[Sample] = []
        self._tags_by_id: dict[int, list[str]] = {}
        self._crates: list = []
        self._table = _SampleTableWidget(self._selected_samples_for_drag)
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setDragEnabled(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(_FNAME_COL, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        self._table.setItemDelegateForColumn(_SIM_COL, SimilarityBarDelegate(self._table))

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

        self._table.currentCellChanged.connect(self._on_cell_changed)

    def set_crates(self, crates) -> None:
        self._crates = list(crates)

    def set_samples(
        self,
        samples,
        tags_by_id=None,
        scores: dict[int, float] | None = None,
        show_path: bool = False,
    ) -> None:
        self._samples = list(samples)
        self._tags_by_id = tags_by_id if tags_by_id is not None else {}
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._samples))

        for row, s in enumerate(self._samples):
            bpm = f"{s.bpm:.1f}" if s.bpm is not None else ""
            tags_str = ", ".join(self._tags_by_id.get(s.id, []))
            display_name = filename_parts(s.filename)[0]
            fname = similar_name(s.path) if show_path else display_name
            values = (
                fname,
                s.instrument_class or "",
                s.category or "",
                bpm,
                _fmt_key(s.musical_key, s.key_scale),
                _fmt_sr(s.samplerate),
                tags_str,
                _fmt_duration(s.duration_sec),
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == _FNAME_COL:
                    item.setToolTip(s.path)
                self._table.setItem(row, col, item)

            sim_item = QTableWidgetItem("")
            sim_item.setFlags(sim_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if scores is not None and s.id in scores:
                # Cosine can be negative for dissimilar vectors; clamp to the
                # bar's [0,1] display range so poor matches render as a tiny bar
                # rather than a blank cell.
                sim_item.setData(
                    Qt.ItemDataRole.UserRole, max(0.0, min(1.0, float(scores[s.id])))
                )
            self._table.setItem(row, _SIM_COL, sim_item)

        self._table.blockSignals(False)
        self._table.setColumnWidth(_SIM_COL, 110)

    def _on_cell_changed(self, current_row: int, _cc: int, _pr: int, _pc: int) -> None:
        if 0 <= current_row < len(self._samples):
            self.sample_selected.emit(self._samples[current_row])

    def _selected_samples_for_drag(self) -> list[Sample]:
        rows = sorted({idx.row() for idx in self._table.selectionModel().selectedRows()})
        return [self._samples[row] for row in rows if 0 <= row < len(self._samples)]

    def _on_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._samples):
            return
        sample = self._samples[row]

        menu = QMenu(self)
        menu.addAction("Find similar").triggered.connect(lambda: self.similar_requested.emit(sample))
        crate_menu = menu.addMenu("Add to crate")
        if self._crates:
            for crate in self._crates:
                crate_menu.addAction(crate.name).triggered.connect(
                    lambda _checked=False, c=crate: self.add_to_crate_requested.emit(sample, c.id)
                )
            crate_menu.addSeparator()
        crate_menu.addAction("New crate…").triggered.connect(
            lambda: self.create_crate_requested.emit(sample, "")
        )
        menu.addSeparator()
        menu.addAction("Rename…").triggered.connect(lambda: self.rename_requested.emit(sample))
        menu.addAction("Move…").triggered.connect(lambda: self.move_requested.emit(sample))
        menu.addAction("Delete").triggered.connect(lambda: self.delete_requested.emit(sample))
        menu.addAction("Reveal in Explorer").triggered.connect(lambda: self.reveal_requested.emit(sample))
        menu.exec(self._table.viewport().mapToGlobal(pos))

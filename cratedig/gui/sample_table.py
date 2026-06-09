"""Center-panel sample list widget."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QSettings, Qt, QUrl, Signal
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
from .settings_tabs import _keys

_COLUMNS = ("Filename", "Class", "Category", "BPM", "Key", "SR", "Tags", "Duration", "Similarity")

_SIM_COL = _COLUMNS.index("Similarity")
_FNAME_COL = _COLUMNS.index("Filename")
_TAGS_COL = _COLUMNS.index("Tags")

_COLUMN_WIDTHS = {
    "Class": 74,
    "Category": 76,
    "BPM": 64,
    "Key": 92,
    "SR": 64,
    "Tags": 90,
    "Duration": 72,
    "Similarity": 92,
}


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

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
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
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(44)
        for col, name in enumerate(_COLUMNS):
            if col == _FNAME_COL:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
                self._table.setColumnWidth(col, 240)
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(col, _COLUMN_WIDTHS.get(name, 80))
        self._table.verticalHeader().setVisible(False)

        self._table.setItemDelegateForColumn(_SIM_COL, SimilarityBarDelegate(self._table))

        # Tags column: default visible (True) unless pref says otherwise
        show_tags = self._read_bool(_keys.SHOW_TAGS_COLUMN, _keys.DEFAULTS[_keys.SHOW_TAGS_COLUMN])
        self._table.setColumnHidden(_TAGS_COL, not show_tags)
        self._table.setColumnHidden(_SIM_COL, True)

        # Restore saved column state if prefs say so
        self._restore_column_state()

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

        self._table.currentCellChanged.connect(self._on_cell_changed)

        # Connect persistence signals
        header.sectionResized.connect(self._on_section_resized)
        header.sectionMoved.connect(self._on_section_moved)

    # --- settings helpers ---------------------------------------------------

    def _read_bool(self, key: str, default: object) -> bool:
        if self._settings is None:
            return bool(default)
        return self._settings.value(key, default, type=bool)

    def _restore_column_state(self) -> None:
        if self._settings is None:
            return
        header = self._table.horizontalHeader()
        if self._read_bool(_keys.REMEMBER_COLUMN_WIDTHS, _keys.DEFAULTS[_keys.REMEMBER_COLUMN_WIDTHS]):
            saved = self._settings.value("browser/column_widths")
            if isinstance(saved, QByteArray) and not saved.isEmpty():
                header.restoreState(saved)

    def save_column_state(self) -> None:
        """Persist header state to QSettings (called from MainWindow.closeEvent)."""
        if self._settings is None:
            return
        if self._read_bool(_keys.REMEMBER_COLUMN_WIDTHS, _keys.DEFAULTS[_keys.REMEMBER_COLUMN_WIDTHS]):
            self._settings.setValue("browser/column_widths", self._table.horizontalHeader().saveState())

    def set_tags_visible(self, visible: bool) -> None:
        """Show or hide the Tags column live."""
        self._table.setColumnHidden(_TAGS_COL, not visible)

    def _on_section_resized(self, _logical: int, _old: int, _new: int) -> None:
        if self._settings is None:
            return
        if self._read_bool(_keys.REMEMBER_COLUMN_WIDTHS, _keys.DEFAULTS[_keys.REMEMBER_COLUMN_WIDTHS]):
            self._settings.setValue("browser/column_widths", self._table.horizontalHeader().saveState())

    def _on_section_moved(self, _logical: int, _old: int, _new: int) -> None:
        if self._settings is None:
            return
        if self._read_bool(_keys.REMEMBER_COLUMN_WIDTHS, _keys.DEFAULTS[_keys.REMEMBER_COLUMN_WIDTHS]):
            self._settings.setValue("browser/column_widths", self._table.horizontalHeader().saveState())

    # --- public API ---------------------------------------------------------

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
        self._table.setColumnHidden(_SIM_COL, scores is None)
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
        self._table.setColumnWidth(_SIM_COL, _COLUMN_WIDTHS["Similarity"])

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

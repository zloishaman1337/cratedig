"""Download panel: search source backends, audition previews, fetch + auto-index."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .logic import hit_rows

_COLUMNS = ("Title", "Artist", "Year", "Album", "Duration", "Backend")
_MODES = ("samples", "tracks", "youtube", "yandex", "freesound", "archive")


class DownloadPane(QWidget):
    """Search + download UI. Emits requests; all blocking work runs in the worker."""

    search_requested = Signal(str, str)   # (query, mode)
    download_requested = Signal(object)   # carries the chosen SearchHit
    preview_requested = Signal(object)    # carries the SearchHit to audition

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hits: list = []

        self._query = QLineEdit()
        self._query.setPlaceholderText("Search query…")
        self._mode = QComboBox()
        self._mode.addItems(_MODES)
        search_btn = QPushButton("Search")

        top = QHBoxLayout()
        top.addWidget(self._query, stretch=1)
        top.addWidget(self._mode)
        top.addWidget(search_btn)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        self._download_btn = QPushButton("Download")
        self._preview_btn = QPushButton("Preview")
        self._download_btn.setEnabled(False)
        self._preview_btn.setEnabled(False)
        self._status = QLabel("")

        bottom = QHBoxLayout()
        bottom.addWidget(self._download_btn)
        bottom.addWidget(self._preview_btn)
        bottom.addWidget(self._status, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._table, stretch=1)
        layout.addLayout(bottom)

        search_btn.clicked.connect(self._emit_search)
        self._query.returnPressed.connect(self._emit_search)
        self._download_btn.clicked.connect(self._emit_download)
        self._preview_btn.clicked.connect(self._emit_preview)
        self._table.itemDoubleClicked.connect(lambda _i: self._emit_download())
        self._table.currentCellChanged.connect(self._on_row_changed)

    # --- inbound API (called from MainWindow) ---------------------------------

    def set_results(self, hits: list, used: str) -> None:
        self._hits = list(hits)
        rows = hit_rows(self._hits)
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(r, c, item)
        self._table.blockSignals(False)
        has = bool(rows)
        self._download_btn.setEnabled(has)
        self._preview_btn.setEnabled(has)
        if has:
            self._table.selectRow(0)
            self.set_status(f"{len(rows)} hits via {used}")
        else:
            self.set_status(f"no hits ({used})")

    def set_status(self, msg: str) -> None:
        self._status.setText(msg)

    # --- internal -------------------------------------------------------------

    def _selected_hit(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._hits):
            return self._hits[row]
        return None

    def _on_row_changed(self, current_row: int, *_args) -> None:
        enabled = 0 <= current_row < len(self._hits)
        self._download_btn.setEnabled(enabled)
        self._preview_btn.setEnabled(enabled)

    def _emit_search(self) -> None:
        query = self._query.text().strip()
        if query:
            self.set_status("searching…")
            self.search_requested.emit(query, self._mode.currentText())

    def _emit_download(self) -> None:
        hit = self._selected_hit()
        if hit is not None:
            self.set_status("downloading…")
            self.download_requested.emit(hit)

    def _emit_preview(self) -> None:
        hit = self._selected_hit()
        if hit is not None:
            self.preview_requested.emit(hit)

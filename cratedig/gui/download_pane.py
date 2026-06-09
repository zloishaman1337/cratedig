"""Download panel: search source backends, audition previews, fetch + auto-index."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .logic import backend_badge, hit_rows, should_preview_hit
from .settings_tabs import _keys

_COLUMNS = ("Title", "Artist", "Year", "Album", "Duration", "Backend")
_MODES = ("samples", "tracks", "youtube", "yandex", "freesound", "archive")


class DownloadPane(QWidget):
    """Search + download UI. Emits requests; all blocking work runs in the worker."""

    search_requested = Signal(str, str)         # (query, mode)
    download_requested = Signal(object)         # carries the chosen SearchHit
    preview_requested = Signal(object)          # carries the SearchHit to audition
    refresh_metadata_requested = Signal()       # no-arg; triggers metadata re-query

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hits: list = []

        self._query = QLineEdit()
        self._query.setPlaceholderText("Search query…")
        self._mode = QComboBox()
        self._mode.addItems(_MODES)
        search_btn = QPushButton("Search")

        # Apply saved default download mode
        if self._settings is not None:
            default_mode = self._settings.value(
                _keys.DEFAULT_DOWNLOAD_MODE,
                _keys.DEFAULTS[_keys.DEFAULT_DOWNLOAD_MODE],
                type=str,
            )
            idx = self._mode.findText(default_mode)
            if idx >= 0:
                self._mode.setCurrentIndex(idx)

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
        self._refresh_meta_btn = QPushButton("Refresh Meta")
        self._download_btn.setEnabled(False)
        self._preview_btn.setEnabled(False)
        self._bar = QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._backend_label = QLabel()
        self._notification_label = QLabel()
        self._notification_label.setVisible(False)

        bottom = QHBoxLayout()
        bottom.addWidget(self._download_btn)
        bottom.addWidget(self._preview_btn)
        bottom.addWidget(self._refresh_meta_btn)
        bottom.addWidget(self._backend_label)
        bottom.addWidget(self._bar, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._table, stretch=1)
        layout.addLayout(bottom)
        layout.addWidget(self._notification_label)

        search_btn.clicked.connect(self._emit_search)
        self._query.returnPressed.connect(self._emit_search)
        self._download_btn.clicked.connect(self._emit_download)
        self._preview_btn.clicked.connect(self._emit_preview)
        self._refresh_meta_btn.clicked.connect(self.refresh_metadata_requested)
        self._table.itemDoubleClicked.connect(lambda _i: self._emit_download())
        self._table.currentCellChanged.connect(self._on_row_changed)
        self._mode.currentTextChanged.connect(self._on_mode_changed)

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

    # The bar carries a "state" property (idle/busy/ok/fail) for tests/external QSS;
    # the per-state setStyleSheet below is what actually paints it. Applying any
    # stylesheet also forces Qt's QSS render path, so the centered format text stays
    # visible even in the indeterminate busy state (the native marquee would hide it).
    def set_status(self, msg: str) -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setProperty("state", "idle")
        self._bar.setFormat(msg)
        self._bar.setStyleSheet(
            "QProgressBar{border:1px solid #555;border-radius:3px;text-align:center;"
            "background:#2b2b2b;color:#ddd;} QProgressBar::chunk{background:#444;}"
        )

    def start_download(self) -> None:
        self._bar.setRange(0, 0)
        self._bar.setProperty("state", "busy")
        self._bar.setFormat("Downloading…")
        self._bar.setStyleSheet(
            "QProgressBar{border:1px solid #555;border-radius:3px;text-align:center;"
            "background:#2b2b2b;color:#fff;font-weight:bold;} QProgressBar::chunk{background:#1565c0;}"
        )

    def finish_download(self, ok: bool, msg: str) -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        if ok:
            self._bar.setProperty("state", "ok")
            self._bar.setFormat(f"✓ {msg}")
            self._bar.setStyleSheet(
                "QProgressBar{border:1px solid #555;border-radius:3px;text-align:center;"
                "background:#2b2b2b;color:#ffffff;font-weight:bold;} QProgressBar::chunk{background:#2e7d32;}"
            )
            self.show_notification(f"Download complete: {msg}")
        else:
            self._bar.setProperty("state", "fail")
            self._bar.setFormat(f"✗ {msg}")
            self._bar.setStyleSheet(
                "QProgressBar{border:1px solid #555;border-radius:3px;text-align:center;"
                "background:#2b2b2b;color:#ffffff;font-weight:bold;} QProgressBar::chunk{background:#c62828;}"
            )
            self.show_notification(f"Download failed: {msg}")

    def set_progress(self, pct) -> None:
        """Update the progress bar: float 0..100 → determinate; None → indeterminate."""
        if pct is None:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(int(pct))

    def show_notification(self, text: str) -> None:
        """Show a transient status message in the notification label."""
        self._notification_label.setText(text)
        self._notification_label.setVisible(bool(text))

    def set_backend(self, source: str) -> None:
        """Update the backend badge label and color for the given source."""
        label, color = backend_badge(source)
        self._backend_label.setText(label)
        self._backend_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    # --- internal -------------------------------------------------------------

    def _on_mode_changed(self, mode: str) -> None:
        if self._settings is not None:
            self._settings.setValue(_keys.DEFAULT_DOWNLOAD_MODE, mode)

    def _selected_hit(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._hits):
            return self._hits[row]
        return None

    def _on_row_changed(self, current_row: int, *_args) -> None:
        enabled = 0 <= current_row < len(self._hits)
        self._download_btn.setEnabled(enabled)
        self._preview_btn.setEnabled(enabled)
        if enabled and self._settings is not None and self._settings.value(
            _keys.PREVIEW_DOWNLOAD_ON_ROW_SELECT,
            _keys.DEFAULTS[_keys.PREVIEW_DOWNLOAD_ON_ROW_SELECT],
            type=bool,
        ):
            hit = self._hits[current_row]
            if should_preview_hit(hit):
                self.preview_requested.emit(hit)

    def _emit_search(self) -> None:
        query = self._query.text().strip()
        if query:
            self.set_status("searching…")
            self.search_requested.emit(query, self._mode.currentText())

    def _emit_download(self) -> None:
        hit = self._selected_hit()
        if hit is not None:
            self.start_download()
            self.download_requested.emit(hit)

    def _emit_preview(self) -> None:
        hit = self._selected_hit()
        if hit is not None:
            self.preview_requested.emit(hit)

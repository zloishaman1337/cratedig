"""Inline tag editor panel shown under the waveform."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import icon


class TagEditor(QWidget):
    """Edits the tags of the currently selected sample.

    Add/Remove only mutate the local list; the change is written to the DB
    when the user presses Save (emits tags_committed).
    """

    tags_committed = Signal(int, object)  # (sample_id, list[str])

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._sample_id: int | None = None

        self._title = QLabel("No sample selected")
        self._title.setObjectName("SectionTitle")
        self._list = QListWidget()

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("New tag…")
        self._completer = QCompleter([])
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._edit.setCompleter(self._completer)

        self._list.setMaximumHeight(90)

        self._add_btn = QPushButton("Add")
        self._remove_btn = QPushButton("Remove")
        self._save_btn = QPushButton("Save tags")
        self._add_btn.setIcon(icon("favorite"))
        self._remove_btn.setIcon(icon("delete"))
        self._save_btn.setIcon(icon("export"))
        self._save_btn.setProperty("primary", True)

        self._add_btn.clicked.connect(self._add_tag)
        self._edit.returnPressed.connect(self._add_tag)
        self._remove_btn.clicked.connect(self._remove_selected)
        self._save_btn.clicked.connect(self._save)

        input_row = QHBoxLayout()
        input_row.addWidget(self._edit, stretch=1)
        input_row.addWidget(self._add_btn)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._title)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(input_row)
        layout.addLayout(btn_row)

        self._list.installEventFilter(self)
        self._set_enabled(False)

    def set_sample(self, sample, current_tags: list[str], suggestions: list[str]) -> None:
        """Load a sample's tags into the editor; disable if sample is unsaved."""
        if sample is None or sample.id is None:
            self._sample_id = None
            self._title.setText("No sample selected")
            self._list.clear()
            self._set_enabled(False)
            return

        self._sample_id = sample.id
        self._title.setText(f"Tags — {sample.filename}")
        self._list.clear()
        for tag in sorted(set(current_tags)):
            self._list.addItem(tag)
        self._completer.setModel(None)
        self._completer = QCompleter(sorted(set(suggestions)))
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._edit.setCompleter(self._completer)
        self._set_enabled(True)

    def _set_enabled(self, enabled: bool) -> None:
        for w in (self._list, self._edit, self._add_btn, self._remove_btn, self._save_btn):
            w.setEnabled(enabled)

    def _add_tag(self) -> None:
        name = self._edit.text().strip()
        if not name:
            return
        existing = [self._list.item(i).text() for i in range(self._list.count())]
        if name not in existing:
            self._list.addItem(name)
        self._edit.clear()

    def _remove_selected(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def _save(self) -> None:
        if self._sample_id is None:
            return
        tags = sorted({self._list.item(i).text() for i in range(self._list.count())})
        self.tags_committed.emit(self._sample_id, tags)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._list and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete:
                self._remove_selected()
                return True
        return super().eventFilter(obj, event)

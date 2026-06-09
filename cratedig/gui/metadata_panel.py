"""Compact read-only metadata display panel."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from .logic import format_metadata


class MetadataPanel(QWidget):
    """Shows combined scan/analyze + embedded tag metadata for the selected sample."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(160)
        self.setObjectName("Card")

        self._title = QLabel("Metadata")
        self._title.setObjectName("SectionTitle")
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumHeight(130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.addWidget(self._title)
        layout.addWidget(self._text)

    def set_metadata(self, sample, embedded: dict | None) -> None:
        if sample is None:
            self._text.setPlainText("No sample selected")
            return
        rows = format_metadata(sample, embedded)
        lines: list[str] = []
        for label, value in rows:
            if label == "" and value == "":
                lines.append("")
            else:
                lines.append(f"{label}: {value}")
        self._text.setPlainText("\n".join(lines))

    def clear(self) -> None:
        self._text.setPlainText("No sample selected")

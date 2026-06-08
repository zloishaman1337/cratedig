"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Small in-app settings window."""

    auto_preview_changed = Signal(bool)

    def __init__(self, auto_preview_enabled: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(False)

        self._auto_preview = QCheckBox("Auto-preview selected samples")
        self._auto_preview.setChecked(bool(auto_preview_enabled))
        self._auto_preview.toggled.connect(self.auto_preview_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._auto_preview)
        layout.addWidget(buttons)

    def set_auto_preview_enabled(self, enabled: bool) -> None:
        self._auto_preview.setChecked(bool(enabled))


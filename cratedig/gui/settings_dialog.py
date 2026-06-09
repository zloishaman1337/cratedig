"""Application settings dialog — 3-tab QTabWidget shell."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QDialog,
    QTabWidget,
    QVBoxLayout,
)

from .settings_tabs._keys import AUTO_PREVIEW_ON_SELECT
from .settings_tabs.preferences_tab import PreferencesTab
from .settings_tabs.project_config_tab import ProjectConfigTab
from .settings_tabs.paths_tab import PathsTab
from .theme import icon


class SettingsDialog(QDialog):
    """Non-modal settings dialog with three tabs."""

    preferences_changed = Signal(str, object)
    config_written = Signal()
    auto_preview_changed = Signal(bool)

    def __init__(
        self,
        auto_preview_enabled: bool = True,
        parent=None,
        *,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("Settings")
        self.setWindowIcon(icon("settings"))
        self.setModal(False)

        if settings is not None:
            _settings = settings
        else:
            from PySide6.QtWidgets import QApplication
            org = QApplication.organizationName() or "cratedig"
            app_name = QApplication.applicationName() or "cratedig"
            _settings = QSettings(QSettings.IniFormat, QSettings.UserScope, org, app_name)

        self._prefs_tab = PreferencesTab(_settings)
        self._config_tab = ProjectConfigTab()
        self._paths_tab = PathsTab()

        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        tabs.addTab(self._prefs_tab, "Preferences")
        tabs.addTab(self._config_tab, "Project Config")
        tabs.addTab(self._paths_tab, "Paths")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

        # Wire tab signals up to dialog signals
        self._prefs_tab.preference_changed.connect(self._on_preference_changed)
        self._config_tab.config_written.connect(self.config_written)
        self._paths_tab.config_written.connect(self.config_written)

        # Apply initial auto_preview_enabled override
        self._prefs_tab.set_auto_preview_enabled(bool(auto_preview_enabled))

    def _on_preference_changed(self, key: str, value: object) -> None:
        self.preferences_changed.emit(key, value)
        if key == AUTO_PREVIEW_ON_SELECT:
            self.auto_preview_changed.emit(bool(value))

    def set_auto_preview_enabled(self, enabled: bool) -> None:
        """Update the auto-preview checkbox (called by MainWindow)."""
        self._prefs_tab.set_auto_preview_enabled(bool(enabled))

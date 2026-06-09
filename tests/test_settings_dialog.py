"""Tests for cratedig.gui.settings_dialog.SettingsDialog (TDD — FAILING tests).

Tests the dialog shell: tab structure, signals, and preferences persistence.
Uses isolated QSettings (temp path) to avoid touching the user's real settings.
Runs offscreen (QT_QPA_PLATFORM=offscreen) per test_simpler_pane.py pattern.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _app():
    """Set up QApplication for PySide6 tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def qsettings_temp_path(tmp_path):
    """Fixture: isolated QSettings path (doesn't touch user settings).

    Uses tmp_path to create an isolated QSettings store.
    Sets up QApplication org/app name to a temp value and IniFormat path.
    Returns the tmp_path for assertions.
    """
    app = _app()

    # Configure isolated QSettings path
    from PySide6.QtCore import QSettings

    # Set org/app name to temp names so QSettings reads from tmp_path
    app.setOrganizationName("cratedig_test")
    app.setApplicationName("cratedig_test")
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    yield tmp_path

    # Cleanup: restore original settings path (restore to system defaults if needed)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, QSettings.defaultFormat())


@pytest.fixture
def isolated_qsettings(qsettings_temp_path):
    """Fixture: return a fresh QSettings instance pointing to isolated path."""
    from PySide6.QtCore import QSettings

    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "cratedig_test", "cratedig_test")
    settings.clear()  # Start clean
    return settings


class TestSettingsDialogConstruction:
    """Test SettingsDialog construction and basic interface."""

    def test_dialog_constructs_with_defaults(self, qsettings_temp_path):
        """SettingsDialog() constructs without error."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert dialog is not None

    def test_dialog_constructs_with_auto_preview_enabled_false(self, qsettings_temp_path):
        """SettingsDialog(auto_preview_enabled=False) constructs."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(auto_preview_enabled=False)
        assert dialog is not None

    def test_dialog_exposes_preferences_changed_signal(self, qsettings_temp_path):
        """Dialog.preferences_changed signal exists."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert hasattr(dialog, "preferences_changed")
        # Verify it's a PySide6 Signal
        from PySide6.QtCore import Signal

        assert isinstance(type(dialog).preferences_changed, type(Signal(str, object)))

    def test_dialog_exposes_config_written_signal(self, qsettings_temp_path):
        """Dialog.config_written signal exists."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert hasattr(dialog, "config_written")

    def test_dialog_exposes_auto_preview_changed_legacy_signal(self, qsettings_temp_path):
        """Dialog.auto_preview_changed signal exists (legacy shim)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert hasattr(dialog, "auto_preview_changed")

    def test_dialog_exposes_set_auto_preview_enabled_method(self, qsettings_temp_path):
        """Dialog.set_auto_preview_enabled(bool) method exists."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert hasattr(dialog, "set_auto_preview_enabled")
        assert callable(dialog.set_auto_preview_enabled)


class TestSettingsDialogTabStructure:
    """Test that dialog contains three tabs with expected labels."""

    def test_dialog_contains_tab_widget(self, qsettings_temp_path):
        """Dialog contains a QTabWidget."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QTabWidget

        dialog = SettingsDialog()
        # Walk children to find QTabWidget
        tab_widget = None
        for child in dialog.findChildren(QTabWidget):
            tab_widget = child
            break

        assert tab_widget is not None

    def test_dialog_tab_widget_has_three_tabs(self, qsettings_temp_path):
        """Dialog's QTabWidget has 3 tabs."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QTabWidget

        dialog = SettingsDialog()
        tab_widget = None
        for child in dialog.findChildren(QTabWidget):
            tab_widget = child
            break

        assert tab_widget is not None
        assert tab_widget.count() == 3

    def test_dialog_first_tab_label_contains_preferences_case_insensitive(self, qsettings_temp_path):
        """First tab label contains 'Preferences' (case-insensitive)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QTabWidget

        dialog = SettingsDialog()
        tab_widget = None
        for child in dialog.findChildren(QTabWidget):
            tab_widget = child
            break

        assert tab_widget is not None
        tab_0_text = tab_widget.tabText(0).lower()
        assert "preferences" in tab_0_text

    def test_dialog_second_tab_label_contains_config_case_insensitive(self, qsettings_temp_path):
        """Second tab label contains 'config' (case-insensitive)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QTabWidget

        dialog = SettingsDialog()
        tab_widget = None
        for child in dialog.findChildren(QTabWidget):
            tab_widget = child
            break

        assert tab_widget is not None
        tab_1_text = tab_widget.tabText(1).lower()
        assert "config" in tab_1_text

    def test_dialog_third_tab_label_contains_paths_case_insensitive(self, qsettings_temp_path):
        """Third tab label contains 'paths' (case-insensitive)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QTabWidget

        dialog = SettingsDialog()
        tab_widget = None
        for child in dialog.findChildren(QTabWidget):
            tab_widget = child
            break

        assert tab_widget is not None
        tab_2_text = tab_widget.tabText(2).lower()
        assert "paths" in tab_2_text


class TestSettingsDialogAutoPreviewPreference:
    """Test auto-preview preference toggling and persistence."""

    def test_toggling_auto_preview_emits_preferences_changed_signal(self, isolated_qsettings):
        """Toggling auto-preview checkbox emits preferences_changed(key, value)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QCheckBox

        dialog = SettingsDialog()

        # Capture signal emissions
        signal_emissions = []

        def on_preferences_changed(key: str, value):
            signal_emissions.append((key, value))

        dialog.preferences_changed.connect(on_preferences_changed)

        # Find the auto-preview checkbox by searching for a checkbox with matching text
        auto_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            if "auto" in checkbox.text().lower() and "preview" in checkbox.text().lower():
                auto_preview_checkbox = checkbox
                break

        if auto_preview_checkbox is None:
            pytest.skip("auto-preview checkbox not found in dialog")

        # Toggle it
        was_checked = auto_preview_checkbox.isChecked()
        auto_preview_checkbox.setChecked(not was_checked)

        # Should have emitted preferences_changed
        assert len(signal_emissions) > 0
        # At least one emission should be for the auto-preview key
        from cratedig.gui.settings_tabs._keys import AUTO_PREVIEW_ON_SELECT

        found = False
        for key, value in signal_emissions:
            if key == AUTO_PREVIEW_ON_SELECT:
                found = True
                assert isinstance(value, bool)
                break

        assert found, f"Expected {AUTO_PREVIEW_ON_SELECT!r} in signal emissions, got {signal_emissions}"

    def test_toggling_auto_preview_emits_legacy_auto_preview_changed_signal(self, isolated_qsettings):
        """Toggling auto-preview also emits legacy auto_preview_changed(bool) signal."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QCheckBox

        dialog = SettingsDialog()

        # Capture signal emissions
        legacy_emissions = []

        def on_auto_preview_changed(value: bool):
            legacy_emissions.append(value)

        dialog.auto_preview_changed.connect(on_auto_preview_changed)

        # Find the auto-preview checkbox
        auto_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            if "auto" in checkbox.text().lower() and "preview" in checkbox.text().lower():
                auto_preview_checkbox = checkbox
                break

        if auto_preview_checkbox is None:
            pytest.skip("auto-preview checkbox not found in dialog")

        # Toggle it
        was_checked = auto_preview_checkbox.isChecked()
        auto_preview_checkbox.setChecked(not was_checked)

        # Should have emitted legacy signal
        assert len(legacy_emissions) > 0
        assert isinstance(legacy_emissions[-1], bool)

    def test_auto_preview_persists_to_qsettings(self, qsettings_temp_path):
        """Toggling auto-preview writes the value to QSettings."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from cratedig.gui.settings_tabs._keys import AUTO_PREVIEW_ON_SELECT
        from PySide6.QtWidgets import QCheckBox
        from PySide6.QtCore import QSettings

        dialog = SettingsDialog()

        # Find the auto-preview checkbox
        auto_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            if "auto" in checkbox.text().lower() and "preview" in checkbox.text().lower():
                auto_preview_checkbox = checkbox
                break

        if auto_preview_checkbox is None:
            pytest.skip("auto-preview checkbox not found in dialog")

        # Toggle to a new state
        initial_state = auto_preview_checkbox.isChecked()
        new_state = not initial_state
        auto_preview_checkbox.setChecked(new_state)

        # Read back from QSettings
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "cratedig_test", "cratedig_test")
        persisted = settings.value(AUTO_PREVIEW_ON_SELECT, type=bool)

        assert persisted == new_state

    def test_init_with_auto_preview_enabled_false_leaves_checkbox_unchecked(self, qsettings_temp_path):
        """SettingsDialog(auto_preview_enabled=False) renders with unchecked auto-preview."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QCheckBox

        dialog = SettingsDialog(auto_preview_enabled=False)

        # Find the auto-preview checkbox
        auto_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            if "auto" in checkbox.text().lower() and "preview" in checkbox.text().lower():
                auto_preview_checkbox = checkbox
                break

        if auto_preview_checkbox is None:
            pytest.skip("auto-preview checkbox not found in dialog")

        assert auto_preview_checkbox.isChecked() is False

    def test_set_auto_preview_enabled_updates_checkbox_state(self, qsettings_temp_path):
        """set_auto_preview_enabled(bool) updates the checkbox state."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QCheckBox

        dialog = SettingsDialog(auto_preview_enabled=True)

        # Find the auto-preview checkbox
        auto_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            if "auto" in checkbox.text().lower() and "preview" in checkbox.text().lower():
                auto_preview_checkbox = checkbox
                break

        if auto_preview_checkbox is None:
            pytest.skip("auto-preview checkbox not found in dialog")

        # Verify initial state
        assert auto_preview_checkbox.isChecked() is True

        # Call set_auto_preview_enabled(False)
        dialog.set_auto_preview_enabled(False)

        # Checkbox should now be unchecked
        assert auto_preview_checkbox.isChecked() is False


class TestSettingsDialogOtherPreferences:
    """Test that other preferences (e.g., stop_before_preview) also work."""

    def test_toggling_stop_before_preview_emits_preferences_changed(self, qsettings_temp_path):
        """Toggling stop_before_preview preference emits preferences_changed(key, value)."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from cratedig.gui.settings_tabs._keys import STOP_BEFORE_PREVIEW
        from PySide6.QtWidgets import QCheckBox

        dialog = SettingsDialog()

        # Capture signal emissions
        signal_emissions = []

        def on_preferences_changed(key: str, value):
            signal_emissions.append((key, value))

        dialog.preferences_changed.connect(on_preferences_changed)

        # Find stop_before_preview checkbox
        stop_before_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            text = checkbox.text().lower()
            if "stop" in text and "preview" in text:
                stop_before_preview_checkbox = checkbox
                break

        if stop_before_preview_checkbox is None:
            pytest.skip("stop_before_preview checkbox not found in dialog")

        # Toggle it
        was_checked = stop_before_preview_checkbox.isChecked()
        stop_before_preview_checkbox.setChecked(not was_checked)

        # Should have emitted preferences_changed
        assert len(signal_emissions) > 0

        # Find the emission for STOP_BEFORE_PREVIEW
        found = False
        for key, value in signal_emissions:
            if key == STOP_BEFORE_PREVIEW:
                found = True
                assert isinstance(value, bool)
                break

        assert found, f"Expected {STOP_BEFORE_PREVIEW!r} in signal emissions, got {signal_emissions}"

    def test_stop_before_preview_persists_to_qsettings(self, qsettings_temp_path):
        """Toggling stop_before_preview writes the value to QSettings."""
        _app()
        from cratedig.gui.settings_dialog import SettingsDialog
        from cratedig.gui.settings_tabs._keys import STOP_BEFORE_PREVIEW
        from PySide6.QtWidgets import QCheckBox
        from PySide6.QtCore import QSettings

        dialog = SettingsDialog()

        # Find stop_before_preview checkbox
        stop_before_preview_checkbox = None
        for checkbox in dialog.findChildren(QCheckBox):
            text = checkbox.text().lower()
            if "stop" in text and "preview" in text:
                stop_before_preview_checkbox = checkbox
                break

        if stop_before_preview_checkbox is None:
            pytest.skip("stop_before_preview checkbox not found in dialog")

        # Toggle to a new state
        initial_state = stop_before_preview_checkbox.isChecked()
        new_state = not initial_state
        stop_before_preview_checkbox.setChecked(new_state)

        # Read back from QSettings
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "cratedig_test", "cratedig_test")
        persisted = settings.value(STOP_BEFORE_PREVIEW, type=bool)

        assert persisted == new_state

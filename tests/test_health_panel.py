"""Unit tests for cratedig.gui.health_panel.HealthPanel (TDD — these are FAILING tests)."""

from __future__ import annotations

import os

import pytest

from cratedig.health import HealthReport, format_report


def _app():
    """Set up QApplication for PySide6 tests — matches test_gui_logic pattern."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class TestHealthPanelBasic:
    """Tests for HealthPanel widget construction and basic display."""

    def _app(self):
        return _app()

    def test_health_panel_constructs_with_no_args(self):
        """HealthPanel() constructs with no required arguments."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        # Should not raise
        panel = HealthPanel()
        assert panel is not None

    def test_health_panel_has_set_report_method(self):
        """HealthPanel has set_report(report) method."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Build a simple report
        report = HealthReport(
            total=10,
            unanalyzed=2,
            unknown_category=1,
            unknown_class=3,
            missing_files=2,
            duplicate_groups=1,
            duplicate_files=3,
            stale_metadata=0,
            by_source={"local": 7, "edit": 3},
        )

        # Should not raise
        panel.set_report(report)

    def test_health_panel_contains_table_widget(self):
        """After set_report, panel has a QTableWidget with correct row count."""
        self._app()
        from PySide6.QtWidgets import QTableWidget

        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        report = HealthReport(
            total=10,
            unanalyzed=2,
            unknown_category=1,
            unknown_class=3,
            missing_files=2,
            duplicate_groups=1,
            duplicate_files=3,
            stale_metadata=0,
            by_source={"local": 7, "edit": 3},
        )

        panel.set_report(report)

        # Find the QTableWidget
        table = panel.findChild(QTableWidget)
        assert table is not None

        # Row count should match format_report output
        formatted = format_report(report)
        assert table.rowCount() == len(formatted)

    def test_health_panel_table_first_column_matches_labels(self):
        """Table first column texts match format_report labels."""
        self._app()
        from PySide6.QtWidgets import QTableWidget

        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        report = HealthReport(
            total=10,
            unanalyzed=2,
            unknown_category=1,
            unknown_class=3,
            missing_files=2,
            duplicate_groups=1,
            duplicate_files=3,
            stale_metadata=0,
            by_source={"local": 7, "edit": 3},
        )

        panel.set_report(report)

        table = panel.findChild(QTableWidget)
        formatted = format_report(report)

        for row_idx, (label, _) in enumerate(formatted):
            item = table.item(row_idx, 0)
            assert item is not None
            assert item.text() == label

    def test_health_panel_table_second_column_matches_values(self):
        """Table second column texts match format_report values."""
        self._app()
        from PySide6.QtWidgets import QTableWidget

        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        report = HealthReport(
            total=10,
            unanalyzed=2,
            unknown_category=1,
            unknown_class=3,
            missing_files=2,
            duplicate_groups=1,
            duplicate_files=3,
            stale_metadata=0,
            by_source={"local": 7, "edit": 3},
        )

        panel.set_report(report)

        table = panel.findChild(QTableWidget)
        formatted = format_report(report)

        for row_idx, (_, value) in enumerate(formatted):
            item = table.item(row_idx, 1)
            assert item is not None
            assert item.text() == value


class TestHealthPanelSignals:
    """Tests for HealthPanel signals (refresh_requested, remove_missing_requested)."""

    def _app(self):
        return _app()

    def test_health_panel_has_refresh_requested_signal(self):
        """HealthPanel has refresh_requested Signal."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Should have the signal
        assert hasattr(panel, "refresh_requested")
        assert callable(getattr(panel.refresh_requested, "emit", None))
        assert callable(getattr(panel.refresh_requested, "connect", None))

    def test_health_panel_has_remove_missing_requested_signal(self):
        """HealthPanel has remove_missing_requested Signal."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Should have the signal
        assert hasattr(panel, "remove_missing_requested")
        assert callable(getattr(panel.remove_missing_requested, "emit", None))
        assert callable(getattr(panel.remove_missing_requested, "connect", None))

    def test_refresh_requested_signal_emits(self):
        """refresh_requested signal can be connected and emitted."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        collected = []
        panel.refresh_requested.connect(lambda: collected.append(True))

        # Emit manually
        panel.refresh_requested.emit()

        # Should have been collected
        assert len(collected) == 1

    def test_remove_missing_requested_signal_emits(self):
        """remove_missing_requested signal can be connected and emitted."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        collected = []
        panel.remove_missing_requested.connect(lambda: collected.append(True))

        # Emit manually
        panel.remove_missing_requested.emit()

        # Should have been collected
        assert len(collected) == 1


class TestHealthPanelRemoveButton:
    """Tests for HealthPanel remove-missing button state and behavior."""

    def _app(self):
        return _app()

    def test_remove_missing_button_enabled_when_missing_files_gt_zero(self):
        """Remove missing button is ENABLED when report.missing_files > 0."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Report with missing files
        report = HealthReport(
            total=10,
            unanalyzed=0,
            unknown_category=0,
            unknown_class=0,
            missing_files=2,
            duplicate_groups=0,
            duplicate_files=0,
            stale_metadata=0,
            by_source={"local": 10},
        )

        panel.set_report(report)

        # Assume button attribute is panel._remove_missing_btn (or find by text)
        # First try the attribute assumption from spec
        if hasattr(panel, "_remove_missing_btn"):
            button = panel._remove_missing_btn
        else:
            # Search by text containing "missing" (case-insensitive)
            from PySide6.QtWidgets import QPushButton

            buttons = panel.findChildren(QPushButton)
            button = None
            for btn in buttons:
                if "missing" in btn.text().lower():
                    button = btn
                    break

        assert button is not None, "Could not find remove-missing button"
        assert button.isEnabled(), "Button should be enabled when missing_files > 0"

    def test_remove_missing_button_disabled_when_missing_files_zero(self):
        """Remove missing button is DISABLED when report.missing_files == 0."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Report without missing files
        report = HealthReport(
            total=10,
            unanalyzed=0,
            unknown_category=0,
            unknown_class=0,
            missing_files=0,
            duplicate_groups=0,
            duplicate_files=0,
            stale_metadata=0,
            by_source={"local": 10},
        )

        panel.set_report(report)

        # Find button
        if hasattr(panel, "_remove_missing_btn"):
            button = panel._remove_missing_btn
        else:
            from PySide6.QtWidgets import QPushButton

            buttons = panel.findChildren(QPushButton)
            button = None
            for btn in buttons:
                if "missing" in btn.text().lower():
                    button = btn
                    break

        assert button is not None, "Could not find remove-missing button"
        assert not button.isEnabled(), "Button should be disabled when missing_files == 0"

    def test_clicking_remove_missing_button_emits_signal(self):
        """Clicking remove missing button emits remove_missing_requested."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        report = HealthReport(
            total=10,
            unanalyzed=0,
            unknown_category=0,
            unknown_class=0,
            missing_files=2,
            duplicate_groups=0,
            duplicate_files=0,
            stale_metadata=0,
            by_source={"local": 10},
        )

        panel.set_report(report)

        # Find and collect signal
        collected = []
        panel.remove_missing_requested.connect(lambda: collected.append(True))

        # Find button
        if hasattr(panel, "_remove_missing_btn"):
            button = panel._remove_missing_btn
        else:
            from PySide6.QtWidgets import QPushButton

            buttons = panel.findChildren(QPushButton)
            button = None
            for btn in buttons:
                if "missing" in btn.text().lower():
                    button = btn
                    break

        assert button is not None
        assert button.isEnabled()

        # Click the button
        button.click()

        # Signal should be emitted
        assert len(collected) == 1


class TestHealthPanelRefreshButton:
    """Tests for HealthPanel refresh button behavior."""

    def _app(self):
        return _app()

    def test_refresh_button_exists(self):
        """HealthPanel has a refresh button."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Assume button attribute is panel._refresh_btn
        assert hasattr(panel, "_refresh_btn"), "Panel should have _refresh_btn attribute"

    def test_clicking_refresh_button_emits_signal(self):
        """Clicking refresh button emits refresh_requested."""
        self._app()
        from cratedig.gui.health_panel import HealthPanel

        panel = HealthPanel()

        # Collect signal
        collected = []
        panel.refresh_requested.connect(lambda: collected.append(True))

        # Click refresh button
        panel._refresh_btn.click()

        # Signal should be emitted
        assert len(collected) == 1

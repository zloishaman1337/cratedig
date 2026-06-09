"""Tests for cratedig.gui.download_pane and logic.backend_badge - TDD."""

import os
import pytest


class TestBackendBadge:
    """Test pure backend_badge(source: str) -> (label, color_hex) function."""

    def test_backend_badge_returns_tuple_of_two_strings(self):
        """backend_badge must return (label, color_hex)."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("youtube")
        assert isinstance(label, str)
        assert isinstance(color, str)

    def test_backend_badge_youtube_returns_nonempty_label_and_color(self):
        """'youtube' should return a distinct non-empty label and valid hex color."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("youtube")
        assert label, "Label must not be empty"
        assert color.startswith("#"), "Color must be a hex string starting with #"
        assert len(color) == 7, f"Hex color must be 6 digits + '#', got {color}"

    def test_backend_badge_yandex_returns_nonempty_label_and_color(self):
        """'yandex' should return a distinct non-empty label and valid hex color."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("yandex")
        assert label, "Label must not be empty"
        assert color.startswith("#"), "Color must be a hex string starting with #"
        assert len(color) == 7, f"Hex color must be 6 digits + '#', got {color}"

    def test_backend_badge_freesound_returns_nonempty_label_and_color(self):
        """'freesound' should return a distinct non-empty label and valid hex color."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("freesound")
        assert label, "Label must not be empty"
        assert color.startswith("#"), "Color must be a hex string starting with #"
        assert len(color) == 7, f"Hex color must be 6 digits + '#', got {color}"

    def test_backend_badge_known_sources_return_distinct_labels(self):
        """Each known source should return a distinct label."""
        from cratedig.gui.logic import backend_badge

        labels = {}
        for source in ("youtube", "yandex", "freesound"):
            label, _ = backend_badge(source)
            labels[source] = label

        # All labels should be unique (no two sources share the same label)
        unique_labels = set(labels.values())
        assert len(unique_labels) == len(labels), f"Expected distinct labels, got {labels}"

    def test_backend_badge_case_insensitive_youtube(self):
        """'YouTube' should work the same as 'youtube'."""
        from cratedig.gui.logic import backend_badge

        label_lower, color_lower = backend_badge("youtube")
        label_upper, color_upper = backend_badge("YouTube")

        assert label_lower == label_upper, "Case-insensitive: 'youtube' and 'YouTube' should have same label"
        assert color_lower == color_upper, "Case-insensitive: 'youtube' and 'YouTube' should have same color"

    def test_backend_badge_case_insensitive_freesound(self):
        """'FreeSound' should work the same as 'freesound'."""
        from cratedig.gui.logic import backend_badge

        label_lower, color_lower = backend_badge("freesound")
        label_mixed, color_mixed = backend_badge("FreeSound")

        assert label_lower == label_mixed, "Case-insensitive: 'freesound' and 'FreeSound' should have same label"
        assert color_lower == color_mixed, "Case-insensitive: 'freesound' and 'FreeSound' should have same color"

    def test_backend_badge_unknown_source_returns_fallback(self):
        """Unknown/empty source should return a generic fallback label and valid hex color."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("unknown_backend_xyz")
        assert label, "Fallback label must not be empty"
        assert color.startswith("#"), "Fallback color must be a hex string starting with #"
        assert len(color) == 7, f"Hex color must be 6 digits + '#', got {color}"

    def test_backend_badge_empty_source_returns_fallback(self):
        """Empty string source should return a generic fallback label and valid hex color."""
        from cratedig.gui.logic import backend_badge

        label, color = backend_badge("")
        assert label, "Fallback label for empty source must not be empty"
        assert color.startswith("#"), "Fallback color must be a hex string starting with #"
        assert len(color) == 7, f"Hex color must be 6 digits + '#', got {color}"


class TestDownloadPaneSetProgress:
    """Test DownloadPane.set_progress(pct) for determinate/indeterminate progress bar."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_set_progress_with_percentage_makes_determinate(self):
        """set_progress(42.0) should make bar determinate with value 42."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_progress(42.0)

        assert pane._bar.maximum() != 0, "Determinate bar must have maximum > 0"
        assert pane._bar.value() == 42, f"Bar value should be 42, got {pane._bar.value()}"

    def test_set_progress_zero_percent_valid(self):
        """set_progress(0.0) should set value to 0 while making bar determinate."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_progress(0.0)

        assert pane._bar.maximum() != 0, "Determinate bar must have maximum > 0"
        assert pane._bar.value() == 0

    def test_set_progress_hundred_percent_valid(self):
        """set_progress(100.0) should set value to 100."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_progress(100.0)

        assert pane._bar.maximum() != 0, "Determinate bar must have maximum > 0"
        assert pane._bar.value() == 100

    def test_set_progress_none_makes_indeterminate(self):
        """set_progress(None) should make bar indeterminate (minimum == maximum == 0)."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_progress(None)

        assert pane._bar.minimum() == 0, f"Indeterminate bar minimum should be 0, got {pane._bar.minimum()}"
        assert pane._bar.maximum() == 0, f"Indeterminate bar maximum should be 0, got {pane._bar.maximum()}"

    def test_set_progress_does_not_raise(self):
        """set_progress with any valid input must not raise an exception."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        # These should not raise
        pane.set_progress(0.0)
        pane.set_progress(50.5)
        pane.set_progress(100.0)
        pane.set_progress(None)


class TestDownloadPaneRefreshMetadataButton:
    """Test DownloadPane Refresh Metadata button and signal."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_download_pane_has_refresh_meta_button_attribute(self):
        """DownloadPane must have a _refresh_meta_btn attribute."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert hasattr(pane, "_refresh_meta_btn"), "DownloadPane must have _refresh_meta_btn attribute"

    def test_refresh_meta_button_is_qpushbutton(self):
        """_refresh_meta_btn must be a QPushButton."""
        self._app()
        from PySide6.QtWidgets import QPushButton
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert isinstance(pane._refresh_meta_btn, QPushButton), "_refresh_meta_btn must be a QPushButton"

    def test_download_pane_has_refresh_metadata_signal(self):
        """DownloadPane must have a refresh_metadata_requested signal."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert hasattr(pane, "refresh_metadata_requested"), "DownloadPane must have refresh_metadata_requested signal"

    def test_refresh_button_click_emits_signal(self):
        """Clicking _refresh_meta_btn should emit refresh_metadata_requested signal."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        emitted = []
        pane.refresh_metadata_requested.connect(lambda *args: emitted.append(args))

        pane._refresh_meta_btn.click()

        assert len(emitted) == 1, f"Expected signal to emit once, got {len(emitted)} times"


class TestDownloadPaneNotification:
    """Test DownloadPane corner notification method."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_download_pane_has_show_notification_method(self):
        """DownloadPane must have a show_notification method."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert hasattr(pane, "show_notification"), "DownloadPane must have show_notification method"
        assert callable(pane.show_notification), "show_notification must be callable"

    def test_show_notification_accepts_string_does_not_raise(self):
        """show_notification(text: str) must not raise when called with a string."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        # Should not raise
        pane.show_notification("Download complete!")
        pane.show_notification("")
        pane.show_notification("Multi-word message with special chars: 123!@#")


class TestDownloadPaneBackendBadgeIntegration:
    """Test DownloadPane per-backend badge display via set_backend method."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_download_pane_has_set_backend_method(self):
        """DownloadPane must have a set_backend method."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert hasattr(pane, "set_backend"), "DownloadPane must have set_backend method"
        assert callable(pane.set_backend), "set_backend must be callable"

    def test_download_pane_has_backend_label_attribute(self):
        """DownloadPane must have a _backend_label attribute for the backend badge."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        assert hasattr(pane, "_backend_label"), "DownloadPane must have _backend_label attribute"

    def test_set_backend_youtube_does_not_raise(self):
        """set_backend('youtube') should not raise."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        # Should not raise
        pane.set_backend("youtube")

    def test_set_backend_sets_nonempty_label_text(self):
        """After set_backend('youtube'), _backend_label should have non-empty text."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_backend("youtube")

        label_text = pane._backend_label.text()
        assert label_text, f"Expected non-empty label text after set_backend, got '{label_text}'"

    def test_set_backend_freesound_sets_nonempty_label_text(self):
        """After set_backend('freesound'), _backend_label should have non-empty text."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_backend("freesound")

        label_text = pane._backend_label.text()
        assert label_text, f"Expected non-empty label text after set_backend, got '{label_text}'"

    def test_set_backend_different_sources_produce_different_labels(self):
        """set_backend('youtube') vs set_backend('freesound') should produce different badge labels."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane1 = DownloadPane()
        pane1.set_backend("youtube")
        label1 = pane1._backend_label.text()

        pane2 = DownloadPane()
        pane2.set_backend("freesound")
        label2 = pane2._backend_label.text()

        assert label1 != label2, f"Expected different labels for different backends, got '{label1}' and '{label2}'"

"""Badge decision logic for installed-plugin detection in the project explorer."""

from __future__ import annotations

import os

import pytest


def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _index(stems):
    from cratedig.plugins.scanner import InstalledIndex

    return InstalledIndex(stems=frozenset(stems), by_format={}, signature=())


class TestPluginBadge:
    def test_native_device_always_ok(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_OK

        glyph, color = AlsExplorerPanel._plugin_badge("EQ Eight", None)
        assert glyph == "✓" and color == C_OK

    def test_m4l_is_neutral(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_M4L

        glyph, color = AlsExplorerPanel._plugin_badge("Granulator II [M4L]", None)
        assert glyph == "M4L" and color == C_M4L

    def test_third_party_pending_when_no_index(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel

        assert AlsExplorerPanel._plugin_badge("Serum [VST3]", None) is None

    def test_third_party_installed(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_OK

        glyph, color = AlsExplorerPanel._plugin_badge("Serum [VST3]", _index({"serum"}))
        assert glyph == "✓" and color == C_OK

    def test_third_party_missing(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_ERR

        glyph, color = AlsExplorerPanel._plugin_badge("Sylenth1 [VST2]", _index({"serum"}))
        assert glyph == "✗" and color == C_ERR

    def test_set_plugin_index_stores_and_rerenders(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel

        panel = AlsExplorerPanel()
        idx = _index({"serum"})
        panel.set_plugin_index(idx)  # no data loaded → just stores, no crash
        assert panel._plugin_index is idx

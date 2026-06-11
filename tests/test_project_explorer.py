"""Tests for the generic Bitwig/Nuendo project explorer panel."""

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


class TestProjectBadge:
    def test_no_badge_for_native(self):
        _app()
        from cratedig.gui.project_explorer import project_badge

        assert project_badge("EQ-2", _index({"eq-2"})) is None

    def test_no_badge_when_index_missing(self):
        _app()
        from cratedig.gui.project_explorer import project_badge

        assert project_badge("Serum2 [VST3]", None) is None

    def test_installed(self):
        _app()
        from cratedig.gui.project_explorer import project_badge, _C_OK

        glyph, color = project_badge("Serum2 [VST3]", _index({"serum2"}))
        assert glyph == "✓" and color == _C_OK

    def test_missing(self):
        _app()
        from cratedig.gui.project_explorer import project_badge, _C_ERR

        glyph, color = project_badge("FabFilter Pro-MB [VST2]", _index({"serum2"}))
        assert glyph == "✗" and color == _C_ERR


class TestPanel:
    def test_loads_and_renders_dict(self):
        _app()
        from cratedig.gui.project_explorer import ProjectExplorerPanel

        fake = {
            "format": "bitwig",
            "version": "Bitwig 5.2.7",
            "plugins": ["EQ-2", "Serum2 [VST3]"],
            "samples": ["kick.wav"],
            "tracks": [],
        }
        panel = ProjectExplorerPanel(lambda p: fake, "T", "*.bwproject")
        panel._load_file("ignored.bwproject")
        assert panel._data is fake
        assert panel._lbl_version.text() == "Bitwig 5.2.7"

    def test_parse_error_does_not_crash(self, monkeypatch):
        _app()
        import cratedig.gui.project_explorer as pe
        from cratedig.gui.project_explorer import ProjectExplorerPanel

        # The error dialog is modal — stub it so the test doesn't block.
        monkeypatch.setattr(pe.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

        def boom(_p):
            raise ValueError("bad file")

        panel = ProjectExplorerPanel(boom, "T", "*.npr")
        panel._load_file("x.npr")  # error is caught + shown, panel stays empty
        assert panel._data is None

    def test_scan_request_emitted_on_load(self):
        _app()
        from cratedig.gui.project_explorer import ProjectExplorerPanel

        got = []
        panel = ProjectExplorerPanel(
            lambda p: {"version": "v", "plugins": [], "samples": []}, "T", "*"
        )
        panel.pluginScanRequested.connect(lambda force: got.append(force))
        panel._load_file("x")
        assert got == [False]

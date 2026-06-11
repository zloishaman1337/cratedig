"""Bitwig/Nuendo project checker = the Ableton panel reused via parser + normalizer.

Covers the binary→rich-schema adapter (``to_checker_data``) and the parity of the
reused :class:`AlsExplorerPanel` (tabs, plugins surfaced, badge semantics).
"""

from __future__ import annotations

import os

import pytest

from cratedig.projects_fmt.common import resolve_samples_on_disk, to_checker_data


def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _index(stems):
    from cratedig.plugins.scanner import InstalledIndex

    return InstalledIndex(stems=frozenset(stems), by_format={}, signature=())


# ── to_checker_data adapter ──────────────────────────────────────────────────

class TestToCheckerData:
    def test_rich_schema_keys(self, tmp_path):
        raw = {"version": "Bitwig 5.2", "plugins": ["Serum2 [VST3]"], "samples": [], "tracks": []}
        out = to_checker_data(raw, tmp_path / "x.bwproject")
        for key in ("ableton_version", "version", "main", "arrangement", "tracks", "samples"):
            assert key in out
        assert out["version"] == "Bitwig 5.2"
        assert out["arrangement"] is None
        assert out["main"]["fader_db"] is None

    def test_plugins_hang_on_synthetic_project_track(self, tmp_path):
        raw = {"version": "v", "plugins": ["EQ-2", "Serum2 [VST3]"], "samples": [], "tracks": []}
        out = to_checker_data(raw, tmp_path / "x.bwproject")
        assert len(out["tracks"]) == 1
        track = out["tracks"][0]
        assert track["name"] == "Project"
        assert track["plugins"] == ["EQ-2", "Serum2 [VST3]"]
        assert track["instruments"] == []

    def test_no_plugins_no_track(self, tmp_path):
        out = to_checker_data({"version": "v", "plugins": [], "samples": []}, tmp_path / "x")
        assert out["tracks"] == []

    def test_samples_resolved_found_and_missing(self, tmp_path):
        (tmp_path / "kick.wav").write_bytes(b"\0")
        proj = tmp_path / "song.bwproject"
        proj.write_bytes(b"BtWg")
        raw = {"version": "v", "plugins": [], "samples": ["kick.wav", "ghost.wav"]}
        out = to_checker_data(raw, proj)
        assert out["samples"]["found"] == ["kick.wav"]
        assert out["samples"]["missing"] == ["ghost.wav"]


class TestResolveSamplesOnDisk:
    def test_case_insensitive_recursive(self, tmp_path):
        sub = tmp_path / "audio"
        sub.mkdir()
        (sub / "Snare.WAV").write_bytes(b"\0")
        res = resolve_samples_on_disk(["snare.wav", "missing.wav"], tmp_path / "p.npr")
        assert res["found"] == ["snare.wav"]
        assert res["missing"] == ["missing.wav"]

    def test_missing_dir_all_missing(self, tmp_path):
        res = resolve_samples_on_disk(["a.wav"], tmp_path / "nope" / "p.npr")
        assert res["found"] == []
        assert res["missing"] == ["a.wav"]


# ── Reused panel parity ──────────────────────────────────────────────────────

def _bitwig_panel():
    from cratedig.gui.als_explorer import AlsExplorerPanel

    raw = {"version": "Bitwig 5.2.7", "plugins": ["EQ-2", "Serum2 [VST3]"], "samples": [], "tracks": []}
    return AlsExplorerPanel(
        parser=lambda p: raw,
        normalizer=to_checker_data,
        title="Bitwig Project Checker",
        file_exts=(".bwproject",),
        file_filter="Bitwig project (*.bwproject)",
        bare_is_native=True,
    )


class TestReusedPanel:
    def test_accepts_drops(self):
        _app()
        panel = _bitwig_panel()
        assert panel.acceptDrops() is True
        panel.close()

    def test_three_tabs_and_version(self, tmp_path):
        _app()
        from PySide6.QtWidgets import QTabWidget

        panel = _bitwig_panel()
        panel._load_file(str(tmp_path / "x.bwproject"))
        assert panel._lbl_version.text() == "Bitwig 5.2.7"
        tabs = panel.findChild(QTabWidget)
        assert tabs is not None and tabs.count() == 3
        panel.close()

    def test_match_uses_sample_names(self, tmp_path):
        _app()
        (tmp_path / "kick.wav").write_bytes(b"\0")
        from cratedig.gui.als_explorer import AlsExplorerPanel

        raw = {"version": "v", "plugins": [], "samples": ["kick.wav", "ghost.wav"]}
        panel = AlsExplorerPanel(parser=lambda p: raw, normalizer=to_checker_data)
        got = []
        panel.matchRequested.connect(lambda names: got.append(list(names)))
        panel._load_file(str(tmp_path / "x.bwproject"))
        panel._on_match_clicked()
        assert got and set(got[0]) == {"kick.wav", "ghost.wav"}
        panel.close()

    def test_scan_requested_on_load(self, tmp_path):
        _app()
        panel = _bitwig_panel()
        got = []
        panel.pluginScanRequested.connect(lambda force: got.append(force))
        panel._load_file(str(tmp_path / "x.bwproject"))
        assert False in got  # cached scan requested after load
        panel.close()

    def test_parse_error_does_not_crash(self, monkeypatch, tmp_path):
        _app()
        import cratedig.gui.als_explorer as ae
        from cratedig.gui.als_explorer import AlsExplorerPanel

        monkeypatch.setattr(ae.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

        def boom(_p):
            raise ValueError("bad file")

        panel = AlsExplorerPanel(parser=boom, normalizer=to_checker_data)
        panel._load_file(str(tmp_path / "x.bwproject"))
        assert panel._data is None
        panel.close()


class TestBadgeSemantics:
    def test_nuendo_bare_name_no_badge(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel

        # bare_is_native=False (Nuendo) → unknown format, no badge.
        assert AlsExplorerPanel._plugin_badge("Pro-Q 3", None, False) is None

    def test_bitwig_bare_name_native_ok(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_OK

        glyph, color = AlsExplorerPanel._plugin_badge("EQ-2", None, True)
        assert glyph == "✓" and color == C_OK

    def test_suffixed_disk_checked_regardless(self):
        _app()
        from cratedig.gui.als_explorer import AlsExplorerPanel, C_OK, C_ERR

        ok = AlsExplorerPanel._plugin_badge("Serum2 [VST3]", _index({"serum2"}), False)
        miss = AlsExplorerPanel._plugin_badge("Sylenth1 [VST2]", _index({"serum2"}), False)
        assert ok == ("✓", C_OK)
        assert miss == ("✗", C_ERR)

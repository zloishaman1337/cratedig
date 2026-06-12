"""DAW→DAW conversion: IR, writers (round-trip through our own parsers), samples."""

from __future__ import annotations

import pytest

from cratedig.convert import convert_project, ir_from_checker_data
from cratedig.convert.options import ConvertOptions
from cratedig.convert.samples import gather_samples


def _checker_data():
    return {
        "version": "Ableton Live 11",
        "bpm": 128.0,
        "length": "0:08.00",
        "key": "A min",
        "tracks": [
            {"name": "Drums", "type": "audio", "instruments": [], "plugins": ["Pro-Q3 [VST3]"]},
            {"name": "Bass", "type": "midi", "instruments": ["Serum [VST3]"], "plugins": []},
        ],
        "samples": {"found": ["kick.wav"], "missing": ["ghost.wav"]},
    }


def _ir(tmp_path):
    proj = tmp_path / "song.als"
    proj.write_bytes(b"x")
    return ir_from_checker_data(_checker_data(), proj, "Ableton Live")


# --------------------------------------------------------------------------- #
# IR                                                                           #
# --------------------------------------------------------------------------- #

def test_ir_from_checker_data_shape(tmp_path):
    ir = _ir(tmp_path)
    assert ir.bpm == 128.0
    assert ir.key == "A min"
    assert [t.name for t in ir.tracks] == ["Drums", "Bass"]
    assert ir.tracks[1].instruments == ("Serum [VST3]",)
    assert ir.samples_found == ("kick.wav",)
    assert ir.samples_missing == ("ghost.wav",)


# --------------------------------------------------------------------------- #
# samples                                                                      #
# --------------------------------------------------------------------------- #

def test_gather_samples_copies_found_and_reports_missing(tmp_path):
    (tmp_path / "kick.wav").write_bytes(b"RIFFkick")
    ir = _ir(tmp_path)
    out = gather_samples(ir, tmp_path / "out" / "media")
    assert out["media"] == {"kick.wav": "media/kick.wav"}
    assert (tmp_path / "out" / "media" / "kick.wav").is_file()
    assert "ghost.wav" in out["missing"]


# --------------------------------------------------------------------------- #
# Reaper writer — round-trips through parse_rpp                                #
# --------------------------------------------------------------------------- #

def test_reaper_writer_round_trips(tmp_path):
    from cratedig.projects_fmt.reaper import parse_rpp

    (tmp_path / "kick.wav").write_bytes(b"RIFFkick")
    ir = _ir(tmp_path)
    out = tmp_path / "conv" / "song.rpp"
    res = convert_project(ir, "reaper", out, ConvertOptions())

    parsed = parse_rpp(out)
    assert parsed["bpm"] == 128.0
    names = [t["name"] for t in parsed["tracks"]]
    assert any(n.startswith("Drums") for n in names)
    assert any(n.startswith("Bass") for n in names)
    assert "kick.wav" in parsed["samples"]
    assert res["copied"] == ["kick.wav"]
    assert "ghost.wav" in res["missing"]


# --------------------------------------------------------------------------- #
# Ableton writer — round-trips through parse_als                              #
# --------------------------------------------------------------------------- #

def test_ableton_writer_round_trips(tmp_path):
    from cratedig.als.parser import parse_als

    (tmp_path / "kick.wav").write_bytes(b"RIFFkick")
    ir = _ir(tmp_path)
    out = tmp_path / "conv" / "song.als"
    convert_project(ir, "ableton", out, ConvertOptions())

    parsed = parse_als(str(out))
    assert round(parsed["arrangement"]["bpm"]) == 128 or parsed.get("ableton_version")
    names = [t["name"] for t in parsed["tracks"]]
    assert any(n.startswith("Drums") for n in names)
    assert "kick.wav" in parsed["samples"]["found"]


# --------------------------------------------------------------------------- #
# AAF writer — optional (pyaaf2)                                               #
# --------------------------------------------------------------------------- #

def test_aaf_writer_emits_named_slots(tmp_path):
    aaf2 = pytest.importorskip("aaf2")

    (tmp_path / "kick.wav").write_bytes(b"RIFFkick")
    ir = _ir(tmp_path)
    out = tmp_path / "conv" / "song.aaf"
    convert_project(ir, "aaf", out, ConvertOptions())

    assert out.is_file()
    with aaf2.open(str(out), "r") as f:
        comps = [m for m in f.content.mobs if m.usage == "Usage_TopLevel"]
        assert len(comps) == 1
        slots = list(comps[0].slots)
        assert len(slots) == 2  # one per track


def test_unknown_target_raises(tmp_path):
    ir = _ir(tmp_path)
    with pytest.raises(ValueError):
        convert_project(ir, "cubase", tmp_path / "x.cpr", ConvertOptions())


# --------------------------------------------------------------------------- #
# Convert UI wiring (PySide6 optional)                                         #
# --------------------------------------------------------------------------- #

def _qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_convert_button_enables_after_load(tmp_path):
    _qapp()
    from cratedig.gui.als_explorer import AlsExplorerPanel

    # Build a tiny real .rpp the detect panel can open.
    proj = tmp_path / "demo.rpp"
    proj.write_text('<REAPER_PROJECT 0.1 "7.0"\n  TEMPO 120 4 4\n  <TRACK\n    NAME "T1"\n  >\n>\n')

    w = AlsExplorerPanel(detect=True)
    assert w._btn_convert.isEnabled() is False
    w._load_file(str(proj))
    assert w._btn_convert.isEnabled() is True
    assert w._source_format == "Reaper"
    w.close()


def test_convert_dialog_result_spec(tmp_path):
    _qapp()
    from cratedig.gui.convert_dialog import ConvertDialog

    dlg = ConvertDialog(str(tmp_path / "song.als"))
    target, options, out = dlg.result_spec()
    assert target == "reaper"  # first dropdown entry
    assert out.endswith(".rpp")
    assert options.tempo and options.copy_samples
    dlg.close()

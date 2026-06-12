"""Tests for the Reaper .rpp parser (full-parity rich tracks)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cratedig.projects_fmt.reaper import parse_rpp

_REAL = Path(__file__).resolve().parent.parent / "projects" / "tmf-small.RPP"

_SYNTH = """<REAPER_PROJECT 0.1 "7.16/win64" 1700000000
  TEMPO 128.5 4 4
  <TRACK
    NAME "Drums"
    <FXCHAIN
      <VST "VST3i: Serum (Xfer)" "serum.vst3" 0 ""
      >
      <VST "VST: ReaComp (Cockos)" "reacomp.dll" 0 ""
      >
    >
    <ITEM
      <SOURCE WAVE
        FILE "kick.wav"
      >
    >
  >
>
"""


def test_synthetic_extraction(tmp_path):
    f = tmp_path / "p.rpp"
    f.write_text(_SYNTH, encoding="utf-8")
    d = parse_rpp(f)
    assert d["format"] == "reaper"
    assert d["version"] == "Reaper 7.16"
    assert d["bpm"] == 128.5
    assert len(d["tracks"]) == 1
    track = d["tracks"][0]
    assert track["name"] == "Drums"
    assert "Serum [VST3]" in track["instruments"]
    assert "ReaComp [VST2]" in track["plugins"]
    assert d["samples"] == ["kick.wav"]


def test_rejects_non_reaper(tmp_path):
    f = tmp_path / "bad.rpp"
    f.write_text("not a reaper project", encoding="utf-8")
    with pytest.raises(ValueError, match="REAPER"):
        parse_rpp(f)


@pytest.mark.skipif(not _REAL.is_file(), reason="real Reaper project not present")
class TestReal:
    def test_tempo_and_tracks(self):
        d = parse_rpp(_REAL)
        assert d["bpm"] == 120.0
        assert len(d["tracks"]) == 4
        names = {t["name"] for t in d["tracks"]}
        assert "kick" in names

    def test_plugins_and_samples(self):
        d = parse_rpp(_REAL)
        assert any("ReaComp" in p for p in d["plugins"])
        assert any(s.lower().startswith("01-kick") for s in d["samples"])

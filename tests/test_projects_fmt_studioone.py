"""Tests for the Studio One .song (ZIP) best-effort parser."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cratedig.projects_fmt.studioone import parse_song

_REAL = Path(__file__).resolve().parent.parent / "projects" / "CineSymphony v1.2.song"

_SYNTH_DEVICES = """<?xml version="1.0"?>
<Device>
  <Attributes x:id="classInfo" classID="{1}" name="Kontakt" category="AudioSynth" subCategory="VST2"/>
  <Attributes x:id="classInfo" classID="{2}" name="Pro-Q 3" category="AudioEffect" subCategory="VST3"/>
</Device>
"""


def _build_song(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metainfo.xml", "<MetaInformation/>")
        zf.writestr("Devices/audiosynthfolder.xml", _SYNTH_DEVICES)
        zf.writestr("Song/mediapool.xml", '<MediaPool url="Media/loop.wav"/>')
        zf.writestr("Audio Files/take.wav", b"\0")


def test_synthetic_extraction(tmp_path):
    f = tmp_path / "p.song"
    _build_song(f)
    d = parse_song(f)
    assert d["format"] == "studioone"
    assert "Kontakt [VST2]" in d["tracks"][0]["instruments"]
    assert "Pro-Q 3 [VST3]" in d["tracks"][0]["plugins"]
    assert {"take.wav", "loop.wav"} <= set(d["samples"])


def test_rejects_non_zip(tmp_path):
    f = tmp_path / "bad.song"
    f.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="ZIP"):
        parse_song(f)


@pytest.mark.skipif(not _REAL.is_file(), reason="real Studio One project not present")
class TestReal:
    def test_instruments(self):
        d = parse_song(_REAL)
        plugins = d["tracks"][0]["instruments"] + d["tracks"][0]["plugins"]
        assert any("Kontakt" in p for p in plugins)

    def test_shape(self):
        d = parse_song(_REAL)
        assert set(d) >= {"format", "version", "plugins", "samples", "tracks", "bpm"}

"""Tests for the Logic Pro .logicx bundle parser."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from cratedig.projects_fmt.logic import parse_logicx

_REAL = (Path(__file__).resolve().parent.parent / "projects"
         / "Elvis Drew - Not a love song 06-06-25.logicx")


def _build_bundle(root: Path) -> None:
    alt = root / "Alternatives" / "000"
    alt.mkdir(parents=True)
    meta = {
        "BeatsPerMinute": 90.0,
        "NumberOfTracks": 12,
        "SongKey": "A",
        "SongGenderKey": "major",
        "AudioFiles": ["Audio Files/loop.wav", "Audio Files/vox.aiff"],
        "PlaybackFiles": [],
    }
    (alt / "MetaData.plist").write_bytes(plistlib.dumps(meta))
    # An AU effect record: \x02 NAME \x00 <manufacturer4> <type 'xfua'> <subtype4>
    (alt / "ProjectData").write_bytes(b"\x00" * 8 + b"\x02Pro-Q 3\x00 retSxfuaQ3FF" + b"\x00" * 8)
    res = root / "Resources"
    res.mkdir()
    (res / "ProjectInformation.plist").write_bytes(
        plistlib.dumps({"LastSavedFrom": "Logic Pro 11.2 (6306)"})
    )


def test_synthetic_bundle(tmp_path):
    root = tmp_path / "song.logicx"
    _build_bundle(root)
    d = parse_logicx(root)
    assert d["format"] == "logic"
    assert d["version"] == "Logic Pro 11.2"
    assert d["bpm"] == 90.0
    assert d["key"] == "A major"
    assert d["track_count"] == 12
    assert {"loop.wav", "vox.aiff"} <= set(d["samples"])
    assert "Pro-Q 3 [AU]" in d["tracks"][0]["plugins"]


def test_rejects_non_bundle(tmp_path):
    f = tmp_path / "x.logicx"
    f.write_bytes(b"not a dir")
    with pytest.raises(ValueError, match="bundle"):
        parse_logicx(f)


@pytest.mark.skipif(not _REAL.is_dir(), reason="real Logic project not present")
class TestReal:
    def test_meta(self):
        d = parse_logicx(_REAL)
        assert d["bpm"] == 105.0
        assert d["key"] == "D minor"
        assert d["track_count"] == 315
        assert d["version"].startswith("Logic Pro")

    def test_plugins_and_samples(self):
        d = parse_logicx(_REAL)
        plugins = d["tracks"][0]["instruments"] + d["tracks"][0]["plugins"]
        assert any("Serum" in p for p in plugins)
        assert any("Kontakt" in p for p in d["tracks"][0]["instruments"])
        assert len(d["samples"]) > 50

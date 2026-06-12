"""Tests for the FL Studio .flp best-effort parser."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from cratedig.projects_fmt.flstudio import parse_flp

_REAL = Path(__file__).resolve().parent.parent / "projects" / "Aston Martin Music Remake.flp"


def _build_flp() -> bytes:
    """A minimal FLhd + FLdt stream with version (199), tempo (66) and a sample (196)."""
    def text_ev(eid: int, s: bytes) -> bytes:
        body = s + b"\x00"
        return bytes([eid]) + bytes([len(body)]) + body  # len < 128 → single varint byte

    events = b"".join([
        bytes([66]) + struct.pack("<H", 140),                 # word tempo
        text_ev(199, b"20.1.2"),                              # version
        text_ev(196, b"C:\\packs\\snare.wav"),                # sample path
        text_ev(201, b"Sytrus"),                              # generator
        text_ev(203, b"Fruity Reeverb"),                      # effect
    ])
    flhd = b"FLhd" + struct.pack("<I", 6) + struct.pack("<hhh", 0, 4, 96)
    fldt = b"FLdt" + struct.pack("<I", len(events)) + events
    return flhd + fldt


def test_synthetic_extraction(tmp_path):
    f = tmp_path / "p.flp"
    f.write_bytes(_build_flp())
    d = parse_flp(f)
    assert d["format"] == "flstudio"
    assert d["version"] == "FL Studio 20.1.2"
    assert d["bpm"] == 140.0
    assert "snare.wav" in d["samples"]
    assert "Sytrus" in d["tracks"][0]["instruments"]
    assert "Fruity Reeverb" in d["tracks"][0]["plugins"]


def test_rejects_non_flp(tmp_path):
    f = tmp_path / "bad.flp"
    f.write_bytes(b"NOPE" + b"\x00" * 32)
    with pytest.raises(ValueError, match="FLhd"):
        parse_flp(f)


@pytest.mark.skipif(not _REAL.is_file(), reason="real FL project not present")
class TestReal:
    def test_version_and_tempo(self):
        d = parse_flp(_REAL)
        assert d["version"].startswith("FL Studio")
        assert d["bpm"] is not None

    def test_plugins_and_samples(self):
        d = parse_flp(_REAL)
        assert any("Sytrus" in p for p in d["plugins"])
        assert any(s.lower().endswith(".wav") for s in d["samples"])

"""Tests for the Pro Tools .ptx best-effort parser (obfuscated body — limited yield)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cratedig.projects_fmt.protools import parse_ptx

_REAL = Path(__file__).resolve().parent.parent / "projects" / "Can't Get Enough Pro Tools Demo.ptx"


def test_recognises_marker(tmp_path):
    f = tmp_path / "p.ptx"
    f.write_bytes(b"\x03garbage Pro Tools\x00\x00Audio Files/drum.wav\x00padding")
    d = parse_ptx(f)
    assert d["format"] == "protools"
    assert d["version"] == "Pro Tools"
    assert "drum.wav" in d["samples"]
    assert d["plugins"] == []  # AAX names are XOR-encoded; not emitted


def test_rejects_non_pt(tmp_path):
    f = tmp_path / "bad.ptx"
    f.write_bytes(b"NOPE no marker here")
    with pytest.raises(ValueError, match="Pro Tools"):
        parse_ptx(f)


@pytest.mark.skipif(not _REAL.is_file(), reason="real Pro Tools session not present")
class TestReal:
    def test_shape(self):
        d = parse_ptx(_REAL)
        assert d["format"] == "protools"
        assert d["version"] == "Pro Tools"
        assert isinstance(d["samples"], list)

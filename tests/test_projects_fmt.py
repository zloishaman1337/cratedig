"""Tests for the Bitwig / Nuendo best-effort project parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from cratedig.projects_fmt.bitwig import parse_bwproject
from cratedig.projects_fmt.common import extract_sample_basenames, read_be_string
from cratedig.projects_fmt.nuendo import parse_npr

_PROJECTS = Path(__file__).resolve().parent.parent / "projects"
_NPR = _PROJECTS / "Changes.npr"
_BW = _PROJECTS / "Surface Tension.bwproject"


class TestCommonHelpers:
    def test_extract_sample_basenames_drops_dirs_and_prefix_bytes(self):
        blob = b"\x2asamples/sub dir/Kick_01.wav\x00\xffother\x07Snare 02.aiff junk"
        names = extract_sample_basenames(blob)
        assert "Kick_01.wav" in names
        assert "Snare 02.aiff" in names
        # No directory component leaks through.
        assert all("/" not in n for n in names)

    def test_extract_sample_basenames_distinct_sorted(self):
        blob = b"a/x.wav b/x.wav c/Y.WAV"
        assert extract_sample_basenames(blob) == ["x.wav", "Y.WAV"]

    def test_read_be_string_ok(self):
        data = b"\x00\x00\x00\x05Hello\x00"
        assert read_be_string(data, 0) == ("Hello", 9)

    def test_read_be_string_strips_bom_and_nul(self):
        payload = "Serum".encode("utf-8") + b"\x00" + "﻿".encode("utf-8")
        data = len(payload).to_bytes(4, "big") + payload
        value, _ = read_be_string(data, 0)
        assert value == "Serum"

    def test_read_be_string_rejects_implausible_length(self):
        assert read_be_string(b"\xff\xff\xff\xff", 0) is None
        assert read_be_string(b"\x00\x00\x00\x10short", 0) is None


class TestSizeGuard:
    def test_oversize_file_rejected(self, tmp_path, monkeypatch):
        from cratedig.projects_fmt import common

        monkeypatch.setattr(common, "MAX_PROJECT_BYTES", 10)
        f = tmp_path / "big.bwproject"
        f.write_bytes(b"BtWg" + b"\x00" * 100)
        with pytest.raises(ValueError, match="too large"):
            parse_bwproject(f)


class TestHeaderValidation:
    def test_nuendo_rejects_non_riff(self, tmp_path):
        f = tmp_path / "bad.npr"
        f.write_bytes(b"NOPE" + b"\x00" * 100)
        with pytest.raises(ValueError, match="RIFF"):
            parse_npr(f)

    def test_bitwig_rejects_non_btwg(self, tmp_path):
        f = tmp_path / "bad.bwproject"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        with pytest.raises(ValueError, match="BtWg"):
            parse_bwproject(f)


@pytest.mark.skipif(not _NPR.is_file(), reason="real Nuendo sample project not present")
class TestNuendoReal:
    def test_version(self):
        assert parse_npr(_NPR)["version"] == "Nuendo 5.0.0"

    def test_plugins_recovered(self):
        plugins = parse_npr(_NPR)["plugins"]
        assert "REVerence" in plugins
        assert "VintageCompressor" in plugins
        assert "Standard Panner" not in plugins  # routing entry filtered

    def test_samples_recovered(self):
        samples = parse_npr(_NPR)["samples"]
        assert len(samples) > 20
        assert all(s.lower().endswith((".wav", ".aif", ".aiff", ".flac", ".mp3")) for s in samples)

    def test_shape(self):
        data = parse_npr(_NPR)
        assert set(data) >= {"format", "version", "plugins", "samples", "tracks", "bpm"}
        assert data["format"] == "nuendo"

    def test_bpm_recovered(self):
        assert parse_npr(_NPR)["bpm"] == 120.0


@pytest.mark.skipif(not _BW.is_file(), reason="real Bitwig sample project not present")
class TestBitwigReal:
    def test_version(self):
        assert parse_bwproject(_BW)["version"] == "Bitwig 5.2.7"

    def test_third_party_plugins_have_format_suffix(self):
        plugins = parse_bwproject(_BW)["plugins"]
        assert any(p.startswith("Serum2") and p.endswith("[VST3]") for p in plugins)
        assert any("FabFilter Pro-MB" in p and p.endswith("[VST2]") for p in plugins)

    def test_native_devices_have_no_suffix(self):
        plugins = parse_bwproject(_BW)["plugins"]
        assert "EQ-2" in plugins  # native .bwdevice → bare name

    def test_samples_and_presets(self):
        data = parse_bwproject(_BW)
        assert len(data["samples"]) > 5
        assert data["plugin_state_count"] == 74

    def test_bpm_recovered(self):
        assert parse_bwproject(_BW)["bpm"] == 140.0

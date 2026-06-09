"""Tests for cratedig.paths frozen/source runtime resolution."""

from pathlib import Path

import cratedig.paths as paths


def test_is_frozen_false_in_source():
    assert paths.is_frozen() is False


def test_user_data_dir_named_cratedig():
    assert paths.user_data_dir().name == "cratedig"


def test_resource_root_is_repo_root_in_source():
    root = paths.resource_root()
    assert (root / "cratedig").is_dir()
    assert (root / "config.example.toml").is_file()


def test_bundled_binary_none_in_source():
    assert paths.bundled_binary("ffmpeg") is None
    assert paths.bundled_binary("ffplay") is None


def test_ffmpeg_path_falls_back_to_which(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "ffmpeg.exe" if name == "ffmpeg" else None)
    assert paths.ffmpeg_path() == "ffmpeg.exe"


def test_ffplay_path_falls_back_to_which(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
    assert paths.ffplay_path() == "ffplay.exe"


def test_bundled_binary_prefers_bundle_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / paths._bin_name("ffmpeg")
    exe.write_bytes(b"x")
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.bundled_binary("ffmpeg") == str(exe)


def test_resource_path_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("config.example.toml") == tmp_path / "config.example.toml"

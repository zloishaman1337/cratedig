"""Tests for gain_db playback feature.

TDD-style: these are FAILING tests that define the API the developer must satisfy.
Tests cover:
- AudioPlayer.play with gain_db parameter and -af filter
- Player.play forwarding gain_db to AudioPlayer
- Edge cases: gain_db=None, gain_db=0.0, negative gains
- Ffplay argv construction with volume filter
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cratedig.audio.playback import AudioPlayer
from cratedig.gui.player import Player


class TestAudioPlayerPlayWithGainDb:
    """AudioPlayer.play(target, gain_db=...) constructs ffplay argv with -af volume filter."""

    def test_play_with_positive_gain_adds_volume_filter(self, monkeypatch):
        """AudioPlayer.play(target, gain_db=6.0) adds -af volume=6.0dB to argv."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", gain_db=6.0)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        filter_arg = cmd[af_idx + 1]
        assert "volume=6.0dB" in filter_arg

    def test_play_with_negative_gain_adds_volume_filter(self, monkeypatch):
        """AudioPlayer.play(target, gain_db=-3.5) adds -af volume=-3.5dB to argv."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", gain_db=-3.5)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        filter_arg = cmd[af_idx + 1]
        assert "volume=-3.5dB" in filter_arg

    def test_play_with_zero_gain_no_filter(self, monkeypatch):
        """AudioPlayer.play(target, gain_db=0.0) does NOT add -af."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", gain_db=0.0)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" not in cmd

    def test_play_with_none_gain_no_filter(self, monkeypatch):
        """AudioPlayer.play(target, gain_db=None) does NOT add -af."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", gain_db=None)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" not in cmd

    def test_play_default_gain_db_is_none(self, monkeypatch):
        """AudioPlayer.play(target) with no gain_db arg defaults to None (no filter)."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav")

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" not in cmd


class TestPlayerPlayWithGainDb:
    """Player.play forwards gain_db to AudioPlayer.play."""

    def test_player_play_forwards_gain_db_to_audio_player(self, monkeypatch):
        """Player.play(path, gain_db=4.0) forwards gain_db to AudioPlayer.play."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        gui_player = Player()
        gui_player.play("snare.wav", gain_db=4.0)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        filter_arg = cmd[af_idx + 1]
        assert "volume=4.0dB" in filter_arg

    def test_player_play_without_gain_db_no_filter(self, monkeypatch):
        """Player.play(path) with no gain_db arg does NOT add -af."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        gui_player = Player()
        gui_player.play("snare.wav")

        assert len(calls) == 1
        cmd = calls[0]
        assert "-af" not in cmd


class TestGainDbIntegration:
    """Integration: gain_db works with other play parameters (start_sec, duration_sec, loop)."""

    def test_gain_db_with_start_sec_and_duration(self, monkeypatch):
        """gain_db coexists with start_sec and duration_sec."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", start_sec=1.0, duration_sec=2.5, gain_db=3.0)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-ss" in cmd
        assert "-t" in cmd
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        filter_arg = cmd[af_idx + 1]
        assert "volume=3.0dB" in filter_arg

    def test_gain_db_with_loop(self, monkeypatch):
        """gain_db coexists with loop=True."""
        calls = []

        class FakeProc:
            def poll(self):
                return 0

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return FakeProc()

        monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
        monkeypatch.setattr("subprocess.Popen", fake_popen)

        player = AudioPlayer()
        player.play("kick.wav", loop=True, gain_db=2.0)

        assert len(calls) == 1
        cmd = calls[0]
        assert "-loop" in cmd
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        filter_arg = cmd[af_idx + 1]
        assert "volume=2.0dB" in filter_arg

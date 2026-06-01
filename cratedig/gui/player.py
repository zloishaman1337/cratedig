"""Thin GUI-safe wrapper around AudioPlayer (ffplay subprocess)."""

from __future__ import annotations

from pathlib import Path

from ..audio.playback import AudioPlayer


class Player:
    """Non-blocking playback using ffplay. Safe to call on the GUI thread."""

    def __init__(self) -> None:
        self._player = AudioPlayer()

    def play(self, path: str | Path) -> None:
        self._player.play(path)

    def stop(self) -> None:
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.is_playing()

"""Thin GUI-safe wrapper around AudioPlayer (ffplay subprocess)."""

from __future__ import annotations

from pathlib import Path

from ..audio.playback import AudioPlayer


class Player:
    """Non-blocking playback using ffplay. Safe to call on the GUI thread."""

    def __init__(self) -> None:
        self._player = AudioPlayer()
        self.apply_loudness_leveling: bool = False

    def set_loudness_leveling(self, enable: bool) -> None:
        """Enable or disable loudness leveling on A/B slot switches."""
        self.apply_loudness_leveling = enable

    def play(
        self,
        path: str | Path,
        *,
        start_sec: float | None = None,
        duration_sec: float | None = None,
        loop: bool = False,
        gain_db: float | None = None,
    ) -> None:
        self._player.play(path, start_sec=start_sec, duration_sec=duration_sec, loop=loop, gain_db=gain_db)

    def stop(self) -> None:
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.is_playing()

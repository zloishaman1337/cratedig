"""Startup online-update check + download threads (GitHub Releases feed).

Network lives entirely in :mod:`cratedig.updater`; these QThreads only marshal its
results back to the GUI thread. The check is silent unless a newer version exists,
so a network failure or an up-to-date install never nags the user.
"""

from __future__ import annotations

import tempfile

from PySide6.QtCore import QThread, Signal

import cratedig
from cratedig import updater


class UpdateCheckThread(QThread):
    """Fetch the latest release; emit :attr:`found` only when it is newer."""

    found = Signal(object)  # updater.Release
    up_to_date = Signal()
    failed = Signal(str)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            release = updater.fetch_latest_release()
            newer = updater.is_newer(release.version, cratedig.__version__)
        except updater.UpdateError as exc:
            self.failed.emit(str(exc))
            return
        if newer:
            self.found.emit(release)
        else:
            self.up_to_date.emit()


class UpdateDownloadThread(QThread):
    """Download + minisign-verify the OS installer for ``release`` into a temp dir."""

    done = Signal(str)  # verified installer path
    failed = Signal(str)
    progress = Signal(int, int)  # (bytes_done, bytes_total); total=0 if unknown

    def __init__(self, release, parent=None) -> None:
        super().__init__(parent)
        self._release = release
        self._cancelled = False

    def cancel(self) -> None:
        """Request abort; the download loop polls this between chunks."""
        self._cancelled = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            dest = tempfile.mkdtemp(prefix="cratedig-update-dl-")
            path = updater.download_and_verify(
                self._release,
                dest,
                progress=lambda d, t: self.progress.emit(d, t),
                cancel=lambda: self._cancelled,
            )
        except updater.UpdateError as exc:
            if self._cancelled:
                return  # user-initiated abort — stay silent
            self.failed.emit(str(exc))
            return
        self.done.emit(str(path))

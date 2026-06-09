"""Bottom-right transient toast notifications stacked over a host widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, Signal
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel

_COLORS = {
    "info": "#2b2b2b",
    "ok": "#2e7d32",
    "error": "#c62828",
}


class _Toast(QFrame):
    """A single fading notification card."""

    closed = Signal()

    def __init__(self, text: str, color: str, parent) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(
            f"QFrame{{background:{color};border:1px solid #555;border-radius:6px;}}"
            "QLabel{color:#ffffff;font-size:12px;background:transparent;border:none;}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(280)
        layout.addWidget(label)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)

    def show_animated(self, msec: int) -> None:
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        QTimer.singleShot(msec, self._fade_out)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(300)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.closed.emit)
        self._anim.start()


class ToastManager:
    """Shows transient toasts stacked bottom-right of a host widget."""

    _MARGIN = 14
    _SPACING = 6

    def __init__(self, host) -> None:
        self._host = host
        self._toasts: list[_Toast] = []

    def show(self, text: str, level: str = "info", msec: int = 3500) -> None:
        if not text:
            return
        toast = _Toast(text, _COLORS.get(level, _COLORS["info"]), self._host)
        toast.closed.connect(lambda t=toast: self._remove(t))
        self._toasts.append(toast)
        self._reposition()
        toast.show_animated(msec)

    def reposition(self) -> None:
        self._reposition()

    def _remove(self, toast: _Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.deleteLater()
        self._reposition()

    def _reposition(self) -> None:
        host = self._host
        x_right = host.width() - self._MARGIN
        y = host.height() - self._MARGIN
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(x_right - toast.width(), y)
            y -= self._SPACING

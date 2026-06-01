"""Waveform visualization widget."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QWidget

from .logic import compute_peaks


class WaveformPane(QWidget):
    """Draws min/max waveform peaks for the selected sample."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mono: np.ndarray | None = None
        self._peaks: list[tuple[float, float]] = []
        self.setMinimumHeight(60)

    def set_mono(self, mono: np.ndarray | None) -> None:
        """Cache the mono signal and recompute peaks at current width."""
        self._mono = mono
        self._recompute()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recompute()
        self.update()

    def _recompute(self) -> None:
        if self._mono is None or self._mono.size == 0:
            self._peaks = []
            return
        w = self.width()
        if w <= 0:
            self._peaks = []
            return
        self._peaks = compute_peaks(self._mono, w)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w = self.width()
        h = self.height()
        mid = h / 2.0

        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))

        if not self._peaks:
            # Draw flat center line
            pen = QPen(QColor(100, 100, 100))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(0, int(mid), w, int(mid))
            painter.end()
            return

        # Scale amplitude to widget height, clamping to [-1, 1]
        scale = mid * 0.95
        n = len(self._peaks)

        # Build a continuous filled envelope: top contour left→right, then
        # bottom contour right→left. Map every pixel column to a peak so the
        # outline never breaks even when n != w.
        top: list[QPointF] = []
        bot: list[QPointF] = []
        for x in range(w):
            lo, hi = self._peaks[min(n - 1, x * n // w)]
            lo_c = max(-1.0, min(1.0, float(lo)))
            hi_c = max(-1.0, min(1.0, float(hi)))
            top.append(QPointF(x, mid - hi_c * scale))
            bot.append(QPointF(x, mid - lo_c * scale))

        poly = QPolygonF(top + bot[::-1])
        painter.setPen(QPen(QColor(80, 160, 80), 1))
        painter.setBrush(QColor(80, 160, 80))
        painter.drawPolygon(poly)

        painter.end()

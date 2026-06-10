"""Simpler: combined preview + editor pane (replaces the waveform pane).

Draws the selected sample's waveform with draggable region and fade handles,
plus reverse / gain / ADSR controls. Edits are rendered through the pure
``audio.editor`` core; preview and export are routed out via signals, and the
waveform itself is a drag source that renders to the Saved folder on drag-start.
"""

from __future__ import annotations

import re
from math import cos, log10, radians, sin
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QMimeData, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QKeySequence,
    QPainter,
    QPen,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QDial,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QApplication,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..audio.editor import (
    ADSR,
    apply_edit,
    auto_slice,
    dated_export_dir,
    default_export_name,
    detect_transients,
    normalize_peak,
    render_edit,
    snap_to_zero_crossing,
    trim_silence,
    write_wav,
)
from .logic import clamp_region, compute_peaks, time_to_x, x_to_time
from .theme import ACCENT, ACCENT_2, BORDER, PINK, icon

_HANDLE_GRAB_PX = 8
_MIN_VIEW_SEC = 0.02
_PAN_SPEED = 4.0
_LIVE_RENDER_MAX_SAMPLES = 300_000
_EDIT_SUFFIX_RE = re.compile(r"(?:_edit_\d{6})+$")


class _WaveCanvas(QWidget):
    """Waveform with draggable region (start/end) and fade (in/out) handles."""

    edit_changed = Signal()
    drag_started = Signal()  # ask the parent to render+persist and start the QDrag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mono: np.ndarray | None = None
        self._rendered_mono: np.ndarray | None = None
        self._rendered_peaks: list[tuple[float, float]] = []
        self._rendered_source_region: tuple[float, float] = (0.0, 0.0)
        self.adsr: ADSR | None = None
        self.loop_enabled = False
        self.duration = 0.0
        self.region: tuple[float, float] = (0.0, 0.0)
        self.view: tuple[float, float] = (0.0, 0.0)
        self.playhead_time: float | None = None
        self.fade_in = 0.0
        self.fade_out = 0.0
        self._transients: list[float] = []
        self._show_transients = True
        self._drag_handle: str | None = None
        self._drag_handle_changed = False
        self._press_pos = None
        self._panning = False
        self._pan_press_x = 0.0
        self._pan_press_view: tuple[float, float] = (0.0, 0.0)
        self.setMinimumHeight(96)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grabGesture(Qt.GestureType.PinchGesture)

    def set_sample(self, duration: float) -> None:
        self.duration = max(0.0, float(duration or 0.0))
        self.region = (0.0, self.duration)
        self.view = (0.0, self.duration)
        self.playhead_time = None
        self.fade_in = 0.0
        self.fade_out = 0.0
        self.update()

    def set_mono(self, mono: np.ndarray | None) -> None:
        self._mono = mono
        self.update()

    def set_rendered_mono(self, mono: np.ndarray | None) -> None:
        self._rendered_mono = None if mono is None else np.asarray(mono, dtype=np.float32)
        self._rendered_source_region = self.region if mono is not None else (0.0, 0.0)
        self._recompute_rendered()
        self.update()

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_enabled = enabled
        self.update()

    def set_adsr(self, adsr: ADSR | None) -> None:
        self.adsr = adsr
        self.update()

    def set_transients(self, times) -> None:
        self._transients = list(times or [])
        self.update()

    def set_show_transients(self, show: bool) -> None:
        self._show_transients = bool(show)
        self.update()

    def set_playhead(self, seconds: float | None) -> None:
        if seconds is None or self.duration <= 0:
            self.playhead_time = None
        else:
            self.playhead_time = max(0.0, min(self.duration, seconds))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recompute_rendered()
        self.update()

    def _set_view(self, start: float, span: float) -> None:
        if self.duration <= 0:
            return
        span = max(min(self.duration, _MIN_VIEW_SEC), min(self.duration, span))
        start = max(0.0, min(start, self.duration - span))
        old_span = self.view[1] - self.view[0]
        self.view = (start, start + span)
        # Rendered-edit peaks depend on the region's on-screen pixel width, i.e.
        # the zoom span — not the pan offset. Recompute only when the span changes
        # so panning is a pure view shift + repaint (source peaks are rebinned in
        # paintEvent from the visible slice, which is already zoom-bounded).
        if abs(span - old_span) > 1e-9:
            self._recompute_rendered()
        self.update()

    # --- handle geometry ---

    def _handle_x(self) -> dict[str, int]:
        w = self.width()
        start, end = self.region
        return {
            "start": self._time_to_x(start, w),
            "end": self._time_to_x(end, w),
            "fade_in": self._time_to_x(start + self.fade_in, w),
            "fade_out": self._time_to_x(end - self.fade_out, w),
        }

    def _pick_handle(self, x: int) -> str | None:
        nearest, best = None, _HANDLE_GRAB_PX + 1
        for name, hx in self._handle_x().items():
            dist = abs(x - hx)
            if dist < best:
                nearest, best = name, dist
        return nearest

    def _time_to_x(self, t: float, width: int | None = None) -> int:
        width = self.width() if width is None else width
        view_start, view_end = self.view
        return time_to_x(t - view_start, width, view_end - view_start)

    def _time_to_view_x(self, t: float, width: int | None = None) -> float:
        width = self.width() if width is None else width
        view_start, view_end = self.view
        span = view_end - view_start
        if span <= 0 or width <= 0:
            return 0.0
        return (t - view_start) * width / span

    def _region_view_x(self) -> tuple[float, float]:
        start, end = self.region
        return self._time_to_view_x(start), self._time_to_view_x(end)

    def _region_peak_width(self, region: tuple[float, float] | None = None) -> int:
        start, end = self.region if region is None else region
        start_x = self._time_to_view_x(start)
        end_x = self._time_to_view_x(end)
        if self.width() <= 0:
            return 0
        # Cache the rendered edit at the region's current on-screen scale. This
        # keeps the preview smooth when zoomed in, while avoiding runaway bins.
        return min(16384, max(self.width(), int(np.ceil(abs(end_x - start_x)))))

    def _recompute_rendered(self) -> None:
        if self._rendered_mono is None or self._rendered_mono.size == 0:
            self._rendered_peaks = []
            return
        width = self._region_peak_width(self._rendered_source_region)
        self._rendered_peaks = compute_peaks(self._rendered_mono, width)

    def _x_to_time(self, x: float) -> float:
        view_start, view_end = self.view
        return view_start + x_to_time(x, self.width(), view_end - view_start)

    def _samples_for_interval(
        self,
        samples: np.ndarray | None,
        source_start: float,
        source_end: float,
        interval_start: float,
        interval_end: float,
    ) -> np.ndarray:
        if samples is None or samples.size == 0 or source_end <= source_start or interval_end <= interval_start:
            return np.empty(0, dtype=np.float32)
        a = max(source_start, interval_start)
        b = min(source_end, interval_end)
        if b <= a:
            return np.empty(0, dtype=np.float32)
        start_ratio = (a - source_start) / (source_end - source_start)
        end_ratio = (b - source_start) / (source_end - source_start)
        i0 = max(0, min(samples.size, int(np.floor(start_ratio * samples.size))))
        i1 = max(i0 + 1, min(samples.size, int(np.ceil(end_ratio * samples.size))))
        return samples[i0:i1]

    def _draw_waveform(
        self,
        painter: QPainter,
        samples: np.ndarray,
        x0: float,
        x1: float,
        mid: float,
        scale: float,
        pen_color: QColor,
        brush_color: QColor | None,
    ) -> None:
        width = max(1, int(np.ceil(x1 - x0)))
        if samples.size == 0 or width <= 0:
            return
        clean = np.asarray(samples, dtype=np.float32)
        clean = clean[np.isfinite(clean)]
        if clean.size == 0:
            return

        painter.setPen(QPen(pen_color, 1))
        samples_per_px = clean.size / float(width)
        if samples_per_px <= 3.0:
            count = min(width + 1, clean.size)
            idx = np.linspace(0, clean.size - 1, count).astype(np.int64)
            points = QPolygonF([
                QPointF(
                    x0 + i * (x1 - x0) / max(1, count - 1),
                    mid - max(-1.0, min(1.0, float(clean[sample_idx]))) * scale,
                )
                for i, sample_idx in enumerate(idx)
            ])
            painter.drawPolyline(points)
            return

        peaks = compute_peaks(clean, width)
        if not peaks:
            return
        top: list[QPointF] = []
        bot: list[QPointF] = []
        step = (x1 - x0) / max(1, len(peaks) - 1)
        for i, (lo, hi) in enumerate(peaks):
            x = x0 + i * step
            lo_c = max(-1.0, min(1.0, float(lo)))
            hi_c = max(-1.0, min(1.0, float(hi)))
            top.append(QPointF(x, mid - hi_c * scale))
            bot.append(QPointF(x, mid - lo_c * scale))
        poly = QPolygonF(top + bot[::-1])
        if brush_color is None:
            painter.drawPolyline(QPolygonF(top))
            painter.drawPolyline(QPolygonF(bot))
        else:
            painter.setBrush(brush_color)
            painter.drawPolygon(poly)

    def _peaks_for_interval(
        self,
        peaks: list[tuple[float, float]],
        source_start: float,
        source_end: float,
        interval_start: float,
        interval_end: float,
    ) -> list[tuple[float, float]]:
        if not peaks or source_end <= source_start or interval_end <= interval_start:
            return []
        a = max(source_start, interval_start)
        b = min(source_end, interval_end)
        if b <= a:
            return []
        start_ratio = (a - source_start) / (source_end - source_start)
        end_ratio = (b - source_start) / (source_end - source_start)
        i0 = max(0, min(len(peaks), int(np.floor(start_ratio * len(peaks)))))
        i1 = max(i0 + 1, min(len(peaks), int(np.ceil(end_ratio * len(peaks)))))
        return peaks[i0:i1]

    def _rendered_preview_interval(self) -> tuple[float, float]:
        source_start, source_end = self._rendered_source_region
        view_start, view_end = self.view
        return max(view_start, source_start), min(view_end, source_end)

    def _draw_peak_waveform(
        self,
        painter: QPainter,
        peaks: list[tuple[float, float]],
        x0: float,
        x1: float,
        mid: float,
        scale: float,
        pen_color: QColor,
        brush_color: QColor | None,
    ) -> None:
        if not peaks or x1 <= x0:
            return
        painter.setPen(QPen(pen_color, 1))
        top: list[QPointF] = []
        bot: list[QPointF] = []
        step = (x1 - x0) / max(1, len(peaks) - 1)
        for i, (lo, hi) in enumerate(peaks):
            x = x0 + i * step
            lo_c = max(-1.0, min(1.0, float(lo)))
            hi_c = max(-1.0, min(1.0, float(hi)))
            top.append(QPointF(x, mid - hi_c * scale))
            bot.append(QPointF(x, mid - lo_c * scale))
        if brush_color is None:
            painter.drawPolyline(QPolygonF(top))
            painter.drawPolyline(QPolygonF(bot))
        else:
            painter.setBrush(brush_color)
            painter.drawPolygon(QPolygonF(top + bot[::-1]))

    def _zoom_at(self, factor: float, x: float) -> None:
        if self.duration <= 0:
            return
        factor = max(0.1, min(10.0, factor))
        view_start, view_end = self.view
        span = view_end - view_start
        min_span = min(self.duration, _MIN_VIEW_SEC)
        new_span = max(min_span, min(self.duration, span / factor))
        anchor = self._x_to_time(x)
        ratio = 0.5 if self.width() <= 0 else max(0.0, min(1.0, x / self.width()))
        new_start = anchor - new_span * ratio
        self._set_view(new_start, new_span)

    def _pan_to(self, x: float) -> None:
        if self.duration <= 0 or self.width() <= 0:
            return
        view_start, view_end = self._pan_press_view
        span = view_end - view_start
        dx = x - self._pan_press_x
        self._set_view(view_start - dx * span * _PAN_SPEED / self.width(), span)

    def _pan_by_pixels(self, dx: float) -> None:
        if self.duration <= 0 or self.width() <= 0:
            return
        view_start, view_end = self.view
        span = view_end - view_start
        if span >= self.duration:
            return
        self._set_view(view_start + dx * span * _PAN_SPEED / self.width(), span)

    # --- mouse interaction ---

    def mousePressEvent(self, event) -> None:
        if self.duration <= 0:
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_press_x = event.position().x()
            self._pan_press_view = self.view
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_handle = self._pick_handle(int(event.position().x()))
        self._drag_handle_changed = False
        self._press_pos = event.position()

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            self._pan_to(event.position().x())
            event.accept()
            return
        if self._drag_handle is None:
            moved = (
                self._press_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()
            )
            if moved:
                self._press_pos = None
                self.drag_started.emit()
                event.accept()
            return
        t = self._x_to_time(event.position().x())
        start, end = self.region
        if self._drag_handle == "start":
            start, end = clamp_region(t, end, self.duration)
            self.fade_in = min(self.fade_in, end - start)
        elif self._drag_handle == "end":
            start, end = clamp_region(start, t, self.duration)
            self.fade_out = min(self.fade_out, end - start)
        elif self._drag_handle == "fade_in":
            self.fade_in = max(0.0, min(t - start, end - start))
        elif self._drag_handle == "fade_out":
            self.fade_out = max(0.0, min(end - t, end - start))
        self.region = (start, end)
        self._drag_handle_changed = True
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        changed = self._drag_handle_changed
        self._drag_handle = None
        self._drag_handle_changed = False
        self._press_pos = None
        if changed:
            self.edit_changed.emit()

    def wheelEvent(self, event) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            pixel = event.pixelDelta()
            angle = event.angleDelta()
            dx = pixel.x() or angle.x() / 8.0
            if not dx:
                dx = -(pixel.y() or angle.y() / 8.0)
            if dx:
                self._pan_by_pixels(dx)
                event.accept()
                return
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            return
        self._zoom_at(1.25 if delta > 0 else 0.8, event.position().x())
        event.accept()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                change = pinch.scaleFactor()
                if change and change != 1.0:
                    self._zoom_at(change, self.width() / 2)
                return True
        return super().event(event)

    def nativeGestureEvent(self, event) -> None:
        if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self._zoom_at(1.0 + event.value(), event.position().x())
            event.accept()
            return
        super().nativeGestureEvent(event)

    # --- painting ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        mid = h / 2.0
        painter.fillRect(0, 0, w, h, QColor("#10141d"))

        if self._mono is None or self._mono.size == 0:
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.drawLine(0, int(mid), w, int(mid))
            painter.end()
            return

        hx = self._handle_x()
        region_start_x, region_end_x = self._region_view_x()
        fade_in_x = self._time_to_view_x(self.region[0] + self.fade_in)
        fade_out_x = self._time_to_view_x(self.region[1] - self.fade_out)
        # Shade the region.
        region_color = QColor(255, 122, 182, 70) if self.loop_enabled else QColor(34, 42, 58, 150)
        region_edge = QColor(PINK) if self.loop_enabled else QColor(ACCENT)
        painter.fillRect(QRectF(region_start_x, 0, region_end_x - region_start_x, h), region_color)

        # Waveform envelope.
        scale = mid * 0.95
        view_start, view_end = self.view
        source_color = QColor(ACCENT_2)
        if self._rendered_peaks:
            rendered_start, rendered_end = self._rendered_source_region
            intervals = [
                (view_start, min(view_end, rendered_start)),
                (max(view_start, rendered_end), view_end),
            ]
        else:
            intervals = [(view_start, view_end)]
        for a, b in intervals:
            if b <= a:
                continue
            samples = self._samples_for_interval(self._mono, 0.0, self.duration, a, b)
            self._draw_waveform(
                painter,
                samples,
                self._time_to_view_x(a),
                self._time_to_view_x(b),
                mid,
                scale,
                source_color,
                source_color,
            )

        # Rendered edit preview remains anchored to the region that produced it
        # until the next debounced live render replaces it.
        if self._rendered_peaks:
            source_start, source_end = self._rendered_source_region
            a, b = self._rendered_preview_interval()
            peaks = self._peaks_for_interval(self._rendered_peaks, source_start, source_end, a, b)
            self._draw_peak_waveform(
                painter,
                peaks,
                self._time_to_view_x(a),
                self._time_to_view_x(b),
                mid,
                scale,
                QColor(255, 190, 85),
                QColor(255, 180, 70, 145),
            )

        if self.adsr is not None and self.adsr.active and region_end_x > region_start_x:
            points = self._adsr_points(region_start_x, region_end_x, h)
            if len(points) > 1:
                painter.setPen(QPen(QColor(255, 230, 120), 2))
                painter.drawPolyline(QPolygonF(points))

        # Fade ramps (region edges → fade handle, at the top).
        painter.setPen(QPen(QColor(230, 200, 80), 1))
        painter.drawLine(QPointF(region_start_x, h), QPointF(fade_in_x, 0))
        painter.drawLine(QPointF(region_end_x, h), QPointF(fade_out_x, 0))

        # Region handles.
        painter.setPen(QPen(region_edge, 2))
        painter.drawLine(hx["start"], 0, hx["start"], h)
        painter.drawLine(hx["end"], 0, hx["end"], h)
        if self.loop_enabled:
            painter.setPen(QPen(QColor(255, 195, 225), 1))
            label = "Loop Region"
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(label)
            tx = max(4, min(w - tw - 4, region_end_x - tw - 6))
            ty = max(metrics.ascent() + 4, min(h - 4, metrics.ascent() + 8))
            painter.drawText(tx, ty, label)

        if self.playhead_time is not None:
            view_start, view_end = self.view
            if view_start <= self.playhead_time <= view_end:
                x = self._time_to_x(self.playhead_time)
                painter.setPen(QPen(QColor(70, 210, 255), 2))
                painter.drawLine(x, 0, x, h)

        if self._show_transients and self._transients:
            view_start, view_end = self.view
            painter.setPen(QPen(QColor(120, 200, 255, 140), 1))
            for t in self._transients:
                if view_start <= t <= view_end:
                    x = self._time_to_x(t)
                    painter.drawLine(x, 0, x, h)

        painter.end()

    def _adsr_points(self, start_x: float, end_x: float, height: int) -> list[QPointF]:
        if self.adsr is None or end_x <= start_x:
            return []
        width = max(1, end_x - start_x)
        start, end = self.region
        region_len = max(0.001, end - start)
        attack = max(0.0, min(region_len, self.adsr.attack))
        release = max(0.0, min(region_len - attack, self.adsr.release))
        decay = max(0.0, min(region_len - attack - release, self.adsr.decay))

        def px(seconds: float) -> float:
            return start_x + width * max(0.0, min(1.0, seconds / region_len))

        def py(level: float) -> float:
            return height - max(0.0, min(1.0, level)) * height

        points = [QPointF(start_x, py(0.0))]
        points.append(QPointF(px(attack), py(1.0 if attack > 0 else self.adsr.sustain)))
        if decay > 0:
            points.append(QPointF(px(attack + decay), py(self.adsr.sustain)))
        sustain_end = max(attack + decay, region_len - release)
        points.append(QPointF(px(sustain_end), py(self.adsr.sustain)))
        if release > 0:
            points.append(QPointF(end_x, py(0.0)))
        return points


class _KnobDial(QDial):
    """QDial with the native click-to-angle jump removed.

    Overriding the mouse handlers directly (instead of an event filter) is the
    only reliable way to suppress the jump: the base angle-setting code path is
    never entered, and a double-click is never re-sent as a press. Left-press
    starts a relative vertical drag (~150px = full range); double-click emits
    ``doubleClicked`` so the owner can reset to its default.
    """

    doubleClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_y: float | None = None
        self._press_value = 0

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        side = min(self.width(), self.height())
        rect = QRectF(
            (self.width() - side) / 2 + 4,
            (self.height() - side) / 2 + 4,
            side - 8,
            side - 8,
        )
        center = rect.center()
        radius = rect.width() / 2
        ratio = 0.0 if self.maximum() <= self.minimum() else (
            (self.value() - self.minimum()) / (self.maximum() - self.minimum())
        )

        painter.setPen(QPen(QColor("#0a0d13"), 1))
        painter.setBrush(QColor("#0c1018"))
        painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))

        painter.setPen(QPen(QColor("#2b3548"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        painter.setPen(QPen(QColor("#67d5ff"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 225 * 16, int(-270 * ratio * 16))

        angle = radians(225 - 270 * ratio)
        line_inner = radius * 0.26
        line_outer = radius * 0.78
        p1 = center + QPointF(cos(angle) * line_inner, -sin(angle) * line_inner)
        p2 = center + QPointF(cos(angle) * line_outer, -sin(angle) * line_outer)
        painter.setPen(QPen(QColor("#e8edf7"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p1, p2)

        painter.setPen(QPen(QColor("#293449"), 1))
        painter.setBrush(QColor("#151b26"))
        painter.drawEllipse(QRectF(center.x() - 4, center.y() - 4, 8, 8))

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_y = event.position().y()
            self._press_value = self.value()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self._press_y is not None:
            dy = self._press_y - event.position().y()
            steps = int(round(dy / 150.0 * self.maximum()))
            self.setValue(self._press_value + steps)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self._press_y is not None:
            self._press_y = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._press_y = None
        self.doubleClicked.emit()
        event.accept()


class _Knob(QWidget):
    """Small bounded rotary control for Simpler gain/ADSR parameters."""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        lo: float,
        hi: float,
        step: float,
        val: float,
        suffix: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._suffix = suffix
        self._dial = _KnobDial()
        self._dial.setRange(0, int(round((hi - lo) / step)))
        self._dial.setNotchesVisible(False)
        self._dial.setWrapping(False)
        self._dial.setFixedSize(38, 38)
        self._dial.valueChanged.connect(self._on_dial_changed)
        self._dial.doubleClicked.connect(self._reset_to_default)
        self._default = val

        self._value_label = QLabel()
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setFixedWidth(62)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QLabel(label)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 10px; color: #97a1b3; font-weight: 700;")
        self._value_label.setStyleSheet("font-size: 10px; color: #dce7f7;")
        layout.addWidget(title)
        layout.addWidget(self._dial, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value_label)

        self._lo = lo
        self._hi = hi
        self._step = step
        self.setValue(val)

    def value(self) -> float:
        return self._lo + self._dial.value() * self._step

    def setValue(self, value: float) -> None:
        value = max(self._lo, min(self._hi, value))
        self._dial.setValue(int(round((value - self._lo) / self._step)))
        self._sync_label()

    def _reset_to_default(self) -> None:
        self.setValue(self._default)

    def _on_dial_changed(self, _value: int) -> None:
        self._sync_label()
        self.valueChanged.emit(self.value())

    def _sync_label(self) -> None:
        self._value_label.setText(f"{self.value():.2f}{self._suffix}")


class SimplerPane(QWidget):
    """Preview + editor pane. Emits preview/export requests; drags rendered WAVs."""

    preview_requested = Signal(object)  # params dict
    preview_stop_requested = Signal()
    preview_params_changed = Signal(object)  # params dict
    export_requested = Signal(object)   # params dict
    exported = Signal(str)              # path of a drag-exported WAV (for indexing)
    render_stage_requested = Signal(int, str, object)  # (seq, path, params) — drag pre-render

    def __init__(self, saved_dir: Path | str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._saved_dir = Path(saved_dir)
        self._path: str | None = None
        self._preview_playing = False
        self._slices: list[tuple[float, float]] = []
        self._slice_idx = 0
        self._staged_render_path: str | None = None
        self._stage_seq = 0
        self._staged_key: tuple | None = None
        self._stage_timer = QTimer(self)
        self._stage_timer.setSingleShot(True)
        self._stage_timer.setInterval(250)
        self._stage_timer.timeout.connect(self.request_stage_render)
        self._live_render_timer = QTimer(self)
        self._live_render_timer.setSingleShot(True)
        self._live_render_timer.setInterval(35)
        self._live_render_timer.timeout.connect(self._sync_live_render)

        self._canvas = _WaveCanvas()
        self._canvas.drag_started.connect(self._start_drag)
        self._canvas.edit_changed.connect(self._on_canvas_edit_changed)

        self._reverse = QPushButton("Reverse")
        self._reverse.setCheckable(True)
        self._loop = QPushButton("Loop")
        self._loop.setCheckable(True)
        self._gain = self._spin(-24.0, 24.0, 0.5, 0.0, " dB", "Gain")
        self._attack = self._spin(0.0, 5.0, 0.01, 0.0, " s", "A")
        self._decay = self._spin(0.0, 5.0, 0.01, 0.0, " s", "D")
        self._sustain = self._spin(0.0, 1.0, 0.05, 1.0, "", "S")
        self._release = self._spin(0.0, 5.0, 0.01, 0.0, " s", "R")
        self._sensitivity = self._spin(0.0, 1.0, 0.05, 0.5, "", "Sens")
        self._markers_cb = QCheckBox("Markers")
        self._markers_cb.setChecked(True)
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setIcon(icon("refresh"))
        self._normalize_btn = QPushButton("Normalize")
        self._trim_btn = QPushButton("Trim")
        self._snap_btn = QPushButton("Snap")
        self._slice_btn = QPushButton("Slice")
        self._normalize_btn.setIcon(icon("analyze"))
        self._trim_btn.setIcon(icon("delete"))
        self._snap_btn.setIcon(icon("favorite"))
        self._slice_btn.setIcon(icon("duplicates"))
        for button in (self._reset_btn, self._normalize_btn, self._trim_btn, self._snap_btn, self._slice_btn):
            button.setMaximumHeight(24)
        for toggle in (self._reverse, self._loop):
            toggle.setMinimumWidth(82)
            toggle.setMinimumHeight(30)
            toggle.setMaximumHeight(30)
        self._reverse.toggled.connect(self._on_preview_control_changed)
        self._loop.toggled.connect(self._on_loop_toggled)
        for knob in (self._gain, self._attack, self._decay, self._sustain, self._release):
            knob.valueChanged.connect(self._on_preview_control_changed)
        self._sensitivity.valueChanged.connect(self._recompute_transients)
        self._markers_cb.toggled.connect(self._canvas.set_show_transients)
        self._reset_btn.clicked.connect(self._reset_editor)
        self._normalize_btn.clicked.connect(self._on_normalize)
        self._trim_btn.clicked.connect(self._on_trim)
        self._snap_btn.clicked.connect(self._on_snap)
        self._slice_btn.clicked.connect(self._on_slice)

        preview_btn = QPushButton("Preview edit")
        preview_btn.setIcon(icon("play"))
        preview_btn.setProperty("primary", True)
        preview_btn.clicked.connect(self.trigger_preview)
        self._preview_btn = preview_btn
        self._preview_state = QLabel("Stopped")
        self._preview_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_state.setMinimumWidth(50)
        export_btn = QPushButton("Export → Saved")
        export_btn.setIcon(icon("export"))
        export_btn.clicked.connect(lambda: self.export_requested.emit(self.current_params()))
        preview_btn.setMaximumHeight(24)
        export_btn.setMaximumHeight(24)
        self._preview_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._preview_shortcut.activated.connect(self.trigger_preview)

        edit_row = QHBoxLayout()
        edit_row.setContentsMargins(2, 2, 2, 0)
        edit_row.setSpacing(4)
        edit_row.addWidget(self._reverse)
        edit_row.addWidget(self._loop)
        edit_row.addWidget(self._gain)
        edit_row.addWidget(self._attack)
        edit_row.addWidget(self._decay)
        edit_row.addWidget(self._sustain)
        edit_row.addWidget(self._release)
        edit_row.addWidget(self._sensitivity)
        edit_row.addWidget(self._reset_btn)
        edit_row.addStretch()

        action_row = QHBoxLayout()
        action_row.setContentsMargins(2, 0, 2, 2)
        action_row.setSpacing(4)
        action_row.addWidget(self._markers_cb)
        action_row.addWidget(self._normalize_btn)
        action_row.addWidget(self._trim_btn)
        action_row.addWidget(self._snap_btn)
        action_row.addWidget(self._slice_btn)
        action_row.addStretch()
        action_row.addWidget(self._preview_state)
        action_row.addWidget(preview_btn)
        action_row.addWidget(export_btn)

        layout = QVBoxLayout(self)
        self.setObjectName("Panel")
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas, stretch=1)
        layout.addLayout(edit_row)
        layout.addLayout(action_row)
        self.set_preview_playing(False)

    @staticmethod
    def _spin(lo: float, hi: float, step: float, val: float, suffix: str, label: str = "") -> _Knob:
        return _Knob(label, lo, hi, step, val, suffix)

    # --- public API used by MainWindow ---

    def set_sample(self, path: str, duration: float | None) -> None:
        self._path = path
        self._slices = []
        self._slice_idx = 0
        self._canvas.set_mono(None)
        self._staged_render_path = None
        self._staged_key = None
        self._canvas.set_sample(duration or 0.0)
        self._sync_live_render()
        self._recompute_transients()

    def set_mono(self, mono: np.ndarray | None) -> None:
        self._canvas.set_mono(mono)
        self._sync_live_render()
        self._recompute_transients()
        self._slice_idx = 0

    def set_preview_playing(self, playing: bool) -> None:
        self._preview_playing = playing
        self._preview_btn.setText("Stop preview" if playing else "Preview edit")
        self._preview_state.setText("Playing" if playing else "Stopped")
        color = "#38c172" if playing else "#9a9a9a"
        self._preview_state.setStyleSheet(f"color: {color}; font-weight: 600;")
        if not playing:
            self.set_preview_playhead(None)

    def set_preview_playhead(self, seconds: float | None) -> None:
        self._canvas.set_playhead(seconds)

    def current_params(self) -> dict:
        a, d, s, r = (
            self._attack.value(), self._decay.value(),
            self._sustain.value(), self._release.value(),
        )
        adsr = (a, d, s, r) if (a or d or r or s != 1.0) else None
        return {
            "path": self._path,
            "region": self._canvas.region if self._canvas.duration > 0 else None,
            "reverse": self._reverse.isChecked(),
            "loop": self._loop.isChecked(),
            "gain_db": self._gain.value(),
            "fade_in": self._canvas.fade_in,
            "fade_out": self._canvas.fade_out,
            "adsr": adsr,
        }

    def _current_adsr(self) -> ADSR | None:
        values = (
            self._attack.value(),
            self._decay.value(),
            self._sustain.value(),
            self._release.value(),
        )
        adsr = ADSR(*values)
        return adsr if adsr.active else None

    def _on_loop_toggled(self, checked: bool) -> None:
        self._canvas.set_loop_enabled(checked)
        self._sync_live_render()
        self._restart_preview_if_playing()

    def _reset_editor(self) -> None:
        self._reverse.setChecked(False)
        self._loop.setChecked(False)
        for knob in (self._gain, self._attack, self._decay, self._sustain, self._release, self._sensitivity):
            knob._reset_to_default()
        self._canvas.fade_in = 0.0
        self._canvas.fade_out = 0.0
        self._canvas.region = (0.0, self._canvas.duration)
        self._canvas.update()
        self._sync_live_render()
        self._restart_preview_if_playing()

    def _on_preview_control_changed(self, *_args) -> None:
        self._sync_live_render()
        self._restart_preview_if_playing()

    def _on_canvas_edit_changed(self) -> None:
        self._schedule_live_render()
        self._restart_preview_if_playing()

    def _restart_preview_if_playing(self) -> None:
        if self._preview_playing:
            self.preview_params_changed.emit(self.current_params())

    def _schedule_live_render(self) -> None:
        self._live_render_timer.start()

    def _sync_live_render(self, *_args) -> None:
        adsr = self._current_adsr()
        self._canvas.set_adsr(adsr)
        self._canvas.set_loop_enabled(self._loop.isChecked())
        mono = self._canvas._mono
        if mono is None or mono.size == 0 or self._canvas.duration <= 0:
            self._canvas.set_rendered_mono(None)
            return
        start, end = self._canvas.region
        region_len = max(0.001, end - start)
        if self._canvas.duration > 0 and end > start:
            i0 = max(0, min(mono.size, int(round(start / self._canvas.duration * mono.size))))
            i1 = max(i0 + 1, min(mono.size, int(round(end / self._canvas.duration * mono.size))))
            visual_mono = mono[i0:i1]
        else:
            visual_mono = mono
        if visual_mono.size > _LIVE_RENDER_MAX_SAMPLES:
            step = int(np.ceil(visual_mono.size / _LIVE_RENDER_MAX_SAMPLES))
            visual_mono = visual_mono[::step]
        sr = max(1, int(round(visual_mono.size / region_len)))
        try:
            rendered = apply_edit(
                visual_mono,
                sr,
                None,
                reverse=self._reverse.isChecked(),
                gain_db=self._gain.value(),
                fade_in=self._canvas.fade_in,
                fade_out=self._canvas.fade_out,
                adsr=adsr,
            )
        except Exception:  # noqa: BLE001 — visual preview should never break editing
            self._canvas.set_rendered_mono(None)
            return
        self._canvas.set_rendered_mono(rendered)
        # params changed → invalidate the staged drag render and pre-render a fresh
        # one on the worker thread; drag falls back to a synchronous render until ready.
        self._schedule_stage_render()

    @staticmethod
    def _params_key(p: dict) -> tuple:
        return (
            p["path"], p["region"], p["reverse"], p["gain_db"],
            p["fade_in"], p["fade_out"], p["adsr"],
        )

    def request_stage_render(self) -> None:
        """Ask the worker to pre-render the current edit for a future drag-export."""
        params = self.current_params()
        if not params.get("path"):
            return
        self._stage_seq += 1
        self._staged_render_path = None
        self._staged_key = self._params_key(params)
        self.render_stage_requested.emit(self._stage_seq, params["path"], params)

    def _schedule_stage_render(self) -> None:
        self._stage_timer.start()

    def set_staged_render_path(self, seq: int, path: str) -> None:
        """Worker callback: store the pre-rendered drag file if still current."""
        if seq == self._stage_seq:
            self._staged_render_path = path

    def _consume_staged(self) -> Path | None:
        """Return a Saved-dir copy of the staged render iff it matches current params."""
        staged = self._staged_render_path
        if not staged:
            return None
        sp = Path(staged)
        if not sp.exists():
            return None
        if self._staged_key != self._params_key(self.current_params()):
            return None
        import shutil
        dest = dated_export_dir(self._saved_dir) / default_export_name(self._path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sp, dest)
        return dest

    def _drag_display_name(self) -> str:
        """Human-facing filename for external drag targets; content is always WAV."""
        stem = Path(self._path or "sample").stem
        stem = _EDIT_SUFFIX_RE.sub("", stem) or stem
        return f"{stem}.wav"

    def _drag_payload_path(self, service_path: Path) -> Path:
        """Copy the service export to a temp path with the original-facing name."""
        import shutil
        import tempfile
        import uuid

        drag_dir = Path(tempfile.gettempdir()) / "cratedig_drag" / uuid.uuid4().hex
        drag_dir.mkdir(parents=True, exist_ok=True)
        drag_path = drag_dir / self._drag_display_name()
        shutil.copyfile(service_path, drag_path)
        return drag_path

    def _mono_sr(self) -> tuple[np.ndarray | None, int]:
        mono = self._canvas._mono
        if mono is None or mono.size == 0 or self._canvas.duration <= 0:
            return None, 0
        sr = max(1, int(round(mono.size / self._canvas.duration)))
        return mono, sr

    def _recompute_transients(self, *args) -> None:
        mono, sr = self._mono_sr()
        if mono is None:
            self._canvas.set_transients([])
            return
        try:
            times = detect_transients(mono, sr, sensitivity=self._sensitivity.value())
        except Exception:
            times = []
        self._canvas.set_transients(times)

    def _on_normalize(self) -> None:
        mono, sr = self._mono_sr()
        if mono is None:
            return
        start, end = self._canvas.region
        duration = self._canvas.duration
        if duration > 0 and end > start:
            i0 = int(round(start / duration * mono.size))
            i1 = int(round(end / duration * mono.size))
            region_samples = mono[i0:i1]
        else:
            region_samples = mono
        if region_samples.size == 0:
            region_samples = mono
        peak = float(np.max(np.abs(region_samples)))
        if peak < 1e-9:
            return
        target_linear = 10 ** (-0.3 / 20)
        gain_db = 20 * log10(target_linear / peak)
        self._gain.setValue(gain_db)  # _Knob.setValue clamps to its own range

    def _on_trim(self) -> None:
        mono, sr = self._mono_sr()
        if mono is None:
            return
        _, start_sec, end_sec = trim_silence(mono, sr)
        if end_sec > start_sec:
            self._canvas.region = clamp_region(start_sec, end_sec, self._canvas.duration)
            self._sync_live_render()
            self._canvas.update()
            self._restart_preview_if_playing()

    def _on_snap(self) -> None:
        mono, sr = self._mono_sr()
        if mono is None:
            return
        s, e = self._canvas.region
        ns = snap_to_zero_crossing(mono, sr, s)
        ne = snap_to_zero_crossing(mono, sr, e)
        self._canvas.region = clamp_region(ns, ne, self._canvas.duration)
        self._sync_live_render()
        self._canvas.update()
        self._restart_preview_if_playing()

    def _on_slice(self) -> None:
        mono, sr = self._mono_sr()
        if mono is None:
            return
        self._slices = auto_slice(mono, sr, sensitivity=self._sensitivity.value())
        if not self._slices:
            return
        idx = self._slice_idx % len(self._slices)
        start, end = self._slices[idx]
        self._slice_idx = (self._slice_idx + 1) % len(self._slices)
        self._canvas.region = clamp_region(start, end, self._canvas.duration)
        self._sync_live_render()
        self._canvas.update()
        self._restart_preview_if_playing()

    def trigger_preview(self) -> None:
        if self._preview_playing:
            self.preview_stop_requested.emit()
            return
        self.preview_requested.emit(self.current_params())

    # --- drag export ---

    def _start_drag(self) -> None:
        if not self._path:
            return
        dest = self._consume_staged()
        if dest is None:
            try:
                dest = self._render_to_saved()
            except Exception:  # noqa: BLE001 — drag-export is best-effort
                return
        try:
            drag_path = self._drag_payload_path(dest).resolve()
        except OSError:
            drag_path = dest.resolve()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(drag_path))])
        mime.setText(str(drag_path))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
        # Keep the rendered file regardless of the returned action. Several
        # external Windows targets report IgnoreAction even when they consume the
        # file URL, and some read the file after QDrag.exec returns.
        self.exported.emit(str(dest.resolve()))

    def _render_to_saved(self) -> Path:
        p = self.current_params()
        adsr = ADSR(*p["adsr"]) if p["adsr"] else None
        edited, sr = render_edit(
            self._path,
            p["region"],
            reverse=p["reverse"],
            gain_db=p["gain_db"],
            fade_in=p["fade_in"],
            fade_out=p["fade_out"],
            adsr=adsr,
        )
        dest = dated_export_dir(self._saved_dir) / default_export_name(self._path)
        return write_wav(edited, sr, dest)

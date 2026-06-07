"""Simpler: combined preview + editor pane (replaces the waveform pane).

Draws the selected sample's waveform with draggable region and fade handles,
plus reverse / gain / ADSR controls. Edits are rendered through the pure
``audio.editor`` core; preview and export are routed out via signals, and the
waveform itself is a drag source that renders to the Saved folder on drag-start.
"""

from __future__ import annotations

from math import log10
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QMimeData, QPointF, QRectF, Qt, QUrl, Signal
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

_HANDLE_GRAB_PX = 8
_MIN_VIEW_SEC = 0.02
_PAN_SPEED = 4.0


class _WaveCanvas(QWidget):
    """Waveform with draggable region (start/end) and fade (in/out) handles."""

    edit_changed = Signal()
    drag_started = Signal()  # ask the parent to render+persist and start the QDrag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mono: np.ndarray | None = None
        self._peaks: list[tuple[float, float]] = []
        self._rendered_mono: np.ndarray | None = None
        self._rendered_peaks: list[tuple[float, float]] = []
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
        self._press_pos = None
        self._panning = False
        self._pan_press_x = 0.0
        self._pan_press_view: tuple[float, float] = (0.0, 0.0)
        self.setMinimumHeight(120)
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
        self._recompute()
        self.update()

    def set_rendered_mono(self, mono: np.ndarray | None) -> None:
        self._rendered_mono = None if mono is None else np.asarray(mono, dtype=np.float32)
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
        self._recompute()
        self._recompute_rendered()
        self.update()

    def _recompute(self) -> None:
        if self._mono is None or self._mono.size == 0 or self.width() <= 0:
            self._peaks = []
            return
        start, end = self.view
        if self.duration > 0 and end > start:
            n0 = int(max(0.0, start / self.duration) * self._mono.size)
            n1 = int(min(1.0, end / self.duration) * self._mono.size)
            visible = self._mono[n0:max(n0 + 1, n1)]
        else:
            visible = self._mono
        self._peaks = compute_peaks(visible, self.width())

    def _set_view(self, start: float, span: float) -> None:
        if self.duration <= 0:
            return
        span = max(min(self.duration, _MIN_VIEW_SEC), min(self.duration, span))
        start = max(0.0, min(start, self.duration - span))
        self.view = (start, start + span)
        self._recompute()
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

    def _region_peak_width(self) -> int:
        start_x, end_x = self._region_view_x()
        if self.width() <= 0:
            return 0
        # Cache the rendered edit at the region's current on-screen scale. This
        # keeps the preview smooth when zoomed in, while avoiding runaway bins.
        return min(16384, max(self.width(), int(np.ceil(abs(end_x - start_x)))))

    def _recompute_rendered(self) -> None:
        if self._rendered_mono is None or self._rendered_mono.size == 0:
            self._rendered_peaks = []
            return
        width = self._region_peak_width()
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
        self.edit_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_handle = None
        self._press_pos = None

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
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))

        if not self._peaks:
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawLine(0, int(mid), w, int(mid))
            painter.end()
            return

        hx = self._handle_x()
        region_start_x, region_end_x = self._region_view_x()
        fade_in_x = self._time_to_view_x(self.region[0] + self.fade_in)
        fade_out_x = self._time_to_view_x(self.region[1] - self.fade_out)
        # Shade the region.
        region_color = QColor(170, 70, 125, 76) if self.loop_enabled else QColor(60, 60, 90)
        region_edge = QColor(245, 130, 185) if self.loop_enabled else QColor(220, 220, 220)
        painter.fillRect(QRectF(region_start_x, 0, region_end_x - region_start_x, h), region_color)

        # Waveform envelope.
        scale = mid * 0.95
        view_start, view_end = self.view
        source_color = QColor(80, 160, 80)
        if self._rendered_peaks and region_end_x > region_start_x:
            intervals = [
                (view_start, min(view_end, self.region[0])),
                (max(view_start, self.region[1]), view_end),
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

        # Rendered edit preview inside the selected region.
        if self._rendered_mono is not None and self._rendered_mono.size and region_end_x > region_start_x:
            a = max(view_start, self.region[0])
            b = min(view_end, self.region[1])
            samples = self._samples_for_interval(self._rendered_mono, self.region[0], self.region[1], a, b)
            self._draw_waveform(
                painter,
                samples,
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
        self._drag_y: float | None = None
        self._drag_value = 0.0

        self._dial = QDial()
        self._dial.setRange(0, int(round((hi - lo) / step)))
        self._dial.setNotchesVisible(False)
        self._dial.setWrapping(False)
        self._dial.setFixedSize(38, 38)
        self._dial.valueChanged.connect(self._on_dial_changed)

        self._value_label = QLabel()
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setFixedWidth(64)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QLabel(label)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def _on_dial_changed(self, _value: int) -> None:
        self._sync_label()
        self.valueChanged.emit(self.value())

    def _sync_label(self) -> None:
        self._value_label.setText(f"{self.value():.2f}{self._suffix}")


class SimplerPane(QWidget):
    """Preview + editor pane. Emits preview/export requests; drags rendered WAVs."""

    preview_requested = Signal(object)  # params dict
    preview_stop_requested = Signal()
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

        self._canvas = _WaveCanvas()
        self._canvas.drag_started.connect(self._start_drag)
        self._canvas.edit_changed.connect(self._sync_live_render)

        self._reverse = QCheckBox("Reverse")
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
        self._normalize_btn = QPushButton("Normalize")
        self._trim_btn = QPushButton("Trim")
        self._snap_btn = QPushButton("Snap")
        self._slice_btn = QPushButton("Slice")
        self._reverse.stateChanged.connect(self._sync_live_render)
        self._loop.toggled.connect(self._on_loop_toggled)
        for knob in (self._gain, self._attack, self._decay, self._sustain, self._release):
            knob.valueChanged.connect(self._sync_live_render)
        self._sensitivity.valueChanged.connect(self._recompute_transients)
        self._markers_cb.toggled.connect(self._canvas.set_show_transients)
        self._normalize_btn.clicked.connect(self._on_normalize)
        self._trim_btn.clicked.connect(self._on_trim)
        self._snap_btn.clicked.connect(self._on_snap)
        self._slice_btn.clicked.connect(self._on_slice)

        preview_btn = QPushButton("Preview edit")
        preview_btn.clicked.connect(self.trigger_preview)
        self._preview_btn = preview_btn
        self._preview_state = QLabel("Stopped")
        self._preview_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_state.setMinimumWidth(64)
        export_btn = QPushButton("Export → Saved")
        export_btn.clicked.connect(lambda: self.export_requested.emit(self.current_params()))
        self._preview_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._preview_shortcut.activated.connect(self.trigger_preview)

        controls = QHBoxLayout()
        controls.setContentsMargins(2, 2, 2, 2)
        controls.addWidget(self._reverse)
        controls.addWidget(self._loop)
        controls.addWidget(self._gain)
        controls.addWidget(self._attack)
        controls.addWidget(self._decay)
        controls.addWidget(self._sustain)
        controls.addWidget(self._release)
        controls.addWidget(self._sensitivity)
        controls.addWidget(self._markers_cb)
        controls.addWidget(self._normalize_btn)
        controls.addWidget(self._trim_btn)
        controls.addWidget(self._snap_btn)
        controls.addWidget(self._slice_btn)
        controls.addStretch()
        controls.addWidget(self._preview_state)
        controls.addWidget(preview_btn)
        controls.addWidget(export_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas, stretch=1)
        layout.addLayout(controls)
        self.set_preview_playing(False)

    @staticmethod
    def _spin(lo: float, hi: float, step: float, val: float, suffix: str, label: str = "") -> _Knob:
        return _Knob(label, lo, hi, step, val, suffix)

    # --- public API used by MainWindow ---

    def set_sample(self, path: str, duration: float | None) -> None:
        self._path = path
        self._slices = []
        self._slice_idx = 0
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

    def _sync_live_render(self, *_args) -> None:
        adsr = self._current_adsr()
        self._canvas.set_adsr(adsr)
        self._canvas.set_loop_enabled(self._loop.isChecked())
        mono = self._canvas._mono
        if mono is None or mono.size == 0 or self._canvas.duration <= 0:
            self._canvas.set_rendered_mono(None)
            return
        sr = max(1, int(round(mono.size / self._canvas.duration)))
        try:
            rendered = apply_edit(
                mono,
                sr,
                self._canvas.region,
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
        self.request_stage_render()

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
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(dest))])
        drag = QDrag(self)
        drag.setMimeData(mime)
        action = drag.exec(Qt.DropAction.CopyAction)
        # Only a copy drop counts as an export; cancel/ignore (or any non-copy
        # action) drops the rendered orphan so the Saved folder stays clean.
        if action == Qt.DropAction.CopyAction:
            self.exported.emit(str(dest))
        else:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass

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

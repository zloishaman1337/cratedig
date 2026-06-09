"""A/B compare modal: pick two samples from the library tree and audition them.

Midnight-commander style — each side starts as a folder-tree picker; once a
sample is chosen the side shows its filename + waveform. Shared A/B toggle and
Reset below; per-slot Remove and Add-to-crate buttons.
"""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import QMetaObject, QPropertyAnimation, Qt, Q_ARG, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsColorizeEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .logic import ab_level_gain_db, compute_peaks
from .theme import ACCENT, PANEL, icon

# Seq base for our peak requests — far above MainWindow's incrementing _current_seq
# so worker.peaksReady delivered here is ignored by MainWindow._on_peaks_ready.
_PEAK_SEQ_BASE = 9_000_000


class _MiniWave(QWidget):
    """Tiny read-only waveform preview painted from mono peaks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._peaks: list[tuple[float, float]] = []
        self.setMinimumHeight(64)

    def set_mono(self, mono: np.ndarray | None) -> None:
        if mono is None or len(mono) == 0:
            self._peaks = []
        else:
            self._peaks = compute_peaks(np.asarray(mono, dtype=float), max(1, self.width()))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PANEL))
        if not self._peaks:
            return
        h = self.height()
        mid = h / 2.0
        painter.setPen(QPen(QColor(ACCENT), 1))
        n = len(self._peaks)
        for x, (lo, hi) in enumerate(self._peaks):
            px = int(x * self.width() / n)
            y1 = mid - hi * mid
            y2 = mid - lo * mid
            painter.drawLine(px, int(y1), px, int(y2))


class _SlotPanel(QWidget):
    """One A/B side: tree picker, then filename + waveform once a sample is chosen."""

    selected = Signal(object)            # Sample — double-click commits to slot
    audition = Signal(object)            # Sample — single-click/arrow previews
    removed = Signal()
    add_to_crate = Signal(object, int)   # (Sample, crate_id)
    create_crate = Signal(object)        # Sample

    def __init__(self, title: str, nodes: dict, crates: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crates = crates
        self._sample = None
        self._loudness: float = 0.0

        # Pulse glow used to flag the currently-playing slot during A/B toggle.
        self._glow = QGraphicsColorizeEffect(self)
        self._glow.setColor(QColor(ACCENT))
        self._glow.setStrength(0.0)
        self.setGraphicsEffect(self._glow)
        self._pulse = QPropertyAnimation(self._glow, b"strength", self)
        self._pulse.setDuration(550)
        self._pulse.setKeyValueAt(0.0, 0.0)
        self._pulse.setKeyValueAt(0.35, 0.75)
        self._pulse.setKeyValueAt(1.0, 0.0)

        self._stack = QStackedWidget()

        # --- picker page ---
        picker = QWidget()
        picker_layout = QVBoxLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("filter…")
        self._filter.textChanged.connect(self._apply_filter)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel(title)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        self._tree.currentItemChanged.connect(self._on_current_changed)
        self._build_tree(nodes)
        picker_layout.addWidget(self._filter)
        picker_layout.addWidget(self._tree)

        # --- loaded page ---
        loaded = QWidget()
        loaded_layout = QVBoxLayout(loaded)
        loaded_layout.setContentsMargins(0, 0, 0, 0)
        self._name_label = QLabel("—")
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet("font-weight: bold;")
        self._wave = _MiniWave()
        button_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setIcon(icon("delete"))
        self._remove_btn.setProperty("danger", True)
        self._remove_btn.clicked.connect(self._on_remove)
        self._crate_btn = QToolButton()
        self._crate_btn.setText("Add to crate")
        self._crate_btn.setIcon(icon("favorite"))
        self._crate_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._crate_btn.setMenu(self._build_crate_menu())
        button_row.addWidget(self._remove_btn)
        button_row.addWidget(self._crate_btn)
        button_row.addStretch()
        loaded_layout.addWidget(self._name_label)
        loaded_layout.addWidget(self._wave)
        loaded_layout.addLayout(button_row)

        self._stack.addWidget(picker)   # 0
        self._stack.addWidget(loaded)   # 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    # --- public API ---
    @property
    def sample(self):
        return self._sample

    def set_sample(self, sample) -> None:
        self._sample = sample
        self._name_label.setText(sample.filename)
        self._wave.set_mono(None)
        self._crate_btn.setMenu(self._build_crate_menu())
        self._stack.setCurrentIndex(1)

    def set_mono(self, mono) -> None:
        self._wave.set_mono(mono)

    def clear(self) -> None:
        self._sample = None
        self._wave.set_mono(None)
        self._stack.setCurrentIndex(0)

    # --- internals ---
    def _build_tree(self, nodes: dict) -> None:
        roots = sorted(
            (n for n in nodes.values() if n.parent_key is None),
            key=lambda n: n.name.lower(),
        )
        for node in roots:
            self._tree.addTopLevelItem(self._make_folder_item(node))

    def _make_folder_item(self, node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        for child in sorted(node.children.values(), key=lambda n: n.name.lower()):
            item.addChild(self._make_folder_item(child))
        for sample in sorted(node.samples, key=lambda s: s.filename.lower()):
            leaf = QTreeWidgetItem([sample.filename])
            leaf.setData(0, Qt.ItemDataRole.UserRole, sample)
            item.addChild(leaf)
        return item

    def _build_crate_menu(self) -> QMenu:
        menu = QMenu(self)
        for crate in self._crates:
            menu.addAction(crate.name).triggered.connect(
                lambda _checked=False, c=crate: self._emit_add_to_crate(c.id)
            )
        menu.addSeparator()
        menu.addAction("New crate…").triggered.connect(self._emit_create_crate)
        return menu

    def _emit_add_to_crate(self, crate_id: int) -> None:
        if self._sample is not None:
            self.add_to_crate.emit(self._sample, crate_id)

    def _emit_create_crate(self) -> None:
        if self._sample is not None:
            self.create_crate.emit(self._sample)

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        sample = item.data(0, Qt.ItemDataRole.UserRole)
        if sample is not None:
            self.selected.emit(sample)

    def _on_current_changed(self, item: QTreeWidgetItem, _prev) -> None:
        # Single click + arrow navigation auditions the highlighted leaf.
        if item is None:
            return
        sample = item.data(0, Qt.ItemDataRole.UserRole)
        if sample is not None:
            self.audition.emit(sample)

    def pulse(self) -> None:
        """Flash a brief glow to flag this slot as the one now playing."""
        self._pulse.stop()
        self._pulse.start()

    def _on_remove(self) -> None:
        self.clear()
        self.removed.emit()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()

        def visit(item: QTreeWidgetItem) -> bool:
            sample = item.data(0, Qt.ItemDataRole.UserRole)
            child_match = False
            for i in range(item.childCount()):
                child_match = visit(item.child(i)) or child_match
            self_match = (not needle) or (needle in item.text(0).lower())
            visible = self_match or child_match
            item.setHidden(not visible)
            if needle and child_match:
                item.setExpanded(True)
            return visible if sample is None else (self_match or visible)

        for i in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(i))


class ABCompareDialog(QDialog):
    """Modal A/B compare workspace built on the library folder tree."""

    add_to_crate_requested = Signal(object, int)   # (Sample, crate_id)
    create_crate_requested = Signal(object)        # Sample

    def __init__(self, nodes: dict, crates: list, worker, player, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("A/B Compare")
        self.resize(760, 560)
        self._worker = worker
        self._player = player
        self._current = "a"
        self._peak_seq = _PEAK_SEQ_BASE
        self._seq_to_panel: dict[int, _SlotPanel] = {}

        self._panel_a = _SlotPanel("A", nodes, crates, self)
        self._panel_b = _SlotPanel("B", nodes, crates, self)
        for panel in (self._panel_a, self._panel_b):
            panel.selected.connect(lambda s, p=panel: self._on_selected(p, s))
            panel.audition.connect(lambda s, p=panel: self._on_audition(s, p))
            panel.removed.connect(self._on_removed)
            panel.add_to_crate.connect(self.add_to_crate_requested)
            panel.create_crate.connect(self.create_crate_requested)

        panels_row = QHBoxLayout()
        panels_row.addWidget(self._panel_a)
        panels_row.addWidget(self._panel_b)

        controls_row = QHBoxLayout()
        self._toggle_btn = QPushButton("A/B Toggle")
        self._toggle_btn.setIcon(icon("play"))
        self._toggle_btn.setProperty("primary", True)
        self._toggle_btn.clicked.connect(self._toggle)
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setIcon(icon("refresh"))
        self._reset_btn.clicked.connect(self._reset)
        controls_row.addWidget(self._toggle_btn)
        controls_row.addWidget(self._reset_btn)
        controls_row.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(panels_row)
        layout.addLayout(controls_row)
        layout.addWidget(button_box)

        if worker is not None:
            worker.peaksReady.connect(self._on_peaks_ready)

    # --- slot selection ---
    def _on_selected(self, panel: _SlotPanel, sample) -> None:
        panel.set_sample(sample)
        self._request_peaks(panel, sample.path)

    def _on_audition(self, sample, panel: _SlotPanel | None = None) -> None:
        try:
            gain_db = None
            if panel is not None and getattr(self._player, "apply_loudness_leveling", False):
                other = self._panel_b if panel is self._panel_a else self._panel_a
                gain_db = ab_level_gain_db(panel._loudness, other._loudness)
            self._player.play(sample.path, gain_db=gain_db)
        except Exception:  # noqa: BLE001 — playback best-effort
            pass

    def _on_removed(self) -> None:
        self._player.stop()

    def _request_peaks(self, panel: _SlotPanel, path: str) -> None:
        if self._worker is None:
            return
        self._peak_seq += 1
        seq = self._peak_seq
        self._seq_to_panel[seq] = panel
        QMetaObject.invokeMethod(
            self._worker,
            "request_peaks",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, seq),
            Q_ARG(str, path),
            Q_ARG(int, 800),
        )

    def _on_peaks_ready(self, seq: int, mono) -> None:
        panel = self._seq_to_panel.pop(seq, None)
        if panel is not None:
            panel.set_mono(mono)
            if mono is not None and len(mono) > 0:
                panel._loudness = float(np.sqrt(np.mean(np.square(np.asarray(mono, dtype=float)))))
            else:
                panel._loudness = 0.0

    # --- playback ---
    def _toggle(self) -> None:
        a, b = self._panel_a.sample, self._panel_b.sample
        if a is None and b is None:
            return
        nxt = "b" if self._current == "a" else "a"
        target = b if nxt == "b" else a
        if target is None:  # other slot empty — stay on current
            nxt = self._current
            target = a if nxt == "a" else b
        if target is None:
            return
        self._current = nxt
        active_panel = self._panel_a if nxt == "a" else self._panel_b
        other_panel = self._panel_b if nxt == "a" else self._panel_a
        active_panel.pulse()
        try:
            gain_db = None
            if getattr(self._player, "apply_loudness_leveling", False):
                gain_db = ab_level_gain_db(active_panel._loudness, other_panel._loudness)
            self._player.play(target.path, gain_db=gain_db)
        except Exception:  # noqa: BLE001 — playback best-effort
            pass

    def _reset(self) -> None:
        self._player.stop()
        self._panel_a.clear()
        self._panel_b.clear()
        self._current = "a"

    def done(self, result: int) -> None:  # noqa: D102 — Qt override; release player + signal
        self._player.stop()
        if self._worker is not None:
            try:
                self._worker.peaksReady.disconnect(self._on_peaks_ready)
            except (RuntimeError, TypeError):
                pass
        super().done(result)

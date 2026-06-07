"""Dialog for resolving duplicate-hash groups detected by the dedup backend."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..db.models import Sample
from ..dedup import ResolutionPlan, group_duplicates, is_generated_edit, pick_best, plan_resolution


class DuplicatesDialog(QDialog):
    reveal_requested = Signal(str)   # sample path
    delete_requested = Signal(int)   # sample id

    def __init__(
        self,
        samples: list[Sample],
        saved_dir: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Duplicates")

        self._saved_dir = saved_dir
        # Keeper ids are used as dict keys; drop any group with an un-indexed
        # member (id is None) so resolution never keys on None.
        self._groups: list[list[Sample]] = [
            g for g in group_duplicates(samples)
            if all(s.id is not None for s in g)
        ]
        self._keepers: dict[int, int] = {}   # gi -> keeper sample id
        self._resolved: dict[int, bool] = {}
        self._group_boxes: dict[int, QGroupBox] = {}

        for gi, group in enumerate(self._groups):
            best = pick_best(group, saved_dir)
            self._keepers[gi] = best.id
            self._resolved[gi] = False

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def group_count(self) -> int:
        return len(self._groups)

    def keeper_id(self, gi: int) -> int:
        return self._keepers[gi]

    def set_keeper(self, gi: int, sample_id: int) -> None:
        self._keepers[gi] = sample_id

    def plan_for_group(self, gi: int) -> ResolutionPlan:
        group = self._groups[gi]
        keeper_id = self._keepers[gi]
        id_to_sample = {s.id: s for s in group}
        keeper = id_to_sample[keeper_id]
        return plan_resolution(group, saved_dir=self._saved_dir, keep=keeper)

    def is_resolved(self, gi: int) -> bool:
        return self._resolved[gi]

    def _perform_resolution(self, gi: int) -> None:
        if self._resolved[gi]:
            return
        plan = self.plan_for_group(gi)
        for s in plan.remove:
            self.delete_requested.emit(s.id)
        self._resolved[gi] = True
        box = self._group_boxes.get(gi)
        if box is not None:
            box.setEnabled(False)
            box.setTitle(box.title() + "  ✓ resolved")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        inner = QVBoxLayout(container)

        for gi, group in enumerate(self._groups):
            box = self._make_group_box(gi, group)
            self._group_boxes[gi] = box
            inner.addWidget(box)

        inner.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        outer.addWidget(button_box)

    def _make_group_box(self, gi: int, group: list[Sample]) -> QGroupBox:
        box = QGroupBox(f"Group {gi + 1} — {len(group)} copies")
        layout = QVBoxLayout(box)

        btn_group = QButtonGroup(box)
        btn_group.setExclusive(True)

        for sample in group:
            radio, row_layout = self._make_member_row(gi, sample, btn_group)
            layout.addLayout(row_layout)
            if sample.id == self._keepers[gi]:
                radio.setChecked(True)

        resolve_btn = QPushButton("Resolve")
        resolve_btn.clicked.connect(lambda checked=False, g=gi: self._on_resolve_clicked(g))
        layout.addWidget(resolve_btn)

        return box

    def _make_member_row(
        self,
        gi: int,
        sample: Sample,
        btn_group: QButtonGroup,
    ) -> tuple[QRadioButton, QHBoxLayout]:
        label = Path(sample.path).name
        tail = str(Path(sample.path).parent)
        if len(tail) > 40:
            tail = "…" + tail[-37:]
        badge = ""
        if is_generated_edit(sample, self._saved_dir):
            badge += " [edit]"
        if sample.analyzed_at:
            badge += " [analyzed]"
        radio = QRadioButton(f"{label}  ({tail}){badge}")
        radio.toggled.connect(
            lambda checked, sid=sample.id, g=gi: self.set_keeper(g, sid) if checked else None
        )
        btn_group.addButton(radio)

        reveal_btn = QPushButton("Reveal")
        reveal_btn.setFixedWidth(60)
        reveal_btn.clicked.connect(lambda checked=False, p=sample.path: self.reveal_requested.emit(p))

        row = QHBoxLayout()
        row.addWidget(radio, stretch=1)
        row.addWidget(reveal_btn)
        return radio, row

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_resolve_clicked(self, gi: int) -> None:
        plan = self.plan_for_group(gi)
        if not plan.remove:
            return

        n_remove = len(plan.remove)
        n_protected = len(plan.protected)

        msg = f"This will remove {n_remove} file(s)."
        if n_protected:
            msg += (
                f"\n\nWarning: {n_protected} of them are generated edits that will be "
                "PERMANENTLY deleted (not sent to the recycle bin)."
            )

        answer = QMessageBox.question(
            self,
            "Confirm resolution",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._perform_resolution(gi)

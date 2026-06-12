"""Modal that picks a target DAW + what metadata to transfer for Convert."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..convert.options import ConvertOptions

# (target id, label shown in the dropdown).
_TARGETS = [
    ("reaper", "Reaper (.RPP)"),
    ("ableton", "Ableton Live (.als)"),
    ("aaf", "AAF interchange (.aaf) — Cubase / Pro Tools / Logic"),
]


class ConvertDialog(QDialog):
    """Choose target DAW, the transfer checkboxes, and the output file path."""

    def __init__(self, source_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Convert project")
        self.setModal(True)
        self._source = Path(source_path)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._target = QComboBox()
        for tid, label in _TARGETS:
            self._target.addItem(label, tid)
        self._target.currentIndexChanged.connect(self._sync_out_ext)
        form.addRow("Target DAW:", self._target)
        layout.addLayout(form)

        layout.addWidget(QLabel("Transfer:"))
        self._cb_tempo = QCheckBox("Tempo")
        self._cb_tracks = QCheckBox("Tracks (names + types)")
        self._cb_samples = QCheckBox("Sample files (copy into ./media)")
        self._cb_plugins = QCheckBox("Plugin / instrument names")
        self._cb_effects = QCheckBox("Effect names")
        for cb in (self._cb_tempo, self._cb_tracks, self._cb_samples,
                   self._cb_plugins, self._cb_effects):
            cb.setChecked(True)
            layout.addWidget(cb)

        out_row = QHBoxLayout()
        self._out = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        out_row.addWidget(QLabel("Output:"))
        out_row.addWidget(self._out, stretch=1)
        out_row.addWidget(browse)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._default_out()

    # ── helpers ─────────────────────────────────────────────────────────────
    def _current_target(self) -> str:
        return self._target.currentData()

    def _default_out(self) -> None:
        from ..convert import target_extension

        ext = target_extension(self._current_target())
        out = self._source.with_name(f"{self._source.stem}_converted{ext}")
        self._out.setText(str(out))

    def _sync_out_ext(self) -> None:
        from ..convert import target_extension

        ext = target_extension(self._current_target())
        cur = self._out.text().strip()
        if cur:
            self._out.setText(str(Path(cur).with_suffix(ext)))
        else:
            self._default_out()

    def _browse(self) -> None:
        from ..convert import target_extension

        ext = target_extension(self._current_target())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save converted project", self._out.text(), f"*{ext}"
        )
        if path:
            if not path.lower().endswith(ext):
                path += ext
            self._out.setText(path)

    def options(self) -> ConvertOptions:
        return ConvertOptions(
            tempo=self._cb_tempo.isChecked(),
            tracks=self._cb_tracks.isChecked(),
            copy_samples=self._cb_samples.isChecked(),
            plugin_names=self._cb_plugins.isChecked(),
            effect_names=self._cb_effects.isChecked(),
        )

    def result_spec(self, _target_extension=None) -> tuple[str, ConvertOptions, str]:
        """Return (target, options, out_path) from the current selections."""
        out = self._out.text().strip()
        return self._current_target(), self.options(), out

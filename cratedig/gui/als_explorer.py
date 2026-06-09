"""ALS Explorer panel — embedded Qt page, native theme (matches sample explorer)."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..als.parser import parse_als

# ── Colors ───────────────────────────────────────────────────────────────────
# Neutral text ("" → inherit palette so it reads on any native theme); semantic
# colors chosen to stay legible on both light and dark; card fills are
# translucent rgba overlays that tint without fighting the native background.
C_OK     = "#2E9E4F"
C_ERR    = "#D8362F"
C_MUTED  = "#808080"
C_LABEL  = "#808080"
C_VALUE  = ""
C_HEADER = ""
C_VST    = "#B8860B"
C_M4L    = "#8E24AA"
C_SILENT = "#607D8B"
C_BG_CARD = "rgba(128,128,128,0.06)"
C_BG_ALT  = "rgba(128,128,128,0.13)"

_SILENT_THRESHOLD = -64.0

_TYPE_COLORS = {
    "midi": "#64B5F6", "audio": "#81C784",
    "group": "#FFD54F", "return": "#CE93D8", "main": "#FF8A65",
}

# ── i18n ───────────────────────────────────────────────────────────────────────

_LANG: str = "ru"

_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "btn_open":            "Открыть .als файл",
        "no_file":             "Файл не выбран",
        "placeholder":         "Перетащите .als файл сюда\nили нажмите «Открыть .als файл»",
        "dialog_title":        "Выберите файл Ableton Live",
        "dialog_all_files":    "Все файлы",
        "warn_invalid_title":  "Неверный файл",
        "warn_invalid_msg":    "Пожалуйста, перетащите файл .als",
        "err_title":           "Ошибка",
        "tab_instruments":     "Инструменты",
        "tab_plugins":         "Плагины",
        "tab_tracks":          "Дорожки",
        "main_channel":        "MAIN КАНАЛ",
        "fader":               "Фейдер:",
        "fader_above":         "⚠ выше 0 dB!",
        "plugins_on_main":     "Плагины на Main:",
        "none":                "Нет",
        "length":              "Длина:",
        "third_party":         "Сторонних плагинов:",
        "samples_none":        "✓  Семплы не используются",
        "empty_list":          "Нет",
    },
    "en": {
        "btn_open":            "Open .als file",
        "no_file":             "No file selected",
        "placeholder":         "Drag .als file here\nor click \"Open .als file\"",
        "dialog_title":        "Select Ableton Live file",
        "dialog_all_files":    "All files",
        "warn_invalid_title":  "Invalid file",
        "warn_invalid_msg":    "Please drop an .als file",
        "err_title":           "Error",
        "tab_instruments":     "Instruments",
        "tab_plugins":         "Plugins",
        "tab_tracks":          "Tracks",
        "main_channel":        "MAIN CHANNEL",
        "fader":               "Fader:",
        "fader_above":         "⚠ above 0 dB!",
        "plugins_on_main":     "Plugins on Main:",
        "none":                "None",
        "length":              "Length:",
        "third_party":         "3rd-party plugins:",
        "samples_none":        "✓  No samples used",
        "empty_list":          "None",
    },
}


def T(key: str) -> str:
    return _STRINGS[_LANG].get(key, key)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_db(val) -> str:
    if val is None:
        return "—"
    if val == float("-inf") or val <= _SILENT_THRESHOLD:
        return "-∞ dB"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f} dB"


def _track_type_label(t: str) -> str:
    return {"midi": "MIDI", "audio": "Audio", "group": "Group", "return": "Return"}.get(t, t)


def _arr_str(arr: dict | None) -> str:
    if not arr:
        return "—"
    t = arr["time_str"].split(":")
    return f"{t[0]}:{t[1][:2]} / {arr['bars']:.0f} bars @ {arr['bpm']} BPM"


def _samples_warning(found: int, total: int, missing: int) -> str:
    if _LANG == "ru":
        return f"⚠  Семплы: {found} из {total} в папке проекта  — {missing} отсутствуют"
    return f"⚠  Samples: {found} of {total} in project folder  — {missing} missing"


def _samples_ok(total: int) -> str:
    if _LANG == "ru":
        return f"✓  Все семплы в папке проекта  ({total})"
    return f"✓  All samples in project folder  ({total})"



# ── Qt style helpers ───────────────────────────────────────────────────────────

def _colored_label(text: str, color: str = "", bold: bool = False, font_size: int = 11) -> QLabel:
    lbl = QLabel(text)
    weight = "bold" if bold else "normal"
    color_css = f"color: {color}; " if color else ""
    lbl.setStyleSheet(f"{color_css}font-weight: {weight}; font-size: {font_size}px; background: transparent;")
    return lbl


def _card_frame(bg_color: str, radius: int = 8) -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(f"QFrame {{ background-color: {bg_color}; border-radius: {radius}px; }}")
    return frame


# ── Expandable samples widget ──────────────────────────────────────────────────

class ExpandableSamples(QWidget):
    def __init__(self, samples: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        found   = samples.get("found", [])
        missing = samples.get("missing", [])
        total   = len(found) + len(missing)

        if missing:
            bg, text_col = "rgba(216,54,47,0.13)", C_ERR
            summary = _samples_warning(len(found), total, len(missing))
        elif total == 0:
            bg, text_col = "rgba(46,158,79,0.13)", C_OK
            summary = T("samples_none")
        else:
            bg, text_col = "rgba(46,158,79,0.13)", C_OK
            summary = _samples_ok(total)

        self.setStyleSheet(f"QWidget#samplesCard {{ background-color: {bg}; border-radius: 8px; }}")
        self.setObjectName("samplesCard")

        self._expanded = False
        self._summary  = summary
        self._text_col = text_col
        self._found    = found
        self._missing  = missing
        self._total    = total

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("samplesCard")
        card.setStyleSheet(f"QFrame#samplesCard {{ background-color: {bg}; border-radius: 8px; }}")
        outer.addWidget(card)

        self._card_layout = QVBoxLayout(card)
        self._card_layout.setContentsMargins(12, 8, 12, 8)
        self._card_layout.setSpacing(0)

        if total == 0:
            lbl = _colored_label(summary, text_col)
            self._card_layout.addWidget(lbl)
            return

        self._btn = QPushButton(f"▶  {summary}")
        self._btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {text_col}; "
            f"text-align: left; border: none; padding: 2px 0; font-size: 11px; }}"
            f"QPushButton:hover {{ background: rgba(128,128,128,0.2); border-radius: 4px; }}"
        )
        self._btn.clicked.connect(self._toggle)
        self._card_layout.addWidget(self._btn)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(4, 2, 4, 4)
        inner_layout.setSpacing(1)
        for name in found:
            inner_layout.addWidget(self._sample_row("✓", name, C_OK))
        for name in missing:
            inner_layout.addWidget(self._sample_row("✗", name, C_ERR))
        self._inner.setVisible(False)
        self._card_layout.addWidget(self._inner)

    @staticmethod
    def _sample_row(icon: str, name: str, color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(4, 0, 4, 0)
        hl.setSpacing(4)
        hl.addWidget(_colored_label(icon, color, bold=True))
        hl.addWidget(_colored_label(name, color))
        hl.addStretch()
        return row

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._inner.setVisible(self._expanded)
        arrow = "▼" if self._expanded else "▶"
        self._btn.setText(f"{arrow}  {self._summary}")


# ── Main window ────────────────────────────────────────────────────────────────

class AlsExplorerPanel(QWidget):
    matchRequested = Signal(object)  # emitted with list[str] of ALS sample names
    reveal_requested = Signal(str)
    add_to_crate_requested = Signal(object, int)
    create_crate_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        self._data: dict | None = None
        self._match_seq = 0
        self._match_tab: QWidget | None = None
        self._crates: list = []

        self._build_ui()

    # ── Entry shape normalization helpers ──────────────────────────────────────

    @staticmethod
    def _normalize_entry(entry) -> object:
        """Return the primary Sample from an entry (single Sample or list[Sample]).

        Returns None for an empty list so callers can skip rather than IndexError.
        """
        if isinstance(entry, list):
            return entry[0] if entry else None
        return entry

    def _emit_reveal_for(self, entry) -> None:
        sample = self._normalize_entry(entry)
        if sample is not None:
            self.reveal_requested.emit(sample.path)

    def _emit_add_to_crate_for(self, entry, crate_id: int) -> None:
        sample = self._normalize_entry(entry)
        if sample is not None:
            self.add_to_crate_requested.emit(sample, crate_id)

    def _emit_create_crate_for(self, entry) -> None:
        sample = self._normalize_entry(entry)
        if sample is not None:
            self.create_crate_requested.emit(sample)

    def set_crates(self, crates: list) -> None:
        """Update the crates list used by the Library Match context menu."""
        self._crates = crates if crates is not None else []

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 12, 8)
        header_layout.setSpacing(8)

        title_lbl = _colored_label("Ableton Project Checker", C_HEADER, bold=True, font_size=16)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        lang_widget = QWidget()
        lang_widget.setStyleSheet("background: transparent;")
        lang_layout = QHBoxLayout(lang_widget)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(2)

        self._btn_lang_ru = QPushButton("RU")
        self._btn_lang_en = QPushButton("EN")
        for btn in (self._btn_lang_ru, self._btn_lang_en):
            btn.setFixedSize(38, 28)
            btn.setCheckable(True)
        self._btn_lang_ru.clicked.connect(lambda: self._set_lang("ru"))
        self._btn_lang_en.clicked.connect(lambda: self._set_lang("en"))
        lang_layout.addWidget(self._btn_lang_ru)
        lang_layout.addWidget(self._btn_lang_en)
        header_layout.addWidget(lang_widget)

        self._btn_open = QPushButton(T("btn_open"))
        self._btn_open.setMinimumWidth(160)
        self._btn_open.clicked.connect(self._open_file)
        header_layout.addWidget(self._btn_open)

        self._btn_match = QPushButton("Match library")
        self._btn_match.setMinimumWidth(120)
        self._btn_match.setEnabled(False)
        self._btn_match.clicked.connect(self._on_match_clicked)
        header_layout.addWidget(self._btn_match)

        main_layout.addWidget(header)

        # File bar
        file_bar = QWidget()
        file_bar_layout = QHBoxLayout(file_bar)
        file_bar_layout.setContentsMargins(16, 4, 16, 4)

        self._lbl_file = _colored_label(T("no_file"), C_MUTED)
        self._lbl_version = _colored_label("", C_MUTED)
        file_bar_layout.addWidget(self._lbl_file)
        file_bar_layout.addStretch()
        file_bar_layout.addWidget(self._lbl_version)
        main_layout.addWidget(file_bar)

        # Placeholder (shown before a file is loaded)
        self._placeholder = QLabel(T("placeholder"))
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {C_MUTED}; font-size: 14px; background: transparent;")
        main_layout.addWidget(self._placeholder, stretch=1)

        # Content area (hidden initially)
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Info area (scrollable, top half of splitter)
        self._info_scroll = QScrollArea()
        self._info_scroll.setWidgetResizable(True)
        self._info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._info_scroll.setMinimumHeight(150)
        self._info_scroll.setStyleSheet("background: transparent; border: none;")

        self._info_area = QWidget()
        self._info_area_layout = QVBoxLayout(self._info_area)
        self._info_area_layout.setContentsMargins(0, 0, 0, 0)
        self._info_area_layout.setSpacing(0)
        self._info_scroll.setWidget(self._info_area)

        # Tab widget (bottom half of splitter)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("")

        # Vertical splitter splits info area and tabs ~50/50
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._info_scroll)
        splitter.addWidget(self._tabs)
        splitter.setSizes([400, 400])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        content_layout.addWidget(splitter, stretch=1)

        self._content.setVisible(False)
        main_layout.addWidget(self._content, stretch=1)

        self._update_lang_buttons()

    # ── Language ───────────────────────────────────────────────────────────────

    def _set_lang(self, lang: str) -> None:
        global _LANG
        if _LANG == lang:
            self._update_lang_buttons()  # re-check: clicking active lang would untoggle it
            return
        _LANG = lang
        self._update_static_labels()
        if self._data is not None:
            self._render(self._data)

    def _update_static_labels(self) -> None:
        self._btn_open.setText(T("btn_open"))
        self._placeholder.setText(T("placeholder"))
        if self._data is None:
            self._lbl_file.setText(T("no_file"))
        self._update_lang_buttons()

    def _update_lang_buttons(self) -> None:
        self._btn_lang_ru.setChecked(_LANG == "ru")
        self._btn_lang_en.setChecked(_LANG == "en")

    # ── Drag & drop ────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path.lower().endswith(".als"):
            QMessageBox.warning(self, T("warn_invalid_title"), T("warn_invalid_msg"))
            return
        self._load_file(path)

    # ── File open ──────────────────────────────────────────────────────────────

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            T("dialog_title"),
            "",
            f"Ableton Live Set (*.als);;{T('dialog_all_files')} (*.*)",
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        try:
            data = parse_als(path)
        except Exception as exc:
            QMessageBox.critical(self, T("err_title"), str(exc))
            return
        self._data = data
        self._lbl_file.setText(os.path.basename(path))
        self._lbl_file.setStyleSheet(f"color: {C_VALUE}; background: transparent;")
        self._lbl_version.setText(data["ableton_version"])
        self._btn_match.setEnabled(True)
        self._render(data)

    def _on_match_clicked(self) -> None:
        if self._data is None:
            return
        samples = self._data.get("samples", {})
        names = list(samples.get("found", [])) + list(samples.get("missing", []))
        self._match_seq += 1
        self.matchRequested.emit(names)

    def set_match_result(self, result: dict) -> None:
        """Populate the Library Match tab with found/candidates/unresolved entries."""
        if self._match_tab is not None:
            idx = self._tabs.indexOf(self._match_tab)
            if idx >= 0:
                self._tabs.removeTab(idx)
        self._match_tab = self._build_match_tab(result)
        self._tabs.addTab(self._match_tab, "Library Match")

    def _build_match_tab(self, result: dict) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(2)

        found = result.get("found", [])
        candidates = result.get("candidates", [])
        unresolved = result.get("unresolved", [])

        if found:
            inner_layout.addWidget(_colored_label(f"Found ({len(found)})", C_OK, bold=True))
            for name, entry in found:
                row = self._build_found_row(name, entry)
                inner_layout.addWidget(row)

        if candidates:
            inner_layout.addWidget(_colored_label(f"Candidates ({len(candidates)})", C_VST, bold=True))
            for name, _entries in candidates:
                inner_layout.addWidget(_colored_label(f"  ?  {name}", C_VST))

        if unresolved:
            inner_layout.addWidget(_colored_label(f"Unresolved ({len(unresolved)})", C_ERR, bold=True))
            for name in unresolved:
                inner_layout.addWidget(_colored_label(f"  ✗  {name}", C_ERR))

        if not found and not candidates and not unresolved:
            inner_layout.addWidget(_colored_label("No samples to match", C_MUTED))

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)
        return tab

    def _build_found_row(self, name: str, entry) -> QWidget:
        """Build a found-entry row with a right-click context menu."""
        lbl = _colored_label(f"  ✓  {name}", C_OK)
        lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def _show_menu(pos) -> None:
            menu = QMenu(lbl)
            menu.addAction("Reveal in Explorer").triggered.connect(
                lambda: self._emit_reveal_for(entry)
            )
            menu.addAction("New crate from sample").triggered.connect(
                lambda: self._emit_create_crate_for(entry)
            )
            if self._crates:
                add_menu = menu.addMenu("Add to crate ▸")
                for crate in self._crates:
                    crate_id = crate.id if hasattr(crate, "id") else crate["id"]
                    crate_name = crate.name if hasattr(crate, "name") else crate["name"]
                    add_menu.addAction(crate_name).triggered.connect(
                        lambda _checked=False, cid=crate_id: self._emit_add_to_crate_for(entry, cid)
                    )
            menu.exec(lbl.mapToGlobal(pos))

        lbl.customContextMenuRequested.connect(_show_menu)
        return lbl

    # ── Render ─────────────────────────────────────────────────────────────────

    def _render(self, data: dict) -> None:
        # Show content area, hide placeholder
        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        # Clear info area
        while self._info_area_layout.count():
            item = self._info_area_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._build_info_area(data)

        # Rebuild tabs
        self._tabs.clear()
        self._match_tab = None
        self._tabs.addTab(self._build_tab_widget(data, "instruments"), T("tab_instruments"))
        self._tabs.addTab(self._build_tab_widget(data, "plugins"),     T("tab_plugins"))
        self._tabs.addTab(self._build_tab_widget(data, "tracks"),      T("tab_tracks"))

    # ── Info area ──────────────────────────────────────────────────────────────

    def _build_info_area(self, data: dict) -> None:
        pad_layout = QVBoxLayout()
        pad_layout.setContentsMargins(12, 4, 12, 4)
        pad_layout.setSpacing(6)

        # MAIN CHANNEL card
        main_card = _card_frame("rgba(63,81,181,0.13)")
        mc_layout = QVBoxLayout(main_card)
        mc_layout.setContentsMargins(12, 10, 12, 10)
        mc_layout.setSpacing(3)

        mc_layout.addWidget(_colored_label(T("main_channel"), C_HEADER, bold=True, font_size=13))

        main = data["main"]
        fdb = main["fader_db"]
        fader_txt = _fmt_db(fdb)
        if main["fader_above_0db"]:
            fader_col = C_ERR
            fader_txt += f"  {T('fader_above')}"
        elif fdb is not None and (fdb == float("-inf") or fdb <= _SILENT_THRESHOLD):
            fader_col = C_SILENT
        else:
            fader_col = C_OK

        mc_layout.addWidget(self._kv_row(T("fader"), fader_txt, fader_col))

        all_main_fx = main.get("plugins", [])
        mc_layout.addWidget(self._kv_row(
            T("plugins_on_main"),
            ", ".join(all_main_fx) if all_main_fx else T("none"),
            C_VALUE if all_main_fx else C_MUTED,
        ))

        pad_layout.addWidget(main_card)

        # Summary bar: count unique third-party plugin entries (VST2/VST3/AU)
        vst_all: set[str] = set()
        for src in data["tracks"] + [main]:
            for name in src.get("instruments", []) + src.get("plugins", []):
                if name.endswith(("[VST2]", "[VST3]", "[AU]")):
                    vst_all.add(name)

        summary_card = _card_frame("rgba(46,158,79,0.13)")
        sc_layout = QHBoxLayout(summary_card)
        sc_layout.setContentsMargins(12, 8, 12, 8)
        sc_layout.setSpacing(0)

        for label_text, val_text in [
            (T("length"),      _arr_str(data.get("arrangement"))),
            (T("third_party"), str(len(vst_all))),
        ]:
            col_widget = QWidget()
            col_widget.setStyleSheet("background: transparent;")
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(14, 0, 14, 0)
            col_layout.setSpacing(0)
            col_layout.addWidget(_colored_label(label_text, C_LABEL, font_size=10))
            col_layout.addWidget(_colored_label(val_text, C_OK, bold=True, font_size=14))
            sc_layout.addWidget(col_widget)
        sc_layout.addStretch()

        pad_layout.addWidget(summary_card)

        # Samples expandable
        samples_widget = ExpandableSamples(data.get("samples", {}))
        pad_layout.addWidget(samples_widget)

        wrapper = QWidget()
        wrapper.setLayout(pad_layout)
        self._info_area_layout.addWidget(wrapper)
        self._info_area_layout.addStretch()

    @staticmethod
    def _kv_row(key: str, value: str, value_color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 1, 0, 1)
        hl.setSpacing(4)
        key_lbl = _colored_label(key, C_LABEL)
        key_lbl.setFixedWidth(160)
        hl.addWidget(key_lbl)
        hl.addWidget(_colored_label(value, value_color, bold=True))
        hl.addStretch()
        return row

    # ── Tab builders ───────────────────────────────────────────────────────────

    def _build_tab_widget(self, data: dict, mode: str) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        rows = self._collect_rows(data, mode)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 4, 8, 4)
        inner_layout.setSpacing(1)

        if not rows:
            empty_lbl = _colored_label(T("empty_list"), C_MUTED, font_size=13)
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner_layout.addWidget(empty_lbl)
            inner_layout.addStretch()
        else:
            for i, (track_name, track_type, dev_name, dev_col) in enumerate(rows):
                bg = C_BG_CARD if i % 2 == 0 else C_BG_ALT
                row_f = QFrame()
                row_f.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 4px; }}")
                row_layout = QHBoxLayout(row_f)
                row_layout.setContentsMargins(8, 4, 10, 4)
                row_layout.setSpacing(4)

                tc  = _TYPE_COLORS.get(track_type, C_VALUE)
                tag = _track_type_label(track_type).upper() if track_type != "main" else "MAIN"
                tag_lbl = _colored_label(f"[{tag}]", tc, bold=True, font_size=10)
                tag_lbl.setFixedWidth(55)
                row_layout.addWidget(tag_lbl)

                name_lbl = _colored_label(track_name, C_LABEL)
                name_lbl.setFixedWidth(180)
                row_layout.addWidget(name_lbl)

                dev_lbl = _colored_label(dev_name, dev_col, bold=True)
                dev_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                row_layout.addWidget(dev_lbl)

                inner_layout.addWidget(row_f)
            inner_layout.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)
        return tab

    @staticmethod
    def _dev_color(name: str) -> str:
        if name.endswith("[VST2]") or name.endswith("[VST3]") or name.endswith("[AU]"):
            return C_VST
        if name.endswith("[M4L]"):
            return C_M4L
        return C_VALUE

    @staticmethod
    def _collect_rows(data: dict, mode: str) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        main = data["main"]

        if mode == "instruments":
            for t in data["tracks"]:
                for d in t.get("instruments", []):
                    rows.append((t["name"], t["type"], d, AlsExplorerPanel._dev_color(d)))
            for d in main.get("instruments", []):
                rows.append(("Main", "main", d, AlsExplorerPanel._dev_color(d)))

        elif mode == "plugins":
            for t in data["tracks"]:
                for d in t.get("plugins", []):
                    rows.append((t["name"], t["type"], d, AlsExplorerPanel._dev_color(d)))
            for d in main.get("plugins", []):
                rows.append(("Main", "main", d, AlsExplorerPanel._dev_color(d)))

        elif mode == "tracks":
            for t in data["tracks"]:
                rows.append((t["name"], t["type"], "", C_VALUE))

        return rows


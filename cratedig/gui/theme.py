"""Shared desktop theme helpers for the PySide6 GUI."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle


BG = "#0f1117"
PANEL = "#141922"
PANEL_2 = "#1a2030"
PANEL_3 = "#232c3d"
BORDER = "#273142"
TEXT = "#e8edf7"
MUTED = "#97a1b3"
ACCENT = "#67d5ff"
ACCENT_2 = "#8bdb81"
WARN = "#f4c95d"
ERROR = "#ff6b6b"
PINK = "#ff7ab6"


class _NoFocusRectStyle(QProxyStyle):
    """Fusion style without Qt's native focus rectangle over selected items."""

    def drawPrimitive(self, element, option, painter, widget=None):  # noqa: N802 - Qt override
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)


def icon(name: str):
    """Return a native Qt standard icon by friendly name."""
    mapping = {
        "play": QStyle.StandardPixmap.SP_MediaPlay,
        "stop": QStyle.StandardPixmap.SP_MediaStop,
        "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
        "download": QStyle.StandardPixmap.SP_ArrowDown,
        "preview": QStyle.StandardPixmap.SP_MediaVolume,
        "refresh": QStyle.StandardPixmap.SP_BrowserReload,
        "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
        "duplicates": QStyle.StandardPixmap.SP_FileDialogListView,
        "compare": QStyle.StandardPixmap.SP_ComputerIcon,
        "samples": QStyle.StandardPixmap.SP_DirHomeIcon,
        "ableton": QStyle.StandardPixmap.SP_DriveHDIcon,
        "health": QStyle.StandardPixmap.SP_DialogApplyButton,
        "scan": QStyle.StandardPixmap.SP_DirOpenIcon,
        "analyze": QStyle.StandardPixmap.SP_FileDialogInfoView,
        "favorite": QStyle.StandardPixmap.SP_DialogYesButton,
        "export": QStyle.StandardPixmap.SP_DialogSaveButton,
        "delete": QStyle.StandardPixmap.SP_TrashIcon,
    }
    app = QApplication.instance()
    style = app.style() if app is not None else QApplication.style()
    return style.standardIcon(mapping.get(name, QStyle.StandardPixmap.SP_FileIcon))


def _render_logo(size: int) -> QPixmap:
    """Paint the brand mark (▣ motif) at a given square size."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.08
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    radius = size * 0.22

    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#16708a"))
    grad.setColorAt(1.0, QColor("#0d1118"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor(ACCENT), max(1.0, size * 0.04)))
    p.drawRoundedRect(rect, radius, radius)

    # Inner square — the ▣ glyph.
    inner = size * 0.30
    inner_rect = QRectF(
        (size - inner) / 2, (size - inner) / 2, inner, inner
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(ACCENT)))
    p.drawRoundedRect(inner_rect, size * 0.06, size * 0.06)
    p.end()
    return pm


def app_icon() -> QIcon:
    """Branded window/taskbar icon, rendered programmatically (no asset file)."""
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_render_logo(s))
    return ic


def apply_app_theme(app: QApplication) -> None:
    """Apply the global dark palette and stylesheet."""
    app.setStyle(_NoFocusRectStyle("Fusion"))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("#10141d"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL_2))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL_3))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1f3a42"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    app.setPalette(palette)

    app.setStyleSheet(f"""
        QWidget {{
            background: {BG};
            color: {TEXT};
            font-size: 12px;
        }}
        QMainWindow, QDialog {{
            background: {BG};
        }}
        #AppShell, #PageSurface {{
            background: {BG};
        }}
        #Sidebar {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0b0f16, stop:1 #101725);
            border-right: 1px solid #202838;
        }}
        #SidebarTitle {{
            color: {ACCENT};
            font-size: 23px;
            font-weight: 800;
            letter-spacing: 0;
        }}
        #SectionTitle {{
            color: {MUTED};
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        #Panel, #Card {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #151b26, stop:1 #111721);
            border: 1px solid rgba(103, 213, 255, 0.12);
            border-radius: 10px;
        }}
        QGroupBox {{
            background: rgba(20, 25, 34, 0.82);
            border: 1px solid rgba(103, 213, 255, 0.16);
            border-radius: 10px;
            margin-top: 14px;
            padding: 10px 10px 10px 10px;
            font-weight: 700;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 1px;
            padding: 0 7px;
            color: {MUTED};
            background: {BG};
        }}
        QDialog#SettingsDialog {{
            background: #0d1118;
        }}
        QGroupBox#SettingsGroup {{
            margin-top: 16px;
            padding-top: 10px;
        }}
        QGroupBox#SettingsGroup::title {{
            top: 2px;
            left: 14px;
            padding: 1px 8px;
            color: {ACCENT};
            background: #0d1118;
        }}
        QDialog#SettingsDialog QCheckBox {{
            min-height: 20px;
            spacing: 8px;
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel[muted="true"] {{
            color: {MUTED};
        }}
        QPushButton, QToolButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #222a3a, stop:1 #171d2a);
            border: 1px solid rgba(103, 213, 255, 0.14);
            border-radius: 7px;
            padding: 6px 10px;
            color: {TEXT};
            font-weight: 600;
        }}
        QPushButton:hover, QToolButton:hover {{
            background: #273246;
            border-color: rgba(103, 213, 255, 0.42);
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background: #263247;
        }}
        QPushButton:disabled, QToolButton:disabled {{
            color: #586173;
            background: #131720;
            border-color: #202838;
        }}
        QPushButton:checked, QToolButton:checked {{
            background: #123345;
            border-color: {ACCENT};
            color: #dff8ff;
        }}
        QPushButton[primary="true"] {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0f5f7a, stop:1 #16708a);
            border-color: {ACCENT};
            color: #ecfbff;
        }}
        QPushButton[danger="true"] {{
            background: #4d1d25;
            border-color: #8b303d;
            color: #ffe9ed;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background: #10141d;
            border: 1px solid rgba(103, 213, 255, 0.15);
            border-radius: 7px;
            padding: 6px 8px;
            selection-background-color: {ACCENT};
            selection-color: #071018;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
            border-color: {ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QTableWidget, QTableView, QTreeWidget, QListWidget {{
            background: #10141d;
            alternate-background-color: #151b27;
            border: 1px solid rgba(103, 213, 255, 0.12);
            border-radius: 9px;
            gridline-color: #242c3b;
            outline: 0;
        }}
        QTreeWidget {{
            show-decoration-selected: 0;
        }}
        QTableWidget::item, QTreeWidget::item, QListWidget::item {{
            padding: 6px 8px;
            border-radius: 6px;
            border: 1px solid transparent;
            margin: 1px 3px;
        }}
        QTreeWidget::item {{
            margin: 1px 0;
        }}
        QTableWidget::item:selected {{
            background: #1e313b;
            border: 1px solid rgba(232, 237, 247, 0.20);
            color: #f5f8ff;
        }}
        QTableWidget::item:focus, QTreeWidget::item:focus, QListWidget::item:focus {{
            border: 1px solid rgba(232, 237, 247, 0.18);
            outline: none;
        }}
        QTreeWidget::item:selected {{
            background: transparent;
            border: 1px solid transparent;
            color: {TEXT};
        }}
        QListWidget::item:selected {{
            background: #1f3a42;
            border: 1px solid rgba(232, 237, 247, 0.16);
            color: {TEXT};
        }}
        QHeaderView::section {{
            background: #171d29;
            color: {MUTED};
            border: none;
            border-right: 1px solid rgba(103, 213, 255, 0.09);
            border-bottom: 1px solid rgba(103, 213, 255, 0.09);
            padding: 7px 8px;
            font-weight: 700;
        }}
        QSplitter::handle {{
            background: #0b0d13;
        }}
        QSplitter::handle:hover {{
            background: {BORDER};
        }}
        QTabWidget::pane {{
            border: 1px solid rgba(103, 213, 255, 0.12);
            border-radius: 9px;
            background: {PANEL};
        }}
        QTabBar::tab {{
            background: #111722;
            border: 1px solid rgba(103, 213, 255, 0.13);
            border-bottom: none;
            padding: 7px 12px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            color: {MUTED};
        }}
        QTabBar::tab:selected {{
            color: {TEXT};
            background: {PANEL_2};
            border-color: {ACCENT};
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: #0d1118;
            border: none;
            width: 10px;
            height: 10px;
        }}
        QScrollBar::handle {{
            background: #354052;
            border-radius: 5px;
            min-height: 28px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
        }}
        QProgressBar {{
            background: #10141d;
            border: 1px solid {BORDER};
            border-radius: 6px;
            text-align: center;
            color: {TEXT};
            font-weight: 700;
        }}
        QProgressBar::chunk {{
            background: {ACCENT};
            border-radius: 5px;
        }}
        QStatusBar {{
            background: #0b0d13;
            border-top: 1px solid rgba(103, 213, 255, 0.10);
            color: transparent;
        }}
        QMenu {{
            background: {PANEL_2};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 22px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: #123345;
        }}
        QCheckBox {{
            spacing: 6px;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: #10141d;
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT};
            border-color: {ACCENT};
        }}
        QDial {{
            background: transparent;
        }}
    """)

"""cratedig.gui — GUI package (Qt-free submodules are safe to import without PySide6)."""

from __future__ import annotations


def run_gui(cfg=None) -> int:
    """Launch the PySide6 desktop GUI. Imports Qt lazily so the core app stays Qt-free."""
    # Lazy imports keep PySide6 optional at module import time.
    from PySide6.QtWidgets import QApplication
    import sys

    from ..config import load_config
    from ..db.database import Database
    from .main_window import MainWindow
    from .theme import app_icon, apply_app_theme

    if cfg is None:
        cfg = load_config()

    # Windows: distinct AppUserModelID so the taskbar shows our icon (not python's).
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("cratedig.app")
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    app.setWindowIcon(app_icon())
    db = Database(cfg.paths.db)
    window = MainWindow(db, cfg)
    window.show()
    return app.exec()

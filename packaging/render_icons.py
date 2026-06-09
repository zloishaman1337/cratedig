"""Generate cratedig.ico / cratedig.icns from the in-app brand mark.

Reuses `cratedig.gui.theme._render_logo` (the same ▣ mark painted at runtime) so
the file icon matches the window/taskbar icon. Run with the GUI extra installed:

    python packaging/render_icons.py

Outputs (next to this script):
  cratedig.ico   (Windows, always)
  cratedig.icns  (macOS, only when iconutil/Pillow can assemble it)
  icons/*.png     (intermediate PNGs)
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICON_DIR = HERE / "icons"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def _render_pngs() -> list[Path]:
    """Paint each size to PNG via Qt's QPixmap (offscreen)."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QBuffer, QIODevice

    from cratedig.gui.theme import _render_logo

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for size in SIZES:
        pm = _render_logo(size)
        dest = ICON_DIR / f"icon_{size}.png"
        pm.save(str(dest), "PNG")
        out.append(dest)
    del app
    return out


def _build_ico(pngs: list[Path]) -> Path:
    from PIL import Image

    ico_sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256)]
    base = Image.open(ICON_DIR / "icon_256.png").convert("RGBA")
    dest = HERE / "cratedig.ico"
    base.save(dest, format="ICO", sizes=ico_sizes)
    return dest


def _build_icns(pngs: list[Path]) -> Path | None:
    """Assemble .icns. Uses iconutil on macOS; falls back to Pillow elsewhere."""
    dest = HERE / "cratedig.icns"
    if sys.platform == "darwin":
        import shutil
        import subprocess

        iconset = HERE / "cratedig.iconset"
        iconset.mkdir(exist_ok=True)
        mapping = {
            16: ["icon_16x16.png"],
            32: ["icon_16x16@2x.png", "icon_32x32.png"],
            64: ["icon_32x32@2x.png"],
            128: ["icon_128x128.png"],
            256: ["icon_128x128@2x.png", "icon_256x256.png"],
            512: ["icon_256x256@2x.png", "icon_512x512.png"],
            1024: ["icon_512x512@2x.png"],
        }
        for size, names in mapping.items():
            src = ICON_DIR / f"icon_{size}.png"
            for name in names:
                shutil.copyfile(src, iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True)
        return dest
    try:
        from PIL import Image

        Image.open(ICON_DIR / "icon_1024.png").convert("RGBA").save(dest, format="ICNS")
        return dest
    except Exception as exc:  # Pillow ICNS support is platform/version dependent
        print(f"icns skipped ({exc}); build on macOS for a real .icns", file=sys.stderr)
        return None


def main() -> int:
    pngs = _render_pngs()
    ico = _build_ico(pngs)
    print(f"wrote {ico}")
    icns = _build_icns(pngs)
    if icns:
        print(f"wrote {icns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

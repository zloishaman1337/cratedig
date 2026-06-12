# PyInstaller spec — onedir build of the cratedig desktop GUI.
# Build:  pyinstaller packaging/cratedig.spec --noconfirm
# Output: dist/cratedig/  (Windows/Linux)  |  dist/cratedig.app  (macOS)

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPECDIR = Path(SPECPATH)            # injected by PyInstaller
ROOT = SPECDIR.parent
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Read the runtime version from the package SSOT mirror (kept in sync with
# pyproject.toml at bump time) so the macOS bundle reports the right version.
_init = (ROOT / "cratedig" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _init).group(1)

icon_file = str(SPECDIR / ("cratedig.ico" if IS_WIN else "cratedig.icns"))

# Bundled ffmpeg/ffplay + minisign (CI / local places them in packaging/bin/<os>/).
# minisign verifies the signed update manifest in the online updater.
bin_dir = SPECDIR / "bin" / ("windows" if IS_WIN else "macos")
exe_suffix = ".exe" if IS_WIN else ""
binaries = []
for tool in ("ffmpeg", "ffplay", "minisign"):
    p = bin_dir / f"{tool}{exe_suffix}"
    if p.exists():
        binaries.append((str(p), "."))

datas = [
    (str(ROOT / "config.example.toml"), "."),
    (str(ROOT / "cratedig" / "db" / "schema.sql"), "cratedig/db"),
]
# librosa ships data files and lazy-imports submodules PyInstaller may miss.
datas += collect_data_files("librosa")
# aaf2 (Convert → AAF export) ships its AAF model/metadict as package data and
# lazy-imports submodules.
datas += collect_data_files("aaf2")

hiddenimports = []
hiddenimports += collect_submodules("librosa")
hiddenimports += collect_submodules("aaf2")

a = Analysis(
    [str(SPECDIR / "cratedig_gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cratedig",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="cratedig",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="cratedig.app",
        icon=icon_file,
        bundle_identifier="com.cratedig.app",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )

# PACKAGING.md — distribution plan (onedir installer + macOS .app)

Goal: a real installed application, not a loose binary.
- **Windows**: signed-ish **Inno Setup** installer (`cratedig-setup-x.y.z.exe`) that
  installs a PyInstaller **onedir** build into `Program Files`, adds Start-menu +
  optional desktop shortcuts, registers an uninstaller.
- **macOS**: PyInstaller **onedir `--windowed`** → `cratedig.app` bundle, wrapped in a
  `.dmg` with drag-to-Applications layout.

Tool: **PyInstaller** (onedir, NOT onefile). No cross-compile — build each OS on its own
host. CI: GitHub Actions matrix (`windows-latest` + `macos-latest` [+ `macos-14` arm64]).

---

## 0. Prerequisites — CODE CHANGES needed BEFORE packaging works

These are blockers; do them first in the build session.

1. **User-writable data dir** (`cratedig/paths.py`, new helper or extend `config.py`):
   - Resolve a per-user data root via `platformdirs` (add dep) or hand-rolled:
     - Win: `%APPDATA%\cratedig`
     - macOS: `~/Library/Application Support/cratedig`
     - Linux: `~/.local/share/cratedig`
   - `load_config()` currently reads `./config.toml` from CWD and resolves relative
     paths against the config dir (`config.py:50-51`). In a frozen install CWD is
     arbitrary and the install dir is read-only. Change default config path + db +
     download_dir + saved_dir defaults to the user data dir when frozen
     (`getattr(sys, "frozen", False)`).
   - On first run: if user `config.toml` absent, seed it from the bundled
     `config.example.toml` (config_writer already has seed logic — reuse).

2. **Frozen resource resolution** for bundled data files (`db/schema.sql`,
   `config.example.toml`): when `sys.frozen`, read from `sys._MEIPASS` (onedir: the
   `_internal` folder). Add a `resource_path(name)` helper; route `schema.sql` load and
   example-config seed through it.

3. **ffmpeg / ffplay**: not Python packages. Ship the executables inside the build and
   make the app prefer the bundled copies:
   - Add a `ffmpeg_path()/ffplay_path()` resolver: when frozen, look in the bundle dir
     first, else fall back to PATH.
   - Audit current callers (yt-dlp ffmpeg location, `audio/playback.py` ffplay/ffmpeg
     calls) to use the resolver instead of bare `"ffplay"`/`"ffmpeg"`.

4. **GUI entry script** `packaging/cratedig_gui.py`: imports and calls
   `cratedig.gui.run_gui()` with no console. (Console subcommands stay on the CLI
   `cratedig` entry; the installed GUI app is windowed-only.)

5. **Icon assets** (real files — runtime `app_icon()` paints the in-app QIcon but the
   EXE/.app file icon needs `.ico`/`.icns`):
   - Add `packaging/render_icons.py`: reuse `theme._render_logo(size)` to dump PNGs at
     16/32/48/64/128/256/512/1024, then assemble `cratedig.ico` (Pillow) and
     `cratedig.icns` (`iconutil` on macOS, or `icnsutil`/Pillow).
   - Commit generated `packaging/cratedig.ico` + `packaging/cratedig.icns`.

---

## 1. PyInstaller spec — `packaging/cratedig.spec`

One spec, OS-branched. Key settings:

```python
# onedir (NOT onefile)
exe = EXE(..., console=False, icon='cratedig.ico'/'cratedig.icns', name='cratedig')
coll = COLLECT(exe, ...)            # → dist/cratedig/  (onedir)
# macOS only:
app = BUNDLE(coll, name='cratedig.app', icon='cratedig.icns',
             bundle_identifier='com.cratedig.app',
             info_plist={'CFBundleShortVersionString': version,
                         'NSHighResolutionCapable': True})
```

- `datas`: `db/schema.sql`, `config.example.toml`, icons.
- `binaries`: bundled `ffmpeg` + `ffplay` (`.exe` on Win). Download per-OS in CI, place
  in `packaging/bin/<os>/`:
  - Windows: gyan.dev / BtbN static builds (x64).
  - macOS: evermeet.cx / osxexperts static builds — **both arm64 AND x64** to match the
    `macos-14` (arm64) + `macos-13` (x64) matrix targets. ffmpeg/ffplay are bundled in
    the `.app` too (NOT only Windows).
- `hiddenimports` / hooks: PySide6 ok via official hook; `soundfile` bundles libsndfile
  via hook; `yt_dlp` fine.
- **INCLUDE `[analysis]` (librosa) — it is CORE, not optional.** librosa is used by
  `audio/analyzer.py`, `audio/features.py`, `index.py` to compute BPM/key + the 193-dim
  feature vectors that power similarity search (the headline feature). Excluding it would
  let the app browse/play/download but break analyze + computing new feature vectors.
  Cost ≈ +150–250MB. librosa pulls scipy + numba + llvmlite transitively (sklearn is NOT
  used directly). numba/llvmlite need their PyInstaller hooks (numba ships its own); onedir
  avoids the numba onefile-freeze pitfalls. Verify `analyze` works in the frozen build.
  (Optional future "lite" build could `excludes=['librosa','numba','llvmlite','scipy']`
  for a ~200MB-smaller browse-only artifact — not the default.)
- `yandex-music`, `requests`, `mutagen`, `tomlkit`, `numpy` → standard, no special work.

Build: `pyinstaller packaging/cratedig.spec --noconfirm` → `dist/cratedig/` (Win) or
`dist/cratedig.app` (mac).

---

## 2. Windows installer — Inno Setup (`packaging/windows/cratedig.iss`)

Inno Setup (free, simplest for "install to Program Files + shortcuts + uninstaller").

```ini
[Setup]
AppName=cratedig
AppVersion={#Version}
DefaultDirName={autopf}\cratedig          ; Program Files\cratedig
DefaultGroupName=cratedig
UninstallDisplayIcon={app}\cratedig.exe
OutputBaseFilename=cratedig-setup-{#Version}
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin                   ; or lowest for per-user install

[Files]
Source: "dist\cratedig\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\cratedig";           Filename: "{app}\cratedig.exe"
Name: "{group}\Uninstall cratedig"; Filename: "{uninstallexe}"
Name: "{autodesktop}\cratedig";     Filename: "{app}\cratedig.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
```

- User data (config.toml, db, downloads) lives in `%APPDATA%\cratedig` (from §0.1), NOT
  under `{app}` — so uninstall doesn't wipe the library and Program Files stays
  read-only-clean.
- Optional: code-sign `cratedig.exe` + installer with an Authenticode cert to avoid
  SmartScreen warnings (deferred — needs paid cert).
- Build: `iscc /DVersion=0.1.0 packaging\windows\cratedig.iss` → `Output\cratedig-setup-0.1.0.exe`.

---

## 3. macOS — `.app` + `.dmg` (`packaging/macos/make_dmg.sh`)

- PyInstaller produces `dist/cratedig.app` (from BUNDLE in spec).
- DMG via `create-dmg` (brew) or `hdiutil`:
  ```sh
  create-dmg --volname cratedig --app-drop-link 450 180 \
             --icon cratedig.app 150 180 \
             cratedig-0.1.0.dmg dist/cratedig.app
  ```
- Signing/notarization (deferred, optional for personal use): unsigned `.app` triggers
  Gatekeeper "unidentified developer" — user right-click→Open once, or
  `xattr -dr com.apple.quarantine`. Proper fix = Apple Developer ID + `codesign` +
  `notarytool` (needs $99/yr account).
- User data in `~/Library/Application Support/cratedig` (from §0.1).

---

## 4. CI — `.github/workflows/release.yml` (matrix)

```yaml
strategy:
  matrix:
    include:
      - os: windows-latest   # → Inno Setup installer
      - os: macos-14         # arm64 → .dmg
      - os: macos-13         # x64   → .dmg  (optional)
steps:
  - checkout
  - setup-python 3.11
  - pip install ".[gui,analysis,download,metadata]" pyinstaller pillow   # full app
  - download ffmpeg/ffplay for the OS → packaging/bin/
  - python packaging/render_icons.py
  - pyinstaller packaging/cratedig.spec --noconfirm
  - win:  choco install innosetup; iscc ...     → upload setup .exe
  - mac:  brew install create-dmg; make_dmg.sh  → upload .dmg
  - upload-artifact / attach to GitHub Release
```

---

## 5. Order of work (next session)

1. §0 code changes (data dir + frozen resources + ffmpeg resolver + GUI entry + icons).
   Add deps: `platformdirs`, `pyinstaller` (build-only), `pillow` (icon-build-only).
2. Write `cratedig.spec`; get a working local `dist/cratedig/` that launches.
3. Smoke the frozen app: config seeds to `%APPDATA%`, db created there, playback works
   via bundled ffplay, drag-to-DAW works.
4. Inno Setup script → installer; install/uninstall round-trip test.
5. macOS `.app` + `.dmg` on a Mac; Gatekeeper-open test.
6. CI workflow last (once local builds are green).

Acceptance: double-click installer → app in Start menu/Applications → launches → library
persists across reinstall → uninstall leaves user data intact.

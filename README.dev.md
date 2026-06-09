# cratedig — developer guide

> User-facing docs (install the app, configure, features) live in
> [README.md](README.md). This file is the source/developer workflow.
> Architecture and roadmap: [ARCHITECTURE.md](ARCHITECTURE.md).
> Packaging/distribution: [PACKAGING.md](PACKAGING.md).

A local desktop + TUI fork of **Sononym**: index your sample library, search by
**BPM / key / mood / tags**, find acoustically **similar** samples, **download**
new audio (YouTube, Yandex Music, FreeSound), organize crates,
inspect Ableton `.als` projects, and edit/export sample regions in a Simpler-like
panel. SQLite-backed. For personal, local use.

## Install (from source)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .                       # core: TUI + scan + search
pip install -e ".[analysis]"           # + librosa: BPM/key/similarity
pip install -e ".[download,metadata]"  # + downloaders + MusicBrainz/Discogs
pip install -e ".[gui]"                # + PySide6: desktop GUI
pip install -e ".[build]"              # + PyInstaller + Pillow (packaging only)
```

`ffmpeg` must be on PATH for YouTube audio extraction and best waveform decoding.
Without `ffmpeg`, YouTube downloads fall back to yt-dlp's native bestaudio file.
Waveform rendering falls back to `soundfile` for formats it can decode.
`ffplay` must be on PATH for TUI/GUI playback.

## Configure

```powershell
copy config.example.toml config.toml
```

Edit `config.toml` — set `library_dirs`, `download_dir`, and any API tokens.
Do not commit your local `config.toml` if it contains tokens or machine-specific
paths; keep `config.example.toml` as the shareable template.

In a **frozen/installed** build, `config.toml` + the database + downloads live in
the per-user data dir (`%APPDATA%\cratedig` on Windows,
`~/Library/Application Support/cratedig` on macOS), seeded from the bundled
`config.example.toml` on first run. See `cratedig/paths.py`.

## Use

```powershell
cratedig                 # launch the TUI
cratedig gui             # launch the desktop GUI (needs [gui] extra)
cratedig scan            # index library_dirs (headless)
cratedig classify        # fill missing categories from filenames/paths
cratedig analyze         # compute BPM/key/feature vectors (needs librosa)
cratedig download "artist - track"            # combined-fallback download
cratedig download "<url>" --url --source youtube
cratedig health          # library health report
cratedig dedup           # duplicate-resolution dry run
```

### TUI keys

| key | action |
|-----|--------|
| `s` | scan library_dirs |
| `a` | analyze (compute descriptors) |
| `c` | classify missing categories |
| `f` | find similar to selected row |
| `u` | show duplicate files grouped by file hash |
| `t` | reload the path-based library tree |
| `b` | toggle favorite on the selected folder/sample |
| arrows / click | preview the highlighted sample or download hit (uses `ffplay`) |
| `p` | play / stop the selected sample, or preview the selected download hit |
| `x` | stop playback |
| `r` | refresh / clear search |
| `d` | toggle Download mode |
| `1` / `2` (download mode) | dl_mode: `samples` (FreeSound) / `tracks` (Yandex → YT) |
| `Enter` (search box) | browse: filter by filename · download: run backend search |
| `Enter` (on a hit) | download the highlighted candidate (auto-indexed) |
| `q` | quit |

### API tokens

See `config.example.toml` for step-by-step token instructions:

- **FreeSound** (`sources.freesound.token`) — sample search/download.
- **Yandex Music** (`sources.yandex.token` / `token_file`) — track search/download.
- **YouTube** — no token; needs `[download]` extra + `ffmpeg` on PATH.

## Packaging

See [PACKAGING.md](PACKAGING.md). Local Windows build:

```powershell
pip install -e ".[gui,analysis,download,metadata,build]"
# stage ffmpeg/ffplay into packaging\bin\windows\
python packaging\render_icons.py
pyinstaller packaging\cratedig.spec --noconfirm     # -> dist\cratedig\
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /DVersion=0.1.0 packaging\windows\cratedig.iss
# -> packaging\windows\Output\cratedig-setup-0.1.0.exe
```

macOS `.app`/`.dmg` and the GitHub Actions release matrix are described in
PACKAGING.md (`packaging/macos/make_dmg.sh`, `.github/workflows/release.yml`).

## Layout

See [ARCHITECTURE.md](ARCHITECTURE.md). Source under `cratedig/`:
`db/` · `scan/` · `audio/` · `search/` · `sources/` · `metadata/` · `tui/` · `gui/` · `als/` · `paths.py`.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest
```

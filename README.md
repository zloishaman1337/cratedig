# cratedig

A local desktop + TUI fork of **Sononym**: index your sample library, search by
**BPM / key / mood / tags**, find acoustically **similar** samples, **download**
new audio (YouTube, Yandex Music, FreeSound, Internet Archive), organize crates,
inspect Ableton `.als` projects, and edit/export sample regions in a Simpler-like
panel. SQLite-backed. For personal, local use.

> Status: standalone desktop GUI is now the primary surface. Scan → analyze →
> browse → search → similarity → crates → Simpler export works in code/tests.
> Web UI has been removed; finish the pre-redesign stabilization roadmap in
> [ARCHITECTURE.md](ARCHITECTURE.md) before visual redesign.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .                       # core: TUI + scan + search
pip install -e ".[analysis]"           # + librosa: BPM/key/similarity
pip install -e ".[download,metadata]"  # + downloaders + MusicBrainz/Discogs
pip install -e ".[gui]"                # + PySide6: desktop GUI (optional)
```

`ffmpeg` must be on PATH for YouTube audio extraction and best waveform decoding.
Without `ffmpeg`, YouTube downloads fall back to yt-dlp's native bestaudio file.
Waveform rendering falls back to `soundfile` for formats it can decode.
`ffplay` must be on PATH for TUI playback.

## Configure

```powershell
copy config.example.toml config.toml
```

Edit `config.toml` — set `library_dirs`, `download_dir`, and any API tokens.
Do not commit your local `config.toml` if it contains tokens or machine-specific
paths; keep `config.example.toml` as the shareable template.

## Use

```powershell
cratedig                 # launch the TUI
cratedig gui             # launch the desktop GUI (needs [gui] extra)
cratedig scan            # index library_dirs (headless)
cratedig classify        # fill missing categories from filenames/paths
cratedig analyze         # compute BPM/key/feature vectors (needs librosa)
cratedig download "artist - track"            # combined-fallback download
cratedig download "<url>" --url --source youtube
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
| `b` | toggle favorite on the selected folder (in tree) or sample (in contents) |
| arrows / click | preview the highlighted sample or download hit (uses `ffplay`) |
| `p` | play / stop the selected sample, or preview the selected download hit |
| `x` | stop playback |
| `r` | refresh / clear search |
| `d` | toggle Download mode |
| `1` / `2` (in download mode) | switch dl_mode: `samples` (FreeSound) / `tracks` (Yandex → YT fallback) |
| `Enter` (in search box) | browse: filter by filename · download: run backend search |
| `Enter` (on a hit) | download the highlighted candidate (auto-indexed into library) |
| `q` | quit |

Download-mode preview needs a direct preview URL from the backend. FreeSound
results include one; Yandex/YouTube hits usually do not, so they show a status
message and can still be downloaded with `Enter`.

### Desktop GUI

```powershell
pip install -e ".[gui]"   # installs PySide6
cratedig gui              # or: python -m cratedig gui
```

The desktop GUI is the main app surface. It includes a folder tree, sample table,
favorites, crates, similarity search, metadata panel, download pane, embedded
Ableton `.als` explorer, and a Simpler-like editor/preview pane with region,
fade, ADSR, reverse, loop preview, Saved exports, and drag export. Playback reuses
the same `ffplay`-backed `AudioPlayer` as the TUI. PySide6 is an optional
dependency; core CLI/TUI commands still run without it.

Before redesign, the locked stabilization roadmap is: clean legacy files/docs,
fix drag-to-DAW, improve download/metadata feedback, add Simpler transient tools,
build a duplicates resolver, match missing ALS samples against the library, add
A/B audition controls, expand auto-tags, and add a library health dashboard.

### API tokens

The Download mode needs credentials for the paid/private backends. See
`config.example.toml` for step-by-step instructions on getting tokens for:

- **FreeSound** (`sources.freesound.token`) — required for sample search/download.
- **Yandex Music** (`sources.yandex.token` or `token_file`) — required for track search/download. The old `yamdl.exe` flow is gone; we now use the `yandex-music` Python library directly.
- **YouTube** — no token; `pip install -e ".[download]"` for `yt-dlp` + `ffmpeg` on PATH.

Scan, analyze, classify, and download operations show live progress/status in a
multi-line TUI operation panel. Scan and analyze are intentionally mutually exclusive.
After analysis, the TUI library table shows a compact waveform thumbnail in each
analyzed file row.

## Clone on another machine

```powershell
git clone https://github.com/<your-user>/Sononym_fork.git
cd Sononym_fork

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
pip install -e ".[dev,analysis,download,metadata]"
copy config.example.toml config.toml
notepad config.toml
```

Set `library_dirs`, `download_dir`, and tokens in the new machine's local
`config.toml`, then run:

```powershell
cratedig scan
cratedig analyze
cratedig
cratedig gui
```

Recommended Windows tools:

```powershell
winget install --id Gyan.FFmpeg --source winget
ffmpeg -version
ffplay -version
```

Large/local artifacts such as `.venv/`, `data/`, SQLite DBs, downloaded audio,
and private tokens should stay out of git unless you intentionally choose
otherwise.

## Layout

See [ARCHITECTURE.md](ARCHITECTURE.md). Source under `cratedig/`:
`db/` · `scan/` · `audio/` · `search/` · `sources/` · `metadata/` · `tui/` · `gui/` · `als/`.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest
```

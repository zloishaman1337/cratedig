# cratedig

A local TUI + web-panel fork of **Sononym**: index your sample library, search by
**BPM / key / mood / tags**, find acoustically **similar** samples, **download**
new audio (YouTube, Yandex Music, FreeSound, Internet Archive), and dive into
samples with a browser waveform/metadata panel. SQLite-backed. For personal,
local use.

> Status: **v0.1 skeleton + working local-scan slice.** Scan → analyze → browse →
> search → similarity works end-to-end. Download backends + metadata are wired but
> need their deps/tokens.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .                       # core: TUI + scan + search
pip install -e ".[analysis]"           # + librosa: BPM/key/similarity
pip install -e ".[download,metadata]"  # + downloaders + MusicBrainz/Discogs
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
cratedig web             # launch the local web sample-diving panel
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
| arrows / click | preview the highlighted sample or download hit (uses `ffplay`) |
| `p` | play / stop the selected sample, or preview the selected download hit |
| `w` | render the interactive terminal waveform for the selected sample |
| `v` | open/sync the selected sample in the local web panel |
| `z` / `o` | waveform zoom in / out |
| `h` / `l` | waveform pan left / right |
| `j` / `k` | move waveform playhead left / right |
| `b` / `e` | mark waveform selection start / end |
| `g` | loop selected waveform region |
| `y` | clear waveform selection |
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

### API tokens

The Download mode needs credentials for the paid/private backends. See
`config.example.toml` for step-by-step instructions on getting tokens for:

- **FreeSound** (`sources.freesound.token`) — required for sample search/download.
- **Yandex Music** (`sources.yandex.token` or `token_file`) — required for track search/download. The old `yamdl.exe` flow is gone; we now use the `yandex-music` Python library directly.
- **YouTube** — no token; `pip install -e ".[download]"` for `yt-dlp` + `ffmpeg` on PATH.

Scan, analyze, classify, download, and waveform operations show live progress/status in a
multi-line TUI operation panel. Download and waveform jobs can run while analyze
is running; scan and analyze are intentionally mutually exclusive.

### Web panel

```powershell
cratedig web
```

The web panel opens at `http://127.0.0.1:8765` by default. It shows a path-based
library tree, Canvas stereo waveform, browser audio controls, file metadata,
tags, and analysis fields. In the TUI, press `v` on a selected sample to open the
same panel directly at `/?sample=<id>`.

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
cratedig web
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
`db/` · `scan/` · `audio/` · `search/` · `sources/` · `metadata/` · `tui/` · `web/`.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest
```

# cratedig

A local, terminal (TUI) fork of **Sononym**: index your sample library, search by
**BPM / key / mood / tags**, find acoustically **similar** samples, and **download**
new audio (YouTube, Yandex Music, FreeSound, Internet Archive) straight into the
library. SQLite-backed. For personal, local use.

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

`ffmpeg` must be on PATH for YouTube audio extraction and waveform rendering.
Without `ffmpeg`, YouTube downloads fall back to yt-dlp's native bestaudio file.
`ffplay` must be on PATH for TUI playback.

## Configure

```powershell
copy config.example.toml config.toml
```

Edit `config.toml` — set `library_dirs`, `download_dir`, and any API tokens.

## Use

```powershell
cratedig                 # launch the TUI
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
| arrows / click | preview the highlighted sample or download hit (uses `ffplay`) |
| `p` | play / stop the selected sample, or preview the selected download hit |
| `w` | render waveform preview for the selected sample (uses `ffmpeg`) |
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

## Layout

See [ARCHITECTURE.md](ARCHITECTURE.md). Source under `cratedig/`:
`db/` · `scan/` · `audio/` · `search/` · `sources/` · `metadata/` · `tui/`.

## Tests

```powershell
pip install -e ".[dev]"
pytest
```

# COMPACT.md — cratedig

## TL;DR
Local TUI fork of Sononym. Index sample library (SQLite), search by BPM/key/mood/tags,
similarity search (librosa features + cosine kNN), download new audio from YouTube/
Yandex/FreeSound/Archive into the library. Python 3.11+ / Textual. Personal use.

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config |
| db | ✅ | sqlite3, schema.sql, dataclasses, no ORM |
| scan | ✅ | walk+probe (soundfile→mutagen), sha1, category heuristics, upsert; `index_file()` for single-file |
| audio.features/similarity | ✅ | 58-dim vector, cosine top-k (numpy) |
| audio.analyzer | ✅ | BPM/key(KS profiles)/loudness — needs librosa |
| search.query | ✅ | parameterized SQL filters incl. category |
| index.py | ✅ | orchestration: scan_libraries/analyze_pending/classify_pending/find_similar |
| tui | ✅ | browse uses path-based tree rows (`t` reloads library tree); download/search/similar/duplicates remain flat work views; auto-preview; duplicate view `u`; classify `c`; multi-operation status panel; playback `p`/`x`; interactive waveform `w`; `v` opens/syncs selected sample in web panel |
| web | ✅ | `cratedig web` starts stdlib HTTP server on `127.0.0.1:8765` by default; static assets in `cratedig/web/static`; APIs: tree/sample/waveform/audio |
| sources.yandex | ✅ | yandex-music lib; search+download+auto-index live-tested |
| sources.youtube | ⚠️ | search works; download untested; ffmpeg extraction with native bestaudio fallback |
| sources.freesound | ✅ | live-tested; token set in config.toml; proxy-bypass session |
| sources.archive | ⚠️ | implemented, untested |
| sources.manager | ✅ | modes: `samples`→FreeSound, `tracks`→Yandex+YT fallback, `<name>`→direct |
| metadata (mb/discogs) | ⚠️ | providers written, NOT wired into TUI |

## Stack decisions
- Python + Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound +
  archive with combined fallback; scope = skeleton + working local-scan slice.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily — core runs without it.
- yandex-music v3.0.0 (`[download]` extra in pyproject.toml) — downloads mp3 directly,
  no ffmpeg needed for Yandex backend.
- yamdl.exe REMOVED — was interactive TUI binary, not a CLI subprocess.

## Gotchas
- ffmpeg required on PATH for YouTube extraction. Waveform decode uses ffmpeg first,
  then falls back to soundfile for formats it can decode when ffmpeg is unavailable.
- YouTube backend falls back to native yt-dlp bestaudio when ffmpeg is unavailable
  or `sources.youtube.audio_format = "native"`.
- ffplay required on PATH for TUI playback (`p` play/stop, `x` stop). When a waveform is
  loaded, `p` plays from the current playhead.
- TUI waveform preview is now an interactive DAW-like terminal panel, not a one-line
  decoration. `w` decodes full-file PCM into stereo min/max/RMS envelopes; lower panel
  is 13 rows. Keys: `z`/`o` zoom, `h`/`l` pan, `j`/`k` move playhead,
  `b`/`e` set selection, `g` loop selected region, `y` clear.
- Local web sample-diving panel: `cratedig web` serves static HTML/CSS/JS and APIs for
  path-based library tree, sample metadata, stereo waveform JSON, and audio streaming.
  UI shows Canvas stereo waveform, audio controls, metadata/analysis/tags inspector.
- TUI `v` starts/reuses a background web server and opens/syncs the selected sample in
  the web panel, e.g. `http://127.0.0.1:8765/?sample=<id>`.
- TUI auto-previews highlighted rows via ffplay. Browse rows play local files;
  download rows play direct backend preview URLs when present (FreeSound has
  `SearchHit.extra["preview"]`; Yandex/YouTube usually do not).
- TUI has a dedicated multi-operation panel under the results table (`scan`,
  `analyze`, `classify`, `download`, `waveform`). `scan`/`analyze`/`classify` share a guarded
  `library` worker group and are mutually exclusive; `download` and `waveform`
  use separate worker groups and can run while analysis is active. Download
  reports phases via `DownloadManager.fetch_hit(..., progress=...)`.
- Librosa `n_fft=... too large for input signal` warnings on very short files are
  non-fatal and suppressed inside `audio.analyzer.analyze()`.
- Duplicate detection is wired into TUI via `u`, using `samples.file_hash`; `r`
  returns to the normal library view.
- Auto-category classification is filename/path heuristic based. New scan/download
  rows get `samples.category`; existing rows can be backfilled with TUI `c` or
  `cratedig classify`.
- Current local DB backfilled with `cratedig classify`: 830 files classified out
  of 848 candidates after batch-update optimization.
- SQLite connection is shared by TUI worker threads; all direct `db.conn` access
  must be guarded by `Database.lock` to avoid `InterfaceError: bad parameter or
  other API misuse` during scan/analyze/download.
- Windows console default codec cp1251 breaks Cyrillic/Unicode prints in headless scripts —
  use `$env:PYTHONIOENCODING="utf-8"` before running.
- FreeSound token-only = HQ mp3 PREVIEWS (full originals need OAuth2, skipped).
- FreeSound API form needs URL + Callback URL — irrelevant for token auth; put any
  valid value (http://localhost). Use "Client secret/Api key" (NOT client id) as token.
- Local VPN proxy (127.0.0.1:2080) resets TLS to freesound.org → silent empty results.
  Fix: freesound.py uses `requests.Session(trust_env=False)` to bypass system proxy
  + 1 retry on ConnectionError. manager.search() now returns backend err in `used`
  instead of swallowing exceptions (was the cause of mystery "no hits").
- example/yamdl/token.txt holds a real Yandex token (gitignored); `sources.yandex.token`
  or `token_file` in config.toml also accepted.
- Git repo initialized at `D:\AI Projects\Sononym_fork` on branch `main`; DB at
  `data/cratedig.db` should stay untracked via `.gitignore`.
- Discogs PyPI pkg = `python3-discogs-client` (NOT `python-discogs-client`); import
  name still `discogs_client`.

## Verification
- `python -m compileall cratedig` passed.
- `.\.venv\Scripts\python.exe -m pytest` passed: 37 tests.
- Web panel verified at `http://127.0.0.1:8765/?sample=5410`: tree/metadata/audio URL
  worked and Canvas rendered stereo waveform after soundfile fallback fix.

## Next session TODO
- Live-test YouTube download with ffmpeg visible on PATH.
- FreeSound search live-tested OK; still verify preview DOWNLOAD + auto-index end-to-end.
- Live-test interactive TUI waveform/playhead/selection playback on real mp3/wav files
  with ffplay visible on PATH; hnswlib ANN for large libraries.

## Authoritative files
- ARCHITECTURE.md — full design + roadmap
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound/Archive into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config |
| db | ✅ | sqlite3, schema.sql, dataclasses, no ORM; `samples.waveform_preview` migrated for TUI row thumbnails; `favorites` + `recent_folders` tables added; `toggle_favorite(kind, ref) -> bool` atomic via single RLock acquisition |
| scan | ✅ | walk+probe (soundfile→mutagen), sha1, category heuristics, upsert; prunes deleted files under scanned roots on re-scan; `index_file()` for single-file |
| audio.features/similarity | ✅ | 193-dim Sononym-like weighted vector: log-mel/MFCC/contrast/chroma/envelope/scalars; cosine top-k skips stale dims |
| audio.analyzer | ✅ | BPM/key(KS profiles)/loudness + compact waveform preview — needs librosa |
| search.query | ✅ | parameterized SQL filters incl. category |
| index.py | ✅ | orchestration: scan_libraries/analyze_pending/classify_pending/find_similar |
| tui | ✅ | browse uses real collapsible Textual Tree (folders + ★ Favorites branch); breadcrumb + #contents DataTable per folder; `b` toggles favorite; opening folder calls touch_recent_folder; download/search/similar/duplicates remain flat work views; auto-preview; `u` duplicates; `c` classify |
| tui.browser | ✅ | pure helper `build_folder_tree(samples, roots)` → `dict[str, FolderNode]`; shared by TUI + GUI (consistent DB favorites across UIs) |
| gui | ✅ | PySide6 desktop: folder tree + sample table + waveform + play/stop; auto-plays on selection (keyboard nav + mouse via currentCellChanged); signed symmetric waveform (averaged lo/hi channels); Download dock (search/download/preview/auto-index, hidden by default, toggled via toolbar); IndexWorker on QThread; reuses backend; favorites toggle (★ Favorite toolbar action + `F` shortcut; checkable, reflects/enables per selected sample) via worker.request_toggle_favorite → db.toggle_favorite → request_reload; pure `logic.tree_rows`/`compute_peaks`/`hit_rows`/`is_sample_favorite` |
| gui.download_pane | ✅ | DownloadPane widget: query field + mode combo (samples/tracks/youtube/yandex/freesound/archive) + Search + results table + Download/Preview; emits search_requested/download_requested/preview_requested; Enter or double-click triggers search/download |
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
- ffplay required on PATH for TUI playback (`p` play/stop, `x` stop), GUI playback,
  and GUI preview of download hits (ffplay handles http URLs directly).
- TUI waveform is a stored row thumbnail: `audio.analyzer.analyze()` writes
  `samples.waveform_preview` (TEXT block-art; unplottable in Qt — GUI decodes peaks).
- Similarity vector is 193-dim. Re-run `cratedig analyze` after this change; rows
  with old `feature_dim` are treated as pending, mixed-dim candidates skipped.
- Re-running scan prunes stale sample rows under each scanned library root.
- Folder keys from tui.browser build_folder_tree are root-relative slash-joined
  strings (e.g. "packs/drums"); shared by TUI + GUI so DB favorites resolve across
  both UIs. Out-of-root samples fall back to "other/<basename>".
- `touch_recent_folder` seq is SELECT-MAX-then-INSERT (TOCTOU) — make atomic if
  concurrent load matters.
- `_tree_rows` in tui/app.py is kept (still imported/tested) but is now unused by
  browse mode — dead-code candidate.
- TUI auto-previews highlighted rows via ffplay. Browse rows play local files;
  download rows play direct backend preview URLs when present.
- TUI has a multi-operation panel (`scan`/`analyze`/`classify` mutually exclusive;
  download uses a separate worker group).
- Librosa `n_fft=... too large for input signal` warnings on very short files are
  non-fatal and suppressed inside `audio.analyzer.analyze()`.
- SQLite connection is shared by TUI worker threads; all direct `db.conn` access
  must be guarded by `Database.lock`. GUI IndexWorker uses the same shared Database.
- Windows console default codec cp1251 breaks Cyrillic/Unicode prints in headless
  scripts — use `$env:PYTHONIOENCODING="utf-8"` before running.
- FreeSound token-only = HQ mp3 PREVIEWS (full originals need OAuth2, skipped).
- FreeSound API form needs URL + Callback URL — irrelevant for token auth; put any
  valid value (http://localhost). Use "Client secret/Api key" (NOT client id) as token.
- Local VPN proxy (127.0.0.1:2080) resets TLS → silent empty results AND breaks
  `pip install` (ProxyError 10054). Fix: freesound.py uses `requests.Session(trust_env=False)`;
  for pip clear `$env:HTTP_PROXY/HTTPS_PROXY=""` + `--proxy ""`.
- example/yamdl/token.txt holds a real Yandex token (gitignored); `sources.yandex.token`
  or `token_file` in config.toml also accepted.
- Git repo initialized at `D:\AI Projects\Sononym_fork` on branch `main`; DB at
  `data/cratedig.db` should stay untracked via `.gitignore`.
- Discogs PyPI pkg = `python3-discogs-client` (NOT `python-discogs-client`); import
  name still `discogs_client`.
- PySide6 is a `[gui]` optional extra, lazily imported — core/TUI run without it.
- PySide6 installed in .venv; GUI window smoke-tested (constructs+shows+worker thread OK). Launch: `cratedig gui`.
- GUI waveform peaks decoded on demand via `playback.decode_waveform_data` + pure `compute_peaks`; `waveform_preview` text field is unplottable directly in Qt.
- GUI waveform channels are averaged as signed lo/hi pairs so the painted waveform is
  symmetric about center. Previous collapse to magnitude caused top-half-only clipping.
- GUI playback reuses ffplay AudioPlayer (not QMediaPlayer).
- GUI Download dock uses `_search_seq` guard to drop stale search results when a new
  query is fired before the previous one completes. Download auto-indexes via `request_reload()`.
- GUI download live-test (real backends, network) still pending manual verification.
- `db.toggle_favorite` re-enters the same RLock (reuses is/add/remove_favorite internally); safe because Python's RLock is reentrant per-thread.

## Verification
- `python -m compileall cratedig` ok.
- `python -m pytest` passed: 100 tests (was 93; +7: 4 toggle_favorite_* in tests/test_database.py, 3 TestIsSampleFavorite in tests/test_gui_logic.py). Headless worker smoke (offscreen Qt) round-trips toggle and emits treeReady.

## Next session TODO
- GUI next stages: file/dir mgmt, dups, tagging, similarity UI.
- Modernize GUI styling (Foleyard-like) once feature set lands.
- Live-test YouTube download with ffmpeg visible on PATH.
- FreeSound: verify preview DOWNLOAD + auto-index end-to-end.
- GUI download live-test (real backends + network) — not covered by automated tests.
- Consider hnswlib ANN for large libraries.
- Make touch_recent_folder seq atomic (currently SELECT-MAX-then-INSERT, TOCTOU).
- Remove `_tree_rows` dead code from tui/app.py.

## Authoritative files
- ARCHITECTURE.md — full design + roadmap; "GUI skeleton (PySide6)" section for GUI decisions
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

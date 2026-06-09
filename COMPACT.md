# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config (stdlib `tomllib`, read-only, frozen); `_default_config_path()` uses user data dir when frozen; `_seed_config_if_frozen()` copies bundled `config.example.toml` → user dir on first run; non-frozen behavior unchanged |
| config_writer | ✅ | **tomlkit** comment-preserving writer; `load_document`/`write_document` (atomic temp+`os.replace`, `newline=""` byte round-trip); seeds from `config.example.toml` if target missing; mutators set paths/audio.extensions/metadata/sources tokens |
| paths | ✅ | `cratedig/paths.py`; `is_frozen()`, `user_data_dir()` (platformdirs — Win `%APPDATA%\cratedig`, mac `~/Library/Application Support/cratedig`, Linux `~/.local/share/cratedig`), `resource_root()`/`resource_path(name)` (`sys._MEIPASS` when frozen else repo root), `bundled_binary(name)`, `ffmpeg_path()`/`ffplay_path()` (bundled-or-`shutil.which`) |
| db | ✅ | sqlite3, schema.sql read via `_read_schema()` (importlib.resources with `resource_path` fallback for frozen); dataclasses; `crates`+`crate_samples`; all schema migrations idempotent |
| scan | ✅ | walk+probe, sha1, upsert; sets category+class from filename; prunes deleted files; `scan_libraries` also scans `paths.saved_dir`; scan builds desktop mono waveform PCM cache best-effort |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude; `aspect_topk`+`cosine_topk` |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` for audio fallback |
| audio.playback | ✅ | `decode_waveform_mono_samples` true mono float32 PCM via ffmpeg with soundfile fallback; `AudioPlayer.play` supports `start_sec`/`duration_sec`/`gain_db`; `ffmpeg_path()`/`ffplay_path()` from `..paths` (bundled-or-PATH); `import shutil` removed |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; DSP tags; mutually-exclusive pairs enforced |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`; `detect_transients` per-frame PEAK+RMS hybrid |
| health | ✅ | `HealthReport` dataclass + `library_health` + `missing_sample_ids` + `format_report`; GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan` |
| index.py | ✅ | `analyze_pending`/`classify_pending`/`tag_pending`/`find_similar_aspects`/`scan_libraries` |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI+GUI |
| gui | ✅ | Global dark redesign; `run_gui` sets Windows AppUserModelID; all subsystems wired |
| gui.theme | ✅ | `apply_app_theme(app)` global dark palette+QSS; `app_icon()` paints branded ▣ mark programmatically |
| gui.toast | ✅ | `ToastManager(host)` + `_Toast(QFrame)` — dark cards; levels info/ok/error; QSS braces must stay balanced |
| gui.health_panel | ✅ | Grafana-style `_StatTile` severity-coloured cards; overall status banner pill |
| gui.ab_dialog | ✅ | `ABCompareDialog(QDialog)` modal A/B compare; loudness leveling wired |
| gui.logic | ✅ | `backend_badge`; `ABState`; `match_als_samples`; `compute_peaks`; `ab_level_gain_db`; `filter_samples` |
| gui.platform_files | ✅ | `reveal_in_file_manager(path)` cross-platform |
| gui.sample_table | ✅ | 9 cols; Tags visible; Similarity hidden until scores shown; drag emits file URLs; context menu |
| gui.metadata_panel | ✅ | compact read-only widget; mutagen easy tags; seq-guarded |
| gui.settings_dialog | ✅ | 3-tab `SettingsDialog`; signals `preferences_changed`/`config_written`/`auto_preview_changed` |
| gui.settings_tabs | ✅ | `_keys.py` (QSettings key constants + `DEFAULTS` + `TYPES`); preferences/project-config/paths tabs |
| gui.simpler_pane | ✅ | Draggable region+fade handles; loop/reverse toggles; ADSR overlay; `_KnobDial` |
| gui.worker | ✅ | all request/signal pairs; `request_delete` → recycle bin for saved/edit files |
| gui.download_pane | ✅ | QProgressBar 4 states; `set_backend(source)`; settings param; auto-preview |
| gui.als_explorer | ✅ | embedded page; 3-tab Instruments/Plugins/Tracks + optional Library Match; drag&drop .als |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L |
| sources.base | ✅ | `safe_filename`+`unique_path`; strips Windows-illegal chars, caps 120 chars |
| sources.yandex | ✅ | `<TRACK> - <ARTIST>.mp3` via `safe_filename`+`unique_path` |
| sources.youtube | ✅ | `_opts` sets yt-dlp `ffmpeg_location` to `bundled_binary("ffmpeg")` when frozen; `safe_filename`+`unique_path` |
| sources.freesound | ✅ | proxy-bypass session; `safe_filename`+`unique_path` |
| sources.manager | ✅ | samples→FreeSound; tracks→merged Yandex+YouTube; MusicBrainz/Discogs incremental-cache ranking |
| metadata (mb/discogs) | ✅ | core wiring done; incremental `metadata_cache`; `rank_track_hits(..., force_live=False)` |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily. **Bundled in release builds** (core feature).
- yandex-music v3.0.0 (`[download]` extra) — mp3 direct, no ffmpeg needed for Yandex.
- yamdl.exe REMOVED. Archive.org backend REMOVED (`sources/archive.py` deleted).
- **Packaging**: distribution decided as **onedir** (NOT onefile). Windows: **Inno Setup installer**. macOS: `.app` bundle in `.dmg`. Build per-OS; CI = GitHub Actions matrix. See `PACKAGING.md`.
- New runtime dep: `platformdirs>=4.0`. New `[build]` extra: `pyinstaller>=6.0` + `pillow>=10.0`.

## Packaging status
| target | status | note |
|---|---|---|
| Windows onedir build | ✅ DONE | `dist/cratedig/` ~572 MB, exe 29 MB; librosa/numba/llvmlite bundle OK on Python 3.13.5 |
| Windows Inno installer | ✅ DONE | `dist/cratedig-setup-0.1.0.exe` 160 MB; `ISCC.exe` at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` |
| macOS `.app` + `.dmg` | ✅ DONE | built on Apple Silicon (arm64): `dist/cratedig.app` 470 MB (main exe arm64), `dist/cratedig-0.1.0.dmg` 181 MB (drag-to-Applications, hdiutil fallback — `create-dmg` not installed). Smoke-tested: seeds `~/Library/Application Support/cratedig/config.toml`+`data/cratedig.db` (13 tables), launches no crash. One command: `bash packaging/macos/build_all.sh 0.1.0` |
| GitHub Actions CI | ⏳ written, not run | `.github/workflows/release.yml` matrix (windows-latest, macos-14, macos-13); fires on tag |

## Gotchas
- **Frozen user-data seeding**: first run copies `config.example.toml` → `%APPDATA%\cratedig\config.toml`; DB defaults to `%APPDATA%\cratedig\data\cratedig.db`. Non-frozen path unchanged.
- **Bundled ffmpeg/ffplay live in `dist/cratedig/_internal/`** (onedir); `bundled_binary()` checks `_MEIPASS`, exe dir, `_MEIPASS/bin`. ffmpeg binaries staged in `packaging/bin/windows/` (and `packaging/bin/macos/`) are git-ignored — `build_all.sh` fetches them.
- **macOS ffmpeg/ffplay from evermeet.cx are x86_64-only** (`Mach-O ... x86_64`), so on the arm64 `.app` they run via **Rosetta 2** (must be installed on target Mac — first x86 launch prompts to install it). evermeet ships no arm64 static build; for a pure-arm64 bundle you'd need to build ffmpeg from source or source arm64 binaries elsewhere. Acceptable for personal use.
- **evermeet.cx download is flaky** — `curl: (56) Recv failure` mid-transfer killed the first build (`set -e`). `build_all.sh` curl now uses `--retry 5 --retry-delay 3 --retry-all-errors`. Re-running the script is safe: `if [[ ! -x ]]` guard skips already-fetched binaries; pip step is a fast no-op when deps satisfied.
- In the `.app`, PyInstaller stages bundled binaries in BOTH `Contents/Resources/` and `Contents/Frameworks/` (ffmpeg, ffplay present in both).
- **Inno Setup location**: `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (winget install). Not on PATH by default — CI script uses full path.
- `sources/youtube.py`: `shutil.which` boolean check kept for test compat; `ffmpeg_location` yt-dlp opt set from `bundled_binary("ffmpeg")` when frozen.
- `audio/playback.py`: `import shutil` removed (was unused after `ffmpeg_path()`/`ffplay_path()` swap); tests monkeypatch `shutil.which` at the global `shutil` level which the resolver calls internally — still passes.
- numba/llvmlite: benign `tbb12.dll` not-found warning on Windows frozen build; numba falls back to workqueue threading — harmless.
- ffmpeg required on PATH (non-frozen) for YouTube extraction and waveform decode (falls back to soundfile).
- ffplay required on PATH (non-frozen) for TUI/GUI playback and GUI download preview.
- Desktop waveform previews use a mono PCM cache at `cfg.paths.db.parent / "waveform_cache"` keyed by sample `file_hash`.
- Similarity vector 193-dim; re-run `cratedig analyze` after vector-dim changes; mixed-dim candidates skipped.
- `MainWindow._similar_requested = Signal(int,int,int,object)` — aspects list as Python object via QueuedConnection.
- SQLite connection shared by threads; all `db.conn` access must be guarded by `Database.lock`.
- Windows console cp1251 breaks Unicode — use `$env:PYTHONIOENCODING="utf-8"`.
- FreeSound token = HQ mp3 previews only (full originals need OAuth2).
- Local VPN proxy (127.0.0.1:2080) breaks TLS → empty results. freesound.py uses `trust_env=False`.
- Toast QSS braces: only f-string lines use `{{`/`}}`; literal stylesheet lines use single `{`/`}`.
- `cfg.metadata` is a plain `dict` — read keys with `.get(...)`, NOT `getattr`.
- `paths.saved_dir` is required on `Paths` dataclass — direct `Paths(...)` construction in tests must pass it.
- ALS Explorer `_LANG` is module-global; single-panel-instance contract.
- `tests/test_settings_dialog.py` teardown: pass `tempfile.gettempdir()` (str path) to `setPath` — PySide6 6.11.1 signature change.
- tomlkit is a runtime dep (config_writer); config.py stays on stdlib tomllib for reads.

## Verification
- `python -m compileall cratedig` ok.
- Full `python -m pytest -q`: **755 passed, 0 failed, 0 errors** (was 746; +8 `tests/test_paths.py`, +1 elsewhere).
- `cratedig health` and `cratedig dedup` smoke-run OK on real 653-sample DB.
- Frozen app launched on Windows: seeded `%APPDATA%\cratedig\config.toml`, created `data\cratedig.db`, window stable.
- macOS `.app` smoke-tested on Apple Silicon: seeded `~/Library/Application Support/cratedig/config.toml` (from `config.example.toml`) + `data/cratedig.db` (all 13 tables, 0 samples), process alive no crash (only benign IMKClient input-method log lines). DMG mounts at `/Volumes/cratedig` with `cratedig.app` + `Applications` symlink.

## macOS build — DONE (2026-06-09, Apple Silicon)
Both desktop targets now built & smoke-tested: Windows (onedir + Inno installer) and
macOS (`.app` + `.dmg`). Build command (one shot from repo root, unsigned, personal use):
  `bash packaging/macos/build_all.sh 0.1.0`
  (venv → pip install `.[gui,analysis,download,metadata,build]` → fetch ffmpeg →
   render_icons.py [.icns via iconutil] → pyinstaller cratedig.spec → make_dmg.sh)
Outputs: `dist/cratedig.app` (470 MB) + `dist/cratedig-0.1.0.dmg` (181 MB) — both
git-ignored (`dist/`); ship via GitHub Releases, do NOT commit. No new source files
needed this session — existing packaging code worked unchanged; only fix was adding
`curl --retry` to `build_all.sh` (flaky evermeet download). render_icons.py
deterministically regenerates `packaging/cratedig.{icns,ico}` + `packaging/icons/*.png`
(same content). numba/llvmlite PyInstaller hook worked on macOS arm64 (Python 3.13.7),
same as Windows — no hidden-import tweaks needed.
First launch on a fresh Mac: right-click→Open, or
`xattr -dr com.apple.quarantine /Applications/cratedig.app` (unsigned). Needs Rosetta 2
for the bundled x86_64 ffmpeg/ffplay (see Gotchas).

## Next session — candidates (build phase complete)
- Exercise CI (`.github/workflows/release.yml`) on a pushed `v*` tag (still un-run).
- If a pure-arm64 mac bundle is wanted: replace evermeet x86_64 ffmpeg/ffplay with
  arm64 binaries (build from source / brew arm64), re-run `build_all.sh`.
- Otherwise resume feature work — both installers are shippable.

## Backlog
- Exercise CI workflow (`.github/workflows/release.yml`) end-to-end on a pushed `v*` tag.
- Optional: code-signing (Windows EV cert) and macOS notarization (Apple Dev ID $99/yr).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).
- Settings restore-last-folder: only `browser/last_folder` persisted.

## Authoritative files
- `ARCHITECTURE.md` — full design + roadmap
- `PACKAGING.md` — distribution/packaging plan: onedir + Inno Setup (Windows) + `.app`/`.dmg` (macOS)
- `README.md` — end-user install guide (installer, first run, data locations, feature tour, troubleshooting)
- `README.dev.md` — developer setup guide (preserved old README)
- `docs/SETTINGS_DESIGN.md` — Settings dialog + config_writer blueprint
- `cratedig/db/schema.sql` — data model
- `config.example.toml` — all settings + OAuth token setup instructions

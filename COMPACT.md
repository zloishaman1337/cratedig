# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).
Releases follow **UPDATE_RULES.md** — **two-tier ONLINE update model** (since 0.4.0):
most releases ship a small **delta** (code-only); full installer only when deps/Python/
ffmpeg/assets change. Tier decided automatically by diffing the new onedir against the
committed release manifest (`packaging/release-manifests/`). **Delta delivery is per-OS:**
Windows delta = small Inno update installer `cratedig-update-<ver>.exe` (downloaded+launched
in-app on Win); macOS delta = `.zip` applied in-app via **Help → "Apply update from file…"**
(`cratedig/updater.py`) + bash restart helper. **App checks for updates automatically on
startup** (frozen builds, GitHub Releases feed, silent on failure/up-to-date, dialog only
when newer). Every asset verified by minisign. **0.6.0: first release shipping delta
over-the-wire** — build publishes full+delta+meta every code-only release; client
fetches+verifies `release-meta-<ver>.json` and picks delta or full automatically.

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config (stdlib `tomllib`, read-only, frozen); `_default_config_path()` uses user data dir when frozen; `_seed_config_if_frozen()` copies bundled `config.example.toml` → user dir on first run; `[plugins].scan_dirs` added (0.5.0) |
| config_writer | ✅ | **tomlkit** comment-preserving writer; `resolve_config_path()` delegates to `config._default_config_path()`; `set_plugin_scan_dirs` added (0.5.0) |
| paths | ✅ | `cratedig/paths.py`; `is_frozen()`, `user_data_dir()` (platformdirs), `resource_root()`/`resource_path(name)`, `bundled_binary(name)`, `ffmpeg_path()`/`ffplay_path()` |
| db | ✅ | WAL mode; `upsert_sample(..., commit=True)`; `Database.commit()` for batch flush; `all_samples(limit: int\|None)`; `tags_for_all() -> dict[int, list[str]]` |
| scan | ✅ | `scan_directory` parallelized via `ThreadPoolExecutor`; DB upserts batched; prunes deleted files; builds waveform PCM cache |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS`; `aspect_topk`+`cosine_topk`; `extract_features(path, sr, y=None)` |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` |
| audio.playback | ✅ | `decode_waveform_mono_samples` true mono float32 PCM via ffmpeg; `AudioPlayer.play` supports `start_sec`/`duration_sec`/`gain_db` |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; mutually-exclusive pairs enforced |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`; `detect_transients` |
| health | ✅ | `HealthReport` dataclass + `library_health` + GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan` |
| index.py | ✅ | `analyze_pending`/`tag_pending` parallelized; batched `executemany`; decode-once reuses buffer |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates |
| gui | ✅ | Global dark redesign; all subsystems wired |
| gui.main_window | ✅ | **0.6.0**: 3 stacked pages (0 Samples · 1 Project Checker · 2 Health); 9 per-DAW pages collapsed into ONE detect-mode `AlsExplorerPanel`; `self._checker_panels=[self._project_checker]`; `_daw_panels`/`_als_panel`/per-DAW nav removed; "Convert…" button in Project Checker toolbar |
| gui.simpler_pane | ✅ | **0.5.0**: `_WaveCanvas.paintEvent` blits cached static QPixmap; playhead drawn live only; mip peak pyramid for envelope |
| gui.als_explorer | ✅ | **0.6.0**: `detect=True` mode — resolves parser per-file by extension in `_resolve_detect`; updates title to "Project Checker — \<DAW\>"; stores `_loaded_path`/`_source_format`; `_on_convert_clicked` wired |
| gui.convert_dialog | ✅ | **NEW 0.6.0** `ConvertDialog` — target dropdown (Reaper/Ableton/AAF) + 5 transfer checkboxes + output path picker |
| gui.sample_table | ✅ | **0.6.0**: `set_samples` resets current cell (`setCurrentCell(-1,-1)`) inside blocked region so re-clicking same row after repopulate fires preview |
| gui.update_check | ✅ | **0.6.0**: `UpdateDownloadThread` fetches+verifies `release-meta-<ver>.json`, calls `choose_tier`, downloads delta when eligible else full; `_on_update_downloaded` branches by suffix (`.exe`→`os.startfile`+quit, `.dmg`→`apply_dmg_update`, `.zip`→`apply_update`) |
| gui.worker | ✅ | `request_reload()` uses `tags_for_all()` (batched); `request_plugin_scan` slot + `pluginIndexReady` signal (0.5.0) |
| updater | ✅ | **0.6.0**: adds `ReleaseMeta`, `build_release_meta`, `parse_release_meta`, `choose_tier(meta,current,release,os)`, `fetch_release_meta` (downloads+minisign-verifies the sidecar), `RELEASE_META_TEMPLATE`. All prior I/O helpers retained. `GITHUB_REPO="zloishaman1337/cratedig"` hardcoded. `MINISIGN_PUBKEY` embedded (key id 54F217219B866BE6). |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; `_match_plugin` delegates to `scanner.match_name` |
| plugins.scanner | ✅ | **0.5.0** `cratedig/plugins/scanner.py`: `standard_plugin_dirs`, `scan_installed`, `match_name`/`match_installed`, `load_or_scan`; disk cache at `user_data_dir()/plugin_index.json` |
| projects_fmt.detect | ✅ | **NEW 0.6.0** `cratedig/projects_fmt/detect.py` — `REGISTRY: dict[ext,FormatSpec]`, `parser_for(path)`, `file_filter()`, `ALL_EXTS`; single source of extension→parser dispatch |
| projects_fmt | ✅ | **0.5.2**: common/als/bitwig/nuendo/reaper/flstudio/studioone/logic/protools parsers; `to_checker_data`, `resolve_samples_on_disk` |
| convert | ✅ | **NEW 0.6.0** `cratedig/convert/` — `ir.py` (`ProjectIR`/`TrackIR`, `ir_from_checker_data`), `options.py` (`ConvertOptions`), `samples.py` (`gather_samples`), `writers/{reaper,ableton,aaf}.py`. Targets: `.RPP`, `.als` (gz-XML), `.aaf` (pyaaf2). Fidelity = metadata + sample file copies only (no plugin state/automation/audio). |
| sources.* | ✅ | youtube/yandex/freesound/manager; `safe_filename`+`unique_path`; `ffmpeg_location` yt-dlp opt from `bundled_binary` when frozen |
| metadata (mb/discogs) | ✅ | incremental `metadata_cache`; `rank_track_hits(..., force_live=False)` |
| make_manifest.py | ✅ | **0.6.0**: adds `emit-release-meta` subcommand; build scripts install `.[gui,analysis,download,metadata,convert,build]` |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily. Bundled in release builds.
- **NEW 0.6.0**: `pyaaf2>=1.7` in new `[convert]` extra. Pure-Python — PyInstaller freezes it into `cratedig.exe`'s PYZ (not loose `_internal` files); `cratedig.spec` adds `collect_data_files("aaf2")` + `collect_submodules("aaf2")`.
- **Packaging**: onedir (NOT onefile). Windows: Inno Setup installer. macOS: `.app` in `.dmg`. See `PACKAGING.md`.

## Packaging status
| target | status | note |
|---|---|---|
| Windows onedir build | ✅ DONE 0.6.0 | smoke-launched alive 8s, clean stop |
| Windows installer | ✅ DONE 0.6.0 | `cratedig-setup-0.6.0.exe` (full, 169MB) + `cratedig-update-0.6.0.exe` (delta, 32MB) + `release-meta-0.6.0.json`; all signed+published; tier auto=delta; both shipped |
| Release manifests | ✅ win 0.6.0 | `cratedig-0.6.0-win.json` committed; mac pending |
| Windows GitHub release | ✅ published 0.6.0 (signed) | https://github.com/zloishaman1337/cratedig/releases/tag/0.6.0 |
| macOS `.app` + `.dmg` | ⏳ PENDING 0.6.0 | see macOS HANDOFF below |
| GitHub Actions CI | ⏳ written, not run | `.github/workflows/release.yml` matrix; fires on tag |

## Gotchas
- **config_writer path**: `resolve_config_path()` MUST mirror `config.load_config` path resolution.
- **Frozen user-data seeding**: first run copies `config.example.toml` → `%APPDATA%\cratedig\config.toml`; DB defaults to `%APPDATA%\cratedig\data\cratedig.db`.
- **Bundled ffmpeg/ffplay/minisign live in `dist/cratedig/_internal/`** (onedir); `bundled_binary()` checks `_MEIPASS`, exe dir, `_MEIPASS/bin`.
- **macOS ffmpeg/ffplay**: `build_all.sh` fetches arm64 static builds from osxexperts.net (FFmpeg 8.1). evermeet.cx (x86_64-only) is the old source.
- In the `.app`, PyInstaller stages bundled binaries in BOTH `Contents/Resources/` and `Contents/Frameworks/`.
- **Inno Setup location**: `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (winget install). Not on PATH by default.
- **DB is WAL mode** since 0.2.0 — `-wal`/`-shm` sidecar files appear next to the db.
- **Do NOT switch scan/analyze ThreadPoolExecutor to ProcessPoolExecutor** — monkeypatching in tests won't reach spawned processes.
- **Per-user installer (0.2.0+)**: `PrivilegesRequired=lowest`; existing per-machine installs must be uninstalled first. User data in `%APPDATA%` preserved.
- numba/llvmlite: benign `tbb12.dll` not-found warning on Windows frozen build — harmless.
- Toast QSS braces: only f-string lines use `{{`/`}}`; literal stylesheet lines use single `{`/`}`.
- `cfg.metadata` is a plain `dict` — read keys with `.get(...)`, NOT `getattr`.
- `paths.saved_dir` is required on `Paths` dataclass — direct `Paths(...)` construction in tests must pass it.
- `tests/test_settings_dialog.py` teardown: pass `tempfile.gettempdir()` (str path) to `setPath` — PySide6 6.11.1 signature change.
- tomlkit is a runtime dep (config_writer); config.py stays on stdlib tomllib for reads.
- **Version is dual-SSOT-mirrored**: `pyproject.toml` (authoritative) AND `cratedig/__init__.__version__` (runtime). Bump BOTH together.
- **pytest lives in `[dev]` extra** — build venv lacks it. Run `pip install -e ".[dev]"` before pytest.
- **Updater manifest hash**: `updater.manifest_sha256` (canonical JSON, sorted keys) — never hand-roll a second hash.
- **Baseline trap (0.4.0)**: 0.2/0.3 installs have no update checker — distribute full installers manually.
- **minisign.key in repo root, gitignored**. Back it up and copy to mac before macOS session. **Password auto-loads from gitignored `.env` (`MINISIGN_PASSWORD=…`)** in both build scripts; env var wins if already set. Agent must read `.env`, never ask the user.
- **GITHUB_REPO hardcoded** as `"zloishaman1337/cratedig"` — do not auto-detect from git remote.
- **PyInstaller rewrites `base_library.zip` every build** (churned sha256, identical size) — allowlisted in `make_manifest.py` `DEFAULT_APP_PATHS` so it doesn't force tier=full on code-only diffs.
- **`apply_dmg_update` is macOS-only** — raises immediately on non-Darwin; off-platform guard tested in `tests/test_updater_online.py`.
- **Delta-over-the-wire is wired (0.6.0)**: client fetches+verifies `release-meta-<ver>.json`, picks delta when `current_version ∈ delta_from` and a delta asset exists, else full. Build publishes full+delta+meta every code-only release. 0.5.2 clients lack tier-selection logic and fall back to fetching the full installer.
- **pyaaf2 is pure-Python → PyInstaller freezes it into `cratedig.exe`'s PYZ, NOT loose `_internal/aaf2` files.** Verify bundling with `python -m PyInstaller.utils.cliutils.archive_viewer --list --recursive dist\cratedig\cratedig.exe | findstr aaf2`.
- **0.4.1→0.5.0 auto-update was broken** — fixed in 0.5.1. Auto-update only reliable from 0.5.1+. Distribute 0.5.0+ full installers manually to pre-0.5.1 users.
- **Pre-existing test failure**: `test_config_writer.py::test_round_trip_no_mutation_preserves_bytes` fails due to CRLF/LF mismatch in `config.example.toml` working tree — not a regression.
- **Large DAW test fixtures** (`projects/` — Logic ~82MB, Studio One ~75MB, Cubase ~11MB, flp/ptx/rpp) intentionally LEFT UNTRACKED; real-project tests are `skipif`-guarded on their presence.
- **Logic AU plugin names truncated to 11 chars** in `ProjectData` reversed-4cc markers — inherent to source data, not a parser bug.
- **Build venv is Python 3.13 on macOS** (confirmed 0.5.2 session).

## Verification (0.6.0)
- Full pytest: **980 passed, 1 failed** (pre-existing CRLF artifact — not a regression). +25 tests vs 0.5.2.
- New test files: `tests/test_convert.py`, `tests/test_projects_fmt_detect.py`, `tests/test_updater_delta.py`. Extended: `test_als.py` (detect-mode routing, 3 stacked pages), `test_gui_logic.py` (crate re-click selection).
- Frozen 0.6.0 smoke-launched OK. aaf2 confirmed inside `cratedig.exe` PYZ via archive_viewer. All 3 assets minisign-VERIFIED (trusted comment "cratedig 0.6.0").
- Live feed: `fetch_latest_release()`→0.6.0; `is_newer(0.6.0,0.5.2)`=True; `select_asset(win,full)`+`select_asset(win,delta)` both resolve. Source commit `ac9d6b6` on main.

## macOS HANDOFF — PENDING
- version: 0.6.0
- tier: full (build auto-tier will say delta since pyaaf2 rides in the app exe); ship full+delta+meta. 0.5.2 mac clients fetch the full .dmg.
- windows update: DONE (`cratedig-setup-0.6.0.exe` + `cratedig-update-0.6.0.exe` + `release-meta-0.6.0.json`, signed+published)
- macos update: PENDING
- source ref: `ac9d6b6` (branch main)
- changed files: see `git show ac9d6b6` — `cratedig/convert/**`, `cratedig/projects_fmt/detect.py`, `cratedig/gui/{als_explorer,convert_dialog,main_window,sample_table,update_check}.py`, `cratedig/updater.py`, `packaging/{cratedig.spec,make_manifest.py,macos/build_all.sh,windows/build_all.ps1}`, `pyproject.toml`, `tests/`
- new deps/assets: `pyaaf2>=1.7` (new `[convert]` extra; pure-Python, bundles into the app via `collect_submodules('aaf2')` in `cratedig.spec` — `build_all.sh` already installs the convert extra)
- build command: `bash packaging/macos/build_all.sh 0.6.0`
- notes: `build_all.sh` now always builds the full .dmg AND a delta .zip (when code-only) + signs/publishes release-meta. After build: `SIGN=1 PUBLISH=1 bash packaging/macos/build_all.sh 0.6.0`. Verify aaf2 bundled into the .app. Smoke-launch the .app.

## Backlog
- **0.4.0 distribute manually**: hand 0.4.0+ full installers to existing 0.2/0.3 users — they have no update checker.
- Exercise CI workflow (`.github/workflows/release.yml`) end-to-end on a pushed `v*` tag.
- Optional: Windows EV code-signing cert and macOS notarization (Apple Dev ID $99/yr).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).

## Authoritative files
- `ARCHITECTURE.md` — full design + roadmap
- `PACKAGING.md` — distribution/packaging plan; §6 = macOS rebuild procedure; pointer → UPDATE_RULES.md
- `UPDATE_RULES.md` — authoritative release/update pipeline: two-tier ONLINE model (since 0.4.0)
- `packaging/release-manifests/` — per-release file-hash manifests; diff baseline for tier decision
- `cratedig/updater.py` — online feed constants + pure parsing + I/O layer + macOS apply layer + ReleaseMeta/choose_tier (0.6.0)
- `cratedig/gui/update_check.py` — `UpdateCheckThread` + `UpdateDownloadThread`
- `packaging/make_manifest.py` — build-time manifest gen / diff / tier decision / delta-zip (mac) / win-include / emit-release-meta (0.6.0)
- `packaging/windows/cratedig-update.iss` — Windows delta installer (small Inno)
- `packaging/windows/build_all.ps1` — Windows one-shot build; `-Sign` signs; `-Publish` creates/uploads GitHub release
- `packaging/macos/build_all.sh` — macOS one-shot build; `SIGN=1` signs; `PUBLISH=1` uploads
- `.claude/commands/update.md` — `/update` session-start command
- `README.md` — end-user install guide
- `README.dev.md` — developer setup guide
- `docs/SETTINGS_DESIGN.md` — Settings dialog + config_writer blueprint
- `docs/PLAN_0.6.0.md` — 0.6.0 feature blueprint (IMPLEMENTED — shipped in 0.6.0)

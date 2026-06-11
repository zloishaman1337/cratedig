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
in-app on Win; external process closes app, swaps locked files, relaunches).
macOS delta = `.zip` applied in-app via **Help → "Apply update from file…"**
(`cratedig/updater.py`) + bash restart helper that swaps files after app exits.
**App checks for updates automatically on startup** (frozen builds, GitHub Releases feed,
silent on failure/up-to-date, dialog only when newer). Every asset verified by minisign.
**Both Windows and macOS share the same in-app update flow** (launch → accept → auto
download+verify+apply+relaunch). Win-then-mac two-session order. Meta/tooling-only
sessions skip the release stage entirely.

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
| gui.main_window | ✅ | 5 stacked sidebar pages (index 3=Bitwig, 4=Nuendo added 0.5.0); version label in QStatusBar; `_maybe_check_updates()` silent startup check; unified download+install both OS |
| gui.simpler_pane | ✅ | **0.5.0**: `_WaveCanvas.paintEvent` blits cached static QPixmap (`_paint_static`); playhead drawn live only; mip peak pyramid for envelope; cache invalidated by version counters |
| gui.project_explorer | ✅ | **NEW 0.5.0** `cratedig/gui/project_explorer.py`: `ProjectExplorerPanel` — generic panel for Bitwig/Nuendo; badges for format-suffixed 3rd-party plugins |
| gui.update_check | ✅ | `UpdateCheckThread` (silent startup check) + `UpdateDownloadThread` (streams + minisign-verifies) |
| gui.worker | ✅ | `request_reload()` uses `tags_for_all()` (batched); `request_plugin_scan` slot + `pluginIndexReady` signal (0.5.0) |
| updater | ✅ | **ONLINE updater**. `FileEntry`/`UpdateManifest`/`ReleaseAsset`/`Release`, `sha256_file`, `manifest_sha256`, `build_update_zip_doc`, `load_update_manifest`, `is_newer`, `verify_payload`, `current_os`, `parse_release`, `select_asset`, `find_signature`. I/O: `fetch_latest_release`, `download_asset`, `minisign_path`, `verify_signature`, `download_and_verify`. macOS apply: `apply_update` (delta `.zip`), `apply_dmg_update` + `_write_dmg_restart_helper`. `GITHUB_REPO="zloishaman1337/cratedig"` hardcoded. `MINISIGN_PUBKEY` embedded (key id 54F217219B866BE6). |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; `_match_plugin` delegates to `scanner.match_name` (0.5.0) |
| plugins.scanner | ✅ | **NEW 0.5.0** `cratedig/plugins/scanner.py`: `standard_plugin_dirs`, `scan_installed`, `match_name`/`match_installed`, `load_or_scan`; disk cache at `user_data_dir()/plugin_index.json` keyed by dir signature |
| projects_fmt | ✅ | **NEW 0.5.0** `cratedig/projects_fmt/`: `common.py` (`read_project_bytes`, MAX_PROJECT_BYTES=256MB, `_AUDIO_RE` bounded), `bitwig.py` (`BtWg` header + string table + ZIP tail), `nuendo.py` (RIFF tagged tree). Returns `{format, version, plugins, samples, tracks}`. Security hardened (zip-bomb cap, bounds checks). |
| sources.* | ✅ | youtube/yandex/freesound/manager; `safe_filename`+`unique_path`; `ffmpeg_location` yt-dlp opt from `bundled_binary` when frozen |
| metadata (mb/discogs) | ✅ | incremental `metadata_cache`; `rank_track_hits(..., force_live=False)` |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily. **Bundled in release builds**.
- **Packaging**: onedir (NOT onefile). Windows: Inno Setup installer. macOS: `.app` in `.dmg`. See `PACKAGING.md`.
- New runtime dep: `platformdirs>=4.0`. New `[build]` extra: `pyinstaller>=6.0` + `pillow>=10.0`.

## Packaging status
| target | status | note |
|---|---|---|
| Windows onedir build | ✅ DONE 0.5.0 | `dist/cratedig/`; ~168 MB |
| Windows installer | ✅ DONE 0.5.0 | `cratedig-setup-0.5.0.exe` signed; tier=FULL (delta built but not published — client can't consume delta yet) |
| Release manifests | ✅ win + mac 0.5.0 | `cratedig-0.5.0-win.json` + `cratedig-0.5.0-mac.json` produced; mac manifest committed this session |
| Windows GitHub release | ✅ published 0.5.0 (signed) | `cratedig-setup-0.5.0.exe` + `.minisig`; https://github.com/zloishaman1337/cratedig/releases/tag/0.5.0 |
| macOS `.app` + `.dmg` | ✅ DONE 0.5.0 | full `cratedig-0.5.0.dmg` signed + published + verified |
| GitHub Actions CI | ⏳ written, not run | `.github/workflows/release.yml` matrix; fires on tag |

## Gotchas
- **config_writer path**: `resolve_config_path()` MUST mirror `config.load_config` path resolution.
- **Frozen user-data seeding**: first run copies `config.example.toml` → `%APPDATA%\cratedig\config.toml`; DB defaults to `%APPDATA%\cratedig\data\cratedig.db`.
- **Bundled ffmpeg/ffplay/minisign live in `dist/cratedig/_internal/`** (onedir); `bundled_binary()` checks `_MEIPASS`, exe dir, `_MEIPASS/bin`.
- **macOS ffmpeg/ffplay**: `build_all.sh` fetches arm64 static builds from osxexperts.net (FFmpeg 8.1). evermeet.cx (x86_64-only) was the old source; `--retry 5 --retry-delay 3` on curl.
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
- **Baseline trap (0.4.0)**: 0.2/0.3 installs have no update checker — cannot auto-pull 0.4.0+. Distribute full installers manually to those users.
- **minisign.key in repo root, gitignored**. Back it up and copy to mac before Session 2. **Password auto-loads from gitignored `.env` (`MINISIGN_PASSWORD=…`)** in both `build_all.ps1` and `build_all.sh`; env var wins if already set. `.env` added to `.gitignore`. Agent must read `.env`, never ask the user.
- **GITHUB_REPO hardcoded** as `"zloishaman1337/cratedig"` — do not auto-detect from git remote.
- **PyInstaller rewrites `base_library.zip` every build** (churned sha256, identical size) — allowlisted in `make_manifest.py` `DEFAULT_APP_PATHS` so it doesn't force tier=full on code-only diffs.
- **`apply_dmg_update` is macOS-only** — raises immediately on non-Darwin; off-platform guard tested in `tests/test_updater_online.py`.
- **Online client still requests `tier="full"`** — `UpdateDownloadThread` calls `download_and_verify` with default `tier="full"`; delta-over-the-wire is not wired client-side yet. Ship FULL until fixed.
- **0.5.0 shipped FULL despite delta-tier diff** — auto diff reported `changed=3 added=0 → tier=delta` but full was published because the online client always fetches full asset. Delta `cratedig-update-0.5.0.exe` was built but NOT published.

## Verification (0.5.0)
- Full pytest: **918 passed, 0 failed**. New test files: `test_plugin_scanner.py`, `test_plugin_badges.py`, `test_projects_fmt.py`, `test_project_explorer.py`; extended `test_gui_logic.py` (pyramid + version_status_text), `test_simpler_pane.py` (TestWaveCanvasPerf), `test_als.py` (5 stacked pages).
- Frozen `dist\cratedig\cratedig.exe` (0.5.0) smoke-launched — alive 8s, clean stop.
- `cratedig-setup-0.5.0.exe` minisign VERIFIED ("Signature and comment signature verified", trusted comment "cratedig 0.5.0").
- Live feed: `fetch_latest_release()`→0.5.0; `is_newer(0.5.0,0.4.1)` True; `select_asset(win,full)`→cratedig-setup-0.5.0.exe + .minisig. Running 0.4.1 will auto-detect 0.5.0 on startup.
- macOS `cratedig-0.5.0.dmg` built (171.6 MB), signed, minisign VERIFIED ("Signature and comment signature verified", trusted comment "cratedig 0.5.0"), smoke-launched alive >6s clean quit, CFBundleShortVersionString=0.5.0.

## macOS HANDOFF — none
No release is mid-flight. Both Windows and macOS have shipped 0.5.0.

## Backlog
- **0.4.0 distribute manually**: hand 0.4.0+ full installers to existing 0.2/0.3 users — they have no update checker.
- **Delta-over-the-wire (0.6.0+)**: wire client-side `tier="delta"` in `UpdateDownloadThread`/`download_and_verify` before a delta can ship online. Build-level delta detection already works; still ships FULL because client always requests full.
- Exercise CI workflow (`.github/workflows/release.yml`) end-to-end on a pushed `v*` tag.
- Optional: Windows EV code-signing cert and macOS notarization (Apple Dev ID $99/yr).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).

## Authoritative files
- `ARCHITECTURE.md` — full design + roadmap
- `PACKAGING.md` — distribution/packaging plan; §6 = macOS rebuild procedure; pointer → UPDATE_RULES.md
- `UPDATE_RULES.md` — authoritative release/update pipeline: two-tier ONLINE model (since 0.4.0)
- `packaging/release-manifests/` — per-release file-hash manifests; diff baseline for tier decision
- `cratedig/updater.py` — online feed constants + pure parsing + I/O layer + macOS apply layer
- `cratedig/gui/update_check.py` — `UpdateCheckThread` + `UpdateDownloadThread`
- `packaging/make_manifest.py` — build-time manifest gen / diff / tier decision / delta-zip (mac) / win-include
- `packaging/windows/cratedig-update.iss` — Windows delta installer (small Inno)
- `packaging/windows/build_all.ps1` — Windows one-shot build; `-Sign` signs; `-Publish` creates/uploads GitHub release
- `packaging/macos/build_all.sh` — macOS one-shot build; `SIGN=1` signs; `PUBLISH=1` uploads
- `.claude/commands/update.md` — `/update` session-start command
- `README.md` — end-user install guide
- `README.dev.md` — developer setup guide
- `docs/SETTINGS_DESIGN.md` — Settings dialog + config_writer blueprint
- `docs/PLAN_0.5.0.md` — 0.5.0 feature blueprints (all 4 features shipped)

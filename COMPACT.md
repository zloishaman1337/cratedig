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
| gui.main_window | ✅ | **0.5.2**: 11 stacked pages (0 samples · 1 Ableton · 2 Health · 3-10 DAW checkers); `self._checker_panels` list (als + `self._daw_panels`); `self._daw_panels` spec-driven (8 panels: Bitwig, Nuendo, Cubase, Reaper, FL Studio, Studio One, Logic, Pro Tools); all worker wiring loops iterate `self._checker_panels`; version label in QStatusBar; `_maybe_check_updates()` silent startup check; unified download+install both OS; `closeEvent` aborts in-flight threads |
| gui.simpler_pane | ✅ | **0.5.0**: `_WaveCanvas.paintEvent` blits cached static QPixmap (`_paint_static`); playhead drawn live only; mip peak pyramid for envelope; cache invalidated by version counters |
| gui.als_explorer | ✅ | **0.5.2**: generic `AlsExplorerPanel`; 4 tabs (Overview/Instruments/Plugins/Tracks); summary card shows Tempo/Key/Length/3rd-party; NEW Project Health card (`_compute_health` score 0-100 + issues); NEW Overview tab (`_build_overview_tab`); `_plugin_badge` takes `bare_is_native` arg. i18n keys RU+EN for all new UI. `C_WARN` color added. `gui/project_explorer.py` DELETED. |
| gui.update_check | ✅ | `UpdateCheckThread` (silent startup check) + `UpdateDownloadThread` (streams + minisign-verifies); **0.5.1**: `progress = Signal(int,int)` + `cancel()` flag; stays silent on user-initiated cancel |
| gui.worker | ✅ | `request_reload()` uses `tags_for_all()` (batched); `request_plugin_scan` slot + `pluginIndexReady` signal (0.5.0) |
| updater | ✅ | **ONLINE updater**. `FileEntry`/`UpdateManifest`/`ReleaseAsset`/`Release`, `sha256_file`, `manifest_sha256`, `build_update_zip_doc`, `load_update_manifest`, `is_newer`, `verify_payload`, `current_os`, `parse_release`, `select_asset`, `find_signature`. I/O: `fetch_latest_release`, `download_asset` (0.5.1: 1 MiB chunk streaming, optional `progress(done,total)` + `cancel()` poll), `minisign_path`, `verify_signature`, `download_and_verify` (forwards `progress`/`cancel`). macOS apply: `apply_update` (delta `.zip`), `apply_dmg_update` + `_write_dmg_restart_helper`. `GITHUB_REPO="zloishaman1337/cratedig"` hardcoded. `MINISIGN_PUBKEY` embedded (key id 54F217219B866BE6). |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; `_match_plugin` delegates to `scanner.match_name` (0.5.0) |
| plugins.scanner | ✅ | **NEW 0.5.0** `cratedig/plugins/scanner.py`: `standard_plugin_dirs`, `scan_installed`, `match_name`/`match_installed`, `load_or_scan`; disk cache at `user_data_dir()/plugin_index.json` keyed by dir signature |
| projects_fmt | ✅ | **0.5.2**: `common.py` carries `bpm`/`length`/`key`; `to_checker_data` passes rich tracks through (non-empty list-of-dicts wins over synthetic "Project" track); `_arrangement_from` synthesises arrangement from bpm/length; `iter_printable_runs` helper; `resolve_samples_on_disk` scans bundle DIR directly (Logic). `bitwig.py` `_tempo` via 0x07-tagged BE double near TEMPO (bpm 140 verified). `nuendo.py` `_tempo` via BE float near MTempoTrackEvent (bpm 120 verified). NEW: `reaper.py` (full parity: rich tracks/tempo/VST/AU/CLAP/JS/FILE samples), `flstudio.py` (FLhd/FLdt walk: version/tempo/samples/generators/effects/wrapped-VST), `studioone.py` (ZIP classInfo device nodes; tempo→None; zip-bomb caps), `logic.py` (macOS bundle dir; MetaData.plist→bpm/key/tracks/AudioFiles; ProjectInformation.plist→version; 3rd-party AU via reversed 4cc markers; names truncated to 11 chars in source data), `protools.py` (best-effort ONLY: body XOR-obfuscated; returns version + plaintext sample refs, never cipher garbage). |
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
| Windows onedir build | ✅ DONE 0.5.2 | `dist/cratedig/`; smoke-launched alive 8s clean stop |
| Windows installer | ✅ DONE 0.5.2 | `cratedig-setup-0.5.2.exe` signed; tier=FULL (delta removed from release) |
| Release manifests | ✅ win+mac 0.5.2 | `cratedig-0.5.2-win.json` (808 files) + `cratedig-0.5.2-mac.json` committed (commit 29472c8) |
| Windows GitHub release | ✅ published 0.5.2 (signed) | `cratedig-setup-0.5.2.exe` + `.minisig` verified; https://github.com/zloishaman1337/cratedig/releases/tag/0.5.2 |
| macOS `.app` + `.dmg` | ✅ DONE 0.5.2 | `cratedig-0.5.2.dmg` (~172 MB) signed, smoke-launched alive 8s, published to GitHub release 0.5.2 |
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
- **minisign.key in repo root, gitignored**. Back it up and copy to mac before macOS session. **Password auto-loads from gitignored `.env` (`MINISIGN_PASSWORD=…`)** in both `build_all.ps1` and `build_all.sh`; env var wins if already set. `.env` added to `.gitignore`. Agent must read `.env`, never ask the user.
- **GITHUB_REPO hardcoded** as `"zloishaman1337/cratedig"` — do not auto-detect from git remote.
- **PyInstaller rewrites `base_library.zip` every build** (churned sha256, identical size) — allowlisted in `make_manifest.py` `DEFAULT_APP_PATHS` so it doesn't force tier=full on code-only diffs.
- **`apply_dmg_update` is macOS-only** — raises immediately on non-Darwin; off-platform guard tested in `tests/test_updater_online.py`.
- **Online client still requests `tier="full"`** — `UpdateDownloadThread` calls `download_and_verify` with default `tier="full"`; delta-over-the-wire is not wired client-side yet. Ship FULL until fixed.
- **`build_all.ps1 -Tier full` arg can mis-bind through `pwsh -File`** — verify the "Done (tier)" line after the build; if it says delta, build the full installer directly via ISCC on `cratedig.iss` from the existing onedir, sign, and swap the release asset.
- **0.4.1→0.5.0 auto-update was broken** (crash + no progress) — fixed in 0.5.1. Auto-update only reliable from 0.5.1+. Distribute 0.5.0+ full installers manually to pre-0.5.1 users.
- **Pre-existing test failure**: `test_config_writer.py::test_round_trip_no_mutation_preserves_bytes` fails due to CRLF/LF mismatch in `config.example.toml` working tree — not a regression, unrelated to any feature work.
- **Large DAW test fixtures** (`projects/` — Logic ~82MB, Studio One ~75MB, Cubase ~11MB, flp/ptx/rpp) intentionally LEFT UNTRACKED; real-project tests are `skipif`-guarded on their presence. Original fixtures (`Changes.npr`, `Surface Tension.bwproject`) remain tracked.
- **Logic AU plugin names truncated to 11 chars** in `ProjectData` reversed-4cc markers — this is inherent to the source data, not a parser bug.
- **onedir code-only release → auto-tier picks DELTA** (only `cratedig.exe`+`base_library.zip` change); but client still fetches FULL — always build full via ISCC on `cratedig.iss`, sign, delete delta assets from the release.
- **Build venv is Python 3.13 on macOS** (confirmed 0.5.2 session).

## Verification (0.5.2)
- Full pytest: **955 passed, 1 failed** (pre-existing CRLF artifact — not a regression).
- +28 new tests vs 0.5.1 (927→955). New test files: `tests/test_projects_fmt_reaper.py`, `_flstudio.py`, `_studioone.py`, `_logic.py`, `_protools.py`. Extended: `test_projects_fmt.py` (bitwig/nuendo bpm), `test_project_checker.py` (bpm/length/key carry, rich-tracks passthrough, Project Health), `test_als.py` (4 tabs; 11 stacked pages + per-DAW nav).
- Frozen `dist\cratedig\cratedig.exe` (0.5.2) smoke-launched — alive 8s, clean stop.
- `cratedig-setup-0.5.2.exe` minisign VERIFIED (trusted comment "cratedig 0.5.2").
- `cratedig-0.5.2.dmg` (~172 MB) minisign VERIFIED (key id 54F217219B866BE6, trusted comment "cratedig 0.5.2"); `dist/cratedig.app` smoke-launched — alive 8s, clean stop.
- Live feed: `fetch_latest_release()`→0.5.2; `is_newer(0.5.2,0.5.1)`=True; `select_asset(win,full)`→cratedig-setup-0.5.2.exe.
- **Release 0.5.2 complete**: all 4 assets published — `cratedig-setup-0.5.2.exe` + `.minisig` (Windows), `cratedig-0.5.2.dmg` + `.minisig` (macOS).

## macOS HANDOFF — none

Both Windows and macOS 0.5.2 shipped. No release mid-flight.

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
- `docs/PLAN_0.5.2.md` — 0.5.2 feature blueprint (IMPLEMENTED — shipped in 0.5.2)

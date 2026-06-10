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
| config | ✅ | TOML → typed Config (stdlib `tomllib`, read-only, frozen); `_default_config_path()` uses user data dir when frozen; `_seed_config_if_frozen()` copies bundled `config.example.toml` → user dir on first run |
| config_writer | ✅ | **tomlkit** comment-preserving writer; `resolve_config_path()` delegates to `config._default_config_path()` for default branch; `load_document`/`write_document` (atomic temp+`os.replace`); seeds from `config.example.toml` if target missing |
| paths | ✅ | `cratedig/paths.py`; `is_frozen()`, `user_data_dir()` (platformdirs), `resource_root()`/`resource_path(name)`, `bundled_binary(name)`, `ffmpeg_path()`/`ffplay_path()` (bundled-or-`shutil.which`) |
| db | ✅ | WAL mode; `upsert_sample(..., commit=True)`; `Database.commit()` for batch flush; `all_samples(limit: int\|None)`; `tags_for_all() -> dict[int, list[str]]` (one query, replaces N per-sample calls) |
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
| gui.main_window | ✅ | `_preview_timer` 30ms; `_on_config_written()` prompts restart; `_maybe_check_updates()` silent startup check (frozen only); unified download+install on both OS: Win → `os.startfile`+quit; mac → `updater.apply_dmg_update(path)`+quit |
| gui.simpler_pane | ✅ | Waveform pan/zoom lag fixed: removed dead `_recompute()`/`_peaks` double-compute; rendered-edit peaks recompute only on zoom-span change; panning is pure view shift + repaint |
| gui.update_check | ✅ | `UpdateCheckThread` (silent startup check) + `UpdateDownloadThread` (streams + minisign-verifies) |
| gui.worker | ✅ | `request_reload()` uses `tags_for_all()` (batched, single query) instead of per-sample loop |
| updater | ✅ | **ONLINE updater**. Pure layer: `FileEntry`/`UpdateManifest`/`ReleaseAsset`/`Release`, `sha256_file`, `manifest_sha256`, `build_update_zip_doc`, `load_update_manifest`, `is_newer`, `verify_payload`, `current_os`, `parse_release`, `select_asset`, `find_signature`. I/O: `fetch_latest_release`, `download_asset`, `minisign_path`, `verify_signature`, `download_and_verify`. macOS apply: `apply_update` (delta `.zip`), `apply_dmg_update` + `_write_dmg_restart_helper` (full `.dmg` mount→swap→relaunch). `GITHUB_REPO="zloishaman1337/cratedig"` hardcoded. `MINISIGN_PUBKEY` embedded (key id 54F217219B866BE6). |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L |
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
| Windows onedir build | ✅ DONE 0.4.1 | `dist/cratedig/`; ~160 MB |
| Windows installer | ✅ DONE 0.4.1 | `cratedig-setup-0.4.1.exe` ~160 MB signed; tier=FULL; per-user install |
| Release manifests | ✅ DONE — both committed | `cratedig-0.4.1-win.json` (1d108c0) + `cratedig-0.4.1-mac.json` committed; mac diff vs 0.4.0-mac: changed=5 added=0 deleted=0 → tier=full |
| Windows GitHub release | ✅ published to GitHub release 0.4.1 (signed) | `cratedig-setup-0.4.1.exe` + `.minisig` attached; https://github.com/zloishaman1337/cratedig/releases/tag/0.4.1 |
| macOS `.app` + `.dmg` | ✅ DONE 0.4.1 | full `cratedig-0.4.1.dmg` (~171 MB) signed; published to GitHub release 0.4.1 |
| macOS GitHub release | ✅ published to GitHub release 0.4.1 (signed) | `cratedig-0.4.1.dmg` + `.minisig` attached; https://github.com/zloishaman1337/cratedig/releases/tag/0.4.1; verified against embedded MINISIGN_PUBKEY |
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
- **Baseline trap (0.4.0)**: 0.2/0.3 installs have no update checker — cannot auto-pull 0.4.0+. Distribute full installers manually to those users. Auto-update works between 0.4.x releases.
- **minisign.key in repo root, gitignored**. Back it up and copy to mac before Session 2. Password via `$env:MINISIGN_PASSWORD`. Never commit the key.
- **GITHUB_REPO hardcoded** as `"zloishaman1337/cratedig"` — do not auto-detect from git remote.
- **PyInstaller rewrites `base_library.zip` every build** (churned sha256, identical size) — allowlisted in `make_manifest.py` `DEFAULT_APP_PATHS` so it doesn't force tier=full on code-only diffs.
- **`apply_dmg_update` is macOS-only** — raises immediately on non-Darwin; off-platform guard tested in `tests/test_updater_online.py`.
- **Online client still requests `tier="full"`** — `UpdateDownloadThread` calls `download_and_verify` with default `tier="full"`; delta-over-the-wire is not wired client-side yet (0.5.0+ backlog).

## Verification (0.4.1)
- Full pytest: **849 passed, 0 failed** (added: `test_tags_for_all_returns_sorted_map`, `test_tags_for_all_empty_database` in `tests/test_database.py`; `test_tier_delta_when_only_exe_and_base_library_change` in `tests/test_make_manifest.py`).
- Frozen `dist/cratedig/cratedig.exe` (0.4.1) smoke-launched on Windows — alive 8s, clean stop.
- `cratedig-setup-0.4.1.exe` minisign signature VERIFIED end-to-end against embedded `MINISIGN_PUBKEY` ("Signature and comment signature verified").
- Live GitHub feed post-publish: `updater.fetch_latest_release()` returns 0.4.1; `is_newer(0.4.1, 0.4.0)` True; `select_asset(win, full)` → cratedig-setup-0.4.1.exe + .minisig; source archives absent. Running 0.4.0 will detect and offer 0.4.1 on startup.
- macOS full `dist/cratedig.app` (0.4.1) smoke-launched — alive 6s+, clean quit (PID 51953).
- `cratedig-0.4.1.dmg` minisign signature VERIFIED end-to-end ("Signature and comment signature verified", trusted comment "cratedig 0.4.1"). Live feed: `updater.fetch_latest_release()`→0.4.1; `select_asset(mac, full)`→cratedig-0.4.1.dmg + .minisig; no source archives; `is_newer(0.4.1,0.4.0)` True.

## macOS HANDOFF — none

## Backlog
- **0.4.0 distribute manually**: hand 0.4.0+ full installers to existing 0.2/0.3 users — they have no update checker. 0.4.1 auto-updates fine for anyone already on 0.4.0.
- **Delta-over-the-wire (0.5.0+)**: wire client-side `tier="delta"` in `UpdateDownloadThread`/`download_and_verify` before a delta can ship online. Build-level delta detection already works (validated 0.4.0→0.4.1: `make_manifest diff` reports tier=delta for code-only change after base_library.zip allowlisted; still shipped FULL because client always requests full).
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

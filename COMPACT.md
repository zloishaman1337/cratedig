# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).
Releases follow **UPDATE_RULES.md** — **two-tier OFFLINE update model**: most releases
ship a small **delta** (code-only); full installer only when deps/Python/ffmpeg/
assets change. Tier decided automatically by diffing the new onedir against the
committed release manifest (`packaging/release-manifests/`). **Delta delivery is per-OS:**
Windows delta = small Inno update installer `cratedig-update-<ver>.exe` (user double-clicks;
external process closes app, swaps locked files, relaunches — no in-app code).
macOS delta = `.zip` applied in-app via **Help → "Apply update from file…"**
(`cratedig/updater.py`, IMPLEMENTED 0.3.0) + bash restart helper that swaps files after app exits.
App NEVER contacts a server — user supplies the update file manually.
Win-then-mac two-session order. Meta/tooling-only sessions skip the release stage entirely.

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config (stdlib `tomllib`, read-only, frozen); `_default_config_path()` uses user data dir when frozen; `_seed_config_if_frozen()` copies bundled `config.example.toml` → user dir on first run; non-frozen behavior unchanged |
| config_writer | ✅ | **tomlkit** comment-preserving writer; `resolve_config_path()` delegates to `config._default_config_path()` for default branch (precedence: explicit arg > CRATEDIG_CONFIG env > frozen-aware default) — writer and `config.load_config` now resolve the same path; `load_document`/`write_document` (atomic temp+`os.replace`, `newline=""` byte round-trip); seeds from `config.example.toml` if target missing; mutators set paths/audio.extensions/metadata/sources tokens; `DEFAULT_CONFIG_NAME` import removed |
| paths | ✅ | `cratedig/paths.py`; `is_frozen()`, `user_data_dir()` (platformdirs — Win `%APPDATA%\cratedig`, mac `~/Library/Application Support/cratedig`, Linux `~/.local/share/cratedig`), `resource_root()`/`resource_path(name)` (`sys._MEIPASS` when frozen else repo root), `bundled_binary(name)`, `ffmpeg_path()`/`ffplay_path()` (bundled-or-`shutil.which`) |
| db | ✅ | WAL mode (`journal_mode=WAL`, `synchronous=NORMAL`) since 0.2.0; `upsert_sample(..., commit=True)` param; `Database.commit()` for batch flush; `all_samples(limit: int\|None)` — None loads whole library; all schema migrations idempotent |
| scan | ✅ | `scan_directory` parallelized via `ThreadPoolExecutor` (`_scan_workers()` = min(cpu,8)); DB upserts batched (flush every 128 + final); prunes deleted files; `scan_libraries` also scans `paths.saved_dir`; scan builds desktop mono waveform PCM cache best-effort |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude; `aspect_topk`+`cosine_topk`; `extract_features(path, sr, y=None)` — accepts pre-loaded buffer to avoid double librosa.load |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` for audio fallback |
| audio.playback | ✅ | `decode_waveform_mono_samples` true mono float32 PCM via ffmpeg with soundfile fallback; `AudioPlayer.play` supports `start_sec`/`duration_sec`/`gain_db`; `ffmpeg_path()`/`ffplay_path()` from `..paths` (bundled-or-PATH) |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; DSP tags; mutually-exclusive pairs enforced |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`; `detect_transients` per-frame PEAK+RMS hybrid |
| health | ✅ | `HealthReport` dataclass + `library_health` + `missing_sample_ids` + `format_report`; GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan` |
| index.py | ✅ | `analyze_pending`/`tag_pending` parallelized via `ThreadPoolExecutor` (`_worker_count()` = min(cpu,8)); analyze batched via `executemany` every 64 rows; **decode-once**: reuses buffer already loaded by analyzer (no second librosa.load); `analyze_pending` also populates 44.1k mono preview cache per file |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI+GUI |
| gui | ✅ | Global dark redesign; `run_gui` sets Windows AppUserModelID; all subsystems wired |
| gui.theme | ✅ | `apply_app_theme(app)` global dark palette+QSS; `#SidebarTitle` font 18px (was 23px — clipped past 148px sidebar); `app_icon()` paints branded ▣ mark programmatically |
| gui.main_window | ✅ | `_preview_timer` interval 30ms (was 150ms) — smooth playhead glide; `_on_config_written()` prompts restart after settings save |
| gui.toast | ✅ | `ToastManager(host)` + `_Toast(QFrame)` — dark cards; levels info/ok/error; QSS braces must stay balanced |
| gui.health_panel | ✅ | Grafana-style `_StatTile` severity-coloured cards; overall status banner pill |
| gui.ab_dialog | ✅ | `ABCompareDialog(QDialog)` modal A/B compare; loudness leveling wired |
| gui.logic | ✅ | `backend_badge`; `ABState`; `match_als_samples`; `compute_peaks`; `ab_level_gain_db`; `filter_samples` |
| gui.platform_files | ✅ | `reveal_in_file_manager(path)` cross-platform |
| gui.sample_table | ✅ | 9 cols; Tags visible; Similarity hidden until scores shown; drag emits file URLs; context menu |
| gui.metadata_panel | ✅ | compact read-only widget; mutagen easy tags; seq-guarded |
| gui.settings_dialog | ✅ | 3-tab `SettingsDialog`; signals `preferences_changed`/`config_written`/`auto_preview_changed` |
| gui.settings_tabs | ✅ | `_keys.py` (QSettings key constants + `DEFAULTS` + `TYPES`); `browser/library_load_limit` key (default 0 = all); preferences/project-config/paths tabs; spinbox "Library load limit (0 = all)" in preferences_tab |
| gui.simpler_pane | ✅ | Draggable region+fade handles; loop/reverse toggles; ADSR overlay; `_KnobDial` |
| gui.worker | ✅ | all request/signal pairs; `request_delete` → recycle bin for saved/edit files; `IndexWorker._library_load_limit()` reads `browser/library_load_limit` and passes to `db.all_samples(limit=…)` |
| gui.download_pane | ✅ | QProgressBar 4 states; `set_backend(source)`; settings param; auto-preview |
| gui.als_explorer | ✅ | embedded page; 3-tab Instruments/Plugins/Tracks + optional Library Match; drag&drop .als |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L |
| sources.base | ✅ | `safe_filename`+`unique_path`; strips Windows-illegal chars, caps 120 chars |
| sources.yandex | ✅ | `<TRACK> - <ARTIST>.mp3` via `safe_filename`+`unique_path` |
| sources.youtube | ✅ | `_opts` sets yt-dlp `ffmpeg_location` to `bundled_binary("ffmpeg")` when frozen; `safe_filename`+`unique_path` |
| sources.freesound | ✅ | proxy-bypass session; `safe_filename`+`unique_path` |
| sources.manager | ✅ | samples→FreeSound; tracks→merged Yandex+YouTube; MusicBrainz/Discogs incremental-cache ranking |
| metadata (mb/discogs) | ✅ | core wiring done; incremental `metadata_cache`; `rank_track_hits(..., force_live=False)` |
| updater | ✅ | **OFFLINE updater** (UPDATE_RULES §7). Pure logic (cross-platform, tested): `FileEntry`/`UpdateManifest`, `sha256_file`, `manifest_sha256` (canonical JSON), `build_update_zip_doc`, `load_update_manifest`, `is_newer`, `check_compatible`, `verify_payload`. macOS side-effects: `apply_update` → extract+verify → spawn dependency-free bash restart helper (waits for app exit, `ditto` swap, relaunch). Windows uses external Inno update `.exe` instead. NO network. |

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
| Windows onedir build | ✅ DONE | `dist/cratedig/`; v0.3.0; librosa/numba/llvmlite bundle OK on Python 3.13.5/PyInstaller 6.20.0 |
| Windows Inno installer | ✅ DONE | `cratedig-setup-0.3.0.exe` 160.7 MB (full tier — updater baseline); per-user install; `ISCC.exe` at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`; delta path = `cratedig-update.iss` (built only when a prior manifest diffs to delta) |
| Release manifests | ✅ | `packaging/release-manifests/cratedig-0.3.0-win.json` committed (first manifest = delta baseline). Mac manifest pending Session 2. |
| macOS `.app` + `.dmg` | ⏳ PENDING (0.3.0) | last built 0.1.0; needs Mac rebuild for 0.3.0 (updater baseline); see macOS HANDOFF block |
| GitHub Actions CI | ⏳ written, not run | `.github/workflows/release.yml` matrix (windows-latest, macos-14, macos-13); fires on tag |

## Gotchas
- **config_writer path**: `resolve_config_path()` MUST mirror `config.load_config` path resolution — frozen writes/reads both go to `user_data_dir()/config.toml`; do NOT hardcode `./config.toml` in the writer.
- **Settings Save in frozen app**: previously wrote to `./config.toml` (CWD) while reader used `%APPDATA%\cratedig\config.toml` → changes never applied after restart. Fixed: `resolve_config_path()` now delegates to `config._default_config_path()`.
- **Settings Save auto-restart**: `_on_config_written()` in `main_window.py` shows a Yes/No QMessageBox; Yes → `_restart_app()` (`QProcess.startDetached(sys.executable, [])` frozen, else `["-m","cratedig.gui"]`) then `QApplication.quit()`; No → info toast.
- **Frozen user-data seeding**: first run copies `config.example.toml` → `%APPDATA%\cratedig\config.toml`; DB defaults to `%APPDATA%\cratedig\data\cratedig.db`. Non-frozen path unchanged.
- **Bundled ffmpeg/ffplay live in `dist/cratedig/_internal/`** (onedir); `bundled_binary()` checks `_MEIPASS`, exe dir, `_MEIPASS/bin`. ffmpeg binaries staged in `packaging/bin/windows/` (and `packaging/bin/macos/`) are git-ignored — `build_all.sh` fetches them.
- **macOS ffmpeg/ffplay from evermeet.cx are x86_64-only** — run via Rosetta 2 on arm64 `.app`; evermeet ships no arm64 static build. Acceptable for personal use.
- **evermeet.cx download is flaky** — `build_all.sh` curl uses `--retry 5 --retry-delay 3 --retry-all-errors`. Re-running the script is safe.
- In the `.app`, PyInstaller stages bundled binaries in BOTH `Contents/Resources/` and `Contents/Frameworks/`.
- **Inno Setup location**: `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (winget install). Not on PATH by default.
- **DB is WAL mode** since 0.2.0 — `-wal`/`-shm` sidecar files appear next to the db; safe for single-user.
- **Do NOT switch scan/analyze ThreadPoolExecutor to ProcessPoolExecutor** — `tests/test_database.py` monkeypatches `cratedig.audio.analyzer.analyze`; spawned processes would not see the patch.
- **44.1k mono preview cache** is populated during BOTH scan and `analyze_pending`; cache key = file_hash; location = `cfg.paths.db.parent/waveform_cache`. `analyze_pending` guards via `getattr(cfg,'paths',…)` so test cfgs without `.paths` skip it.
- **Per-user installer (0.2.0)**: first release with `PrivilegesRequired=lowest` — existing users must uninstall old per-machine install, then run new setup. User data in `%APPDATA%` is preserved.
- `sources/youtube.py`: `shutil.which` boolean check kept for test compat; `ffmpeg_location` yt-dlp opt set from `bundled_binary("ffmpeg")` when frozen.
- numba/llvmlite: benign `tbb12.dll` not-found warning on Windows frozen build; numba falls back to workqueue threading — harmless.
- ffmpeg required on PATH (non-frozen) for YouTube extraction and waveform decode (falls back to soundfile).
- ffplay required on PATH (non-frozen) for TUI/GUI playback and GUI download preview.
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
- **Version is dual-SSOT-mirrored**: `pyproject.toml` (authoritative per UPDATE_RULES §2) AND `cratedig/__init__.__version__` (runtime, read by updater + spec `info_plist`). Bump BOTH together every release — they had drifted (init was 0.1.0 while pyproject was 0.2.0).
- **pytest lives in `[dev]` extra, NOT installed by `build_all.*`** — the build venv has only gui/analysis/download/metadata/build. Run `pip install -e ".[dev]"` (or `pip install pytest`) before pytest in that venv.
- **Updater manifest hash**: builder (`make_manifest.build_update_zip_doc`) and applier (`updater.load_update_manifest`) MUST use the same `updater.manifest_sha256` (canonical JSON, sorted keys, `,`/`:` separators) — never hand-roll a second hash.
- **`DEFAULT_APP_PATHS` in make_manifest.py is conservative/untested vs a real code-only diff** — first delta release must validate it (see Backlog).

## Verification
- Full pytest: **819 passed, 0 failed** (v0.3.0; +64 new: test_updater.py 57, test_make_manifest.py 7).
- v0.3.0 frozen `cratedig.exe` smoke-launched on Windows — alive 6s, no crash; `cratedig-setup-0.3.0.exe` (160.7 MB) compiled OK; manifest committed.
- macOS `.app` NOT yet rebuilt for 0.3.0 (Session 2 pending).

## macOS HANDOFF — PENDING
- version: 0.3.0
- tier: full   # baseline: offline-updater first ships as FULL on both OS; no prior mac manifest to diff
- windows update: DONE (cratedig-setup-0.3.0.exe; manifest cratedig-0.3.0-win.json committed)
- macos update: PENDING
- source ref: next commit on main (parent b167f45) — user commits this session's diff; macOS session does `git pull` first
- changed files: cratedig/{updater.py NEW, __init__.py, gui/main_window.py}, packaging/{make_manifest.py NEW, cratedig.spec, windows/cratedig-update.iss NEW, windows/build_all.ps1, macos/build_all.sh}, pyproject.toml, tests/{test_updater.py NEW, test_make_manifest.py NEW}, .gitignore
- new deps/assets: none (code-only; build_all.sh fetches the usual ffmpeg/ffplay). NOTE: build venv may lack pytest — `pip install -e ".[dev]"` if running tests there.
- build command: bash packaging/macos/build_all.sh 0.3.0   (no prior mac manifest → full → .dmg; commits cratedig-0.3.0-mac.json)
- notes: **SUPERSEDED — do NOT build mac 0.3.0.** Next session is the GitHub online-update migration (→0.4.0, trigger «начинаем переезд», see Backlog), which rebuilds both OS full as the online baseline. This 0.3.0 handoff is kept only as the record of the last offline release.

## Backlog
- **NEXT SESSION = GitHub online-update MIGRATION → 0.4.0 (trigger: user says «начинаем переезд»).** AGREED: full move from OFFLINE to GitHub Releases feed; **minisign** signing (bundle minisign binary per-OS in `packaging/bin/<os>/` like ffmpeg; sign manifest at build, verify in-app via `minisign -V` + embedded pubkey); **auto-check on startup**. Repo feed = `zloishaman1337/cratedig` (PUBLIC; NOTE local `origin` is stale `Sononym_fork.git` → hardcode the slug, don't auto-detect, or repoint remote first). Tasks: (1) `GITHUB_REPO = "zloishaman1337/cratedig"` const; (2) install+bundle minisign; (3) gen keypair, `.key`→gitignore, `.pub` embedded+committed; (4) `updater.py`: `check_latest`/`download_asset`/minisign-verify/auto-apply + **Windows in-app download+launch** (win had none); (5) `main_window` startup auto-check thread + update dialog; (6) `build_all.*`: sign-manifest + `gh release create` publish; (7) rewrite `UPDATE_RULES.md` offline→online; (8) bump 0.4.0; tester→impl→reviewer; (9) Win full build + sign + smoke + gh publish. Reuses `is_newer`/`check_compatible`/`load_update_manifest`/`verify_payload`/`apply_update`/restart-helper. **Supersedes the pending 0.3.0 mac build** (skip it; 0.4.0 rebuilds both OS full as the online baseline).
- **USER PREREQS for the migration**: (a) `gh auth login` on Win (and mac in Session B); (b) back up `cratedig.key` + password after gen, copy key to mac for Session B signing; (c) repo `zloishaman1337/cratedig` already PUBLIC ✓ (consider `git remote set-url origin https://github.com/zloishaman1337/cratedig.git` so push/gh target it). **Baseline trap**: 0.4.0 is the FIRST online-capable build — 0.2/0.3 installs can't auto-pull it (no checker), so 0.4.0 is distributed manually one last time (full installers on the GitHub release); auto-update works from 0.5.0 onward.
- (Superseded) mac 0.3.0 offline `.dmg` — not built; replaced by 0.4.0 migration above. 0.3.0-win build/manifest stay committed as the last offline artifacts.
- **Exercise the DELTA path on the NEXT code-only release** (after 0.3.0 baseline installed on both OS): build_all diffs vs 0.3.0 manifest → should emit `cratedig-update-<ver>.exe` (Win) / `-mac.zip` (mac). **Verify the `DEFAULT_APP_PATHS` allowlist in `make_manifest.py` matches the REAL code-only diff** — if the frozen exe or other expected-app files have unexpected siblings, tune the allowlist (currently conservative/untested against a real diff).
- Exercise CI workflow (`.github/workflows/release.yml`) end-to-end on a pushed `v*` tag.
- Optional: code-signing (Windows EV cert) and macOS notarization (Apple Dev ID $99/yr).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).
- Settings restore-last-folder: only `browser/last_folder` persisted.
- **`worker.request_reload` still issues one `tags_for` query per sample** — batch if libraries grow very large now that the 1000-sample cap is removed.

## Authoritative files
- `ARCHITECTURE.md` — full design + roadmap
- `PACKAGING.md` — distribution/packaging plan: onedir + Inno Setup (Windows) + `.app`/`.dmg` (macOS); §6 = macOS rebuild-after-source-change procedure; "Release process" pointer → UPDATE_RULES.md
- `UPDATE_RULES.md` — authoritative release/update pipeline: two-tier OFFLINE model (delta vs full), per-OS delta delivery (Win = Inno update `.exe`; Mac = zip + in-app apply), trigger scope, version SSOT, two-session Win-then-mac order, macOS HANDOFF block format (includes `tier` field)
- `packaging/release-manifests/` — per-release file-hash manifests committed to repo; diff baseline for automatic tier decision (§7 UPDATE_RULES.md)
- `cratedig/updater.py` — macOS apply-from-file updater (Help → "Apply update from file…") + bash restart helper; pure logic shared with `make_manifest.py`; see UPDATE_RULES.md §7.3b/7.4
- `packaging/make_manifest.py` — build-time manifest gen / diff / tier decision / delta-zip (mac) / win-include (`update-files.iss`); imports `cratedig.updater` for shared schema+hash
- `packaging/windows/cratedig-update.iss` — Windows delta installer (small Inno, same `AppId`, `#include update-files.iss`); see UPDATE_RULES.md §7.3a
- `packaging/windows/build_all.ps1` — Windows one-shot build (venv→deps→icons→PyInstaller→Inno); usage: `pwsh packaging/windows/build_all.ps1 <version>`
- `.claude/commands/update.md` — `/update` session-start command; branches Win-change-mode vs macOS-build-mode based on HANDOFF block + platform
- `README.md` — end-user install guide (installer, first run, data locations, feature tour, troubleshooting)
- `README.dev.md` — developer setup guide (preserved old README)
- `docs/SETTINGS_DESIGN.md` — Settings dialog + config_writer blueprint
- `cratedig/db/schema.sql` — data model
- `config.example.toml` — all settings + OAuth token setup instructions

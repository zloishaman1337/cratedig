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
| db | ✅ | sqlite3, schema.sql, dataclasses; `samples.instrument_class` + `samples.category` (repurposed) columns added via `_ensure_sample_columns`; `set_classification(id, category, instrument_class)` added; all prior schema migrations idempotent |
| scan | ✅ | walk+probe, sha1, upsert; sets both `category` + `instrument_class` from filename; prunes deleted files under scanned roots |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude to sub-slices; `aspect_topk` (per-aspect cosine + mean); `cosine_topk` unchanged |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm` + `zcr` for audio fallback |
| audio.category | ✅ | `classify_category` (keywords→category), `classify_instrument` (keywords→class), `classify_from_audio(duration_sec, centroid_norm, zcr)` audio fallback |
| index.py | ✅ | `analyze_pending` writes both fields via `COALESCE(?,col)` (never wipes good values); `classify_pending` fills both filename-only; `find_similar_aspects` thin wrapper |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | browse uses real collapsible Textual Tree; breadcrumb + DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI + GUI |
| gui | ✅ | Favorite moved to checkable `_fav_btn` QPushButton in preview bar (shortcut F, replaces toolbar action); Find Similar has own row + 5 aspect QCheckBoxes (`_aspect_boxes`, Overall default-checked); toolbar holds Duplicates (D); ALS Explorer is now an embedded page via left sidebar navigator (Samples/Ableton `QStackedWidget`) |
| gui.sample_table | ✅ | columns: Name/Class/SR/Key/BPM/Mood/Tags/Category/Path/Similarity; `SimilarityBarDelegate` paints bar from `Qt.UserRole`; `set_samples(samples, tags, scores, show_path)` — scores clamped [0,1]; similar-mode Filename shows `logic.similar_name` + full-path tooltip |
| gui.metadata_panel | ✅ | NEW: compact read-only widget under preview; shows scan+analyze fields + embedded file tags (mutagen easy=True); `worker.metadataReady` / `request_metadata`; seq-guarded by `_current_seq`; tags list maxHeight 90 |
| gui.worker | ✅ | `similarReady` is 4-arg (seq, samples, source_id, scores); `request_similar` takes aspects via `@Slot(int,int,int,object)`; `request_metadata` added; `Signal(int,int,int,object)` used (NOT Q_ARG(object)) |
| gui.download_pane | ✅ | permanent bottom section; `_search_seq` guard |
| gui.als_explorer | ✅ | `AlsExplorerPanel(QWidget)`: embedded page inside MainWindow, reached via left sidebar "Ableton" nav button (index 1 of `QStackedWidget`); native Qt theme; drag&drop .als; RU/EN i18n; 3-tab QTabWidget (Instruments/Plugins/Tracks); info area + tabs split by vertical QSplitter (user-draggable); VST-scan tab/button REMOVED |
| als (parser) | ✅ | `cratedig/als/parser.py`; stdlib-only (gzip+xml.etree); `parse_als(path)→dict`; AU plugin support (`AuPluginDevice`, classified via ComponentType fourcc `aumu`=instrument); VST3 via `DeviceType` (1=inst,2=fx); VST2 via `NumAudioInputs` fallback; every track dict + `main` dict now include aggregated `instruments: list[str]` and `plugins: list[str]` (names tagged `[VST2]/[VST3]/[AU]/[M4L]`); Ableton Live 10/11/12; racks depth ≤2; no new deps |
| sources.yandex | ✅ | live-tested |
| sources.youtube | ✅ | live-tested; ffmpeg on PATH required |
| sources.freesound | ✅ | live-tested; proxy-bypass session |
| sources.archive | ⚠️ | implemented, untested |
| sources.manager | ✅ | modes: samples→FreeSound, tracks→Yandex+YT fallback |
| metadata (mb/discogs) | ⚠️ | providers written, NOT wired into TUI |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound + archive.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily.
- yandex-music v3.0.0 (`[download]` extra) — mp3 direct, no ffmpeg needed for Yandex.
- yamdl.exe REMOVED.

## Gotchas
- ffmpeg required on PATH for YouTube extraction and waveform decode (falls back to soundfile).
- ffplay required on PATH for TUI/GUI playback and GUI download preview.
- Similarity vector 193-dim; re-run `cratedig analyze` after vector-dim changes; mixed-dim candidates skipped.
- `ASPECT_BLOCKS` slice boundaries: Spectrum [0,80) logmel, Timbre [80,134) mfcc+contrast, Pitch [134,158) chroma, Amplitude [158,193) envelope+scalars. `_b6==FEATURE_DIM` assertion.
- Aspect cosine scores can be negative (cosine distance); scores clamped [0,1] only at UI store time.
- `MainWindow._similar_requested = Signal(int,int,int,object)` — aspects list crosses worker boundary as Python object via QueuedConnection; `Q_ARG(object,…)` raises QMetaType error in this build.
- `classify_pending` re-processes rows whose class stays None each run (churn on large libs — deferred).
- `worker.request_similar` does k separate `get_sample` calls (batch `get_samples_by_ids` deferred).
- Audio-derived class uses DB `duration_sec` (present after scan); `Descriptors` has no duration field.
- Re-running scan prunes stale rows under each scanned root.
- Folder keys from `tui.browser.build_folder_tree` are root-relative slash-joined strings; out-of-root falls back to "other/<basename>".
- `_tree_rows` in tui/app.py is live — used in non-browse `refresh_results` path.
- SQLite connection shared by threads; all `db.conn` access must be guarded by `Database.lock`.
- Windows console cp1251 breaks Unicode — use `$env:PYTHONIOENCODING="utf-8"`.
- FreeSound token = HQ mp3 previews only (full originals need OAuth2, skipped). Use "Client secret/Api key" as token.
- Local VPN proxy (127.0.0.1:2080) breaks TLS → empty results + pip errors. freesound.py uses `trust_env=False`.
- `db.toggle_favorite` re-enters same RLock — safe (Python RLock is reentrant per-thread).
- send2trash is a `[gui]` extra — delete shows install hint if missing.
- Explorer reveal: use single command string with quoted path (list-arg form breaks for paths with spaces).
- `worker.treeReady` signal has 5 args (`roots, folders, samples, tags_by_id, all_tags`).
- Right-click no longer auto-plays (selectRow removed from context menu).
- `logic.tree_rows` emits `(None, "__library__", "Library", False)` row after favorites; root nodes reparented under `"__library__"`.
- GUI waveform: filled envelope polygon (top L→R + bottom R→L); channels averaged as signed lo/hi pairs.
- rename/move: FS op first then DB update; if DB fails, healed by next re-scan (documented intent).
- GUI rename is stem-only; `files.rename_file()` preserves suffix.
- ALS parser is stdlib-only — no new dependency; rides on the existing `[gui]` PySide6 extra.
- `cratedig/als/parser.py` line ~612: `live_set.find("MasterTrack") or live_set.find("MainTrack")` triggers an ElementTree truthiness DeprecationWarning (verbatim from upstream; harmless — falls through only on an empty element).
- ALS Explorer i18n: `_LANG` is a module-global in `als_explorer.py`; single-panel-instance contract — `T()` reads the global directly.
- Standalone `als_explorer/` folder is now redundant (logic lives in `cratedig/als/`) but left in place untracked.
- Mac ALS projects use `AuPluginDevice` (not `PluginDevice`); parser classifies AU via ComponentType fourcc `aumu`=instrument, else effect; `struct.error` caught on malformed fourcc.
- `scan_vst_plugins`/`_vst_dirs`/`_collect_stems` in parser.py are unused by the GUI (dead app code); only `_match_plugin` is still exercised by tests — deferred removal decision.

## Verification
- `python -m compileall cratedig` ok.
- `pytest` 233 passed (+10 ALS/AU tests vs prior 223); `AlsExplorerPanel` smoke OK (`acceptDrops()` True, 3 tabs after `_load_file`, QSplitter present); GUI smoke on `example/minor rnb kazakh 93bpm.als`: 13 instrument rows / 14 plugin rows / 17 track rows; AU plugins (Kontakt 7, LABS, RC-20, etc.) now appear. `MainWindow` smoke OK (10 table cols, 5 aspect boxes Overall-checked, `_fav_btn` checkable, MetadataPanel present, QStackedWidget 2 pages, sidebar switches to ALS page).

## Roadmap v2 — planned epics (design locked 2026-06; see ARCHITECTURE.md "Roadmap v2")
Build order 5→2→1→3→6→4 (cheap surgical first, Simpler last). All schema deltas additive.
- §5 trim cols (do first): remove `Extension` col from `sample_table._COLUMNS`; remove Duration/BPM/Key rows from `logic.format_metadata` (dup w/ table cols). Update smoke test 10→9 cols. Trivial.
- §2 Drag&Drop sample→DAW: `sample_table` startDrag + `QMimeData.setUrls`; pure `logic.file_urls(samples)`. text/uri-list. No schema.
- §1 Smart character tags [DECIDED DSP, no ML]: new pure `audio/descriptors.py::derive_character_tags`; stored as TAGS (reuse tags/sample_tags). `index.tag_pending`. ADD `sample_tags.source` col (auto vs manual). GOTCHA: `wide` tag needs STEREO decode (features.py loads mono). genre labels (vinyl/jazz/soul/acoustic) stay keyword-only (ML deferred).
- §3 Crates [DECIDED]: new tables `crates` + `crate_samples`; db CRUD; synthetic `📦 Crates` branch in `logic.tree_rows` (like Favorites); context-menu "Add to crate ▸"; whole-crate drag = all member URLs.
- §6 Tracks search fix [DECIDED incremental cache]: ROOT CAUSE = `manager.search` tracks mode returns on FIRST backend hit (Yandex) + `metadata/` providers never wired. 6a gather both backends (no early return); 6b wire MB+Discogs lookup, rank by authority (earliest release defeats re-uploads); 6c new `metadata_cache` table, local-first, launch-time stale refresh (TTL `metadata.cache_ttl_days`) — NOT full dump.
  - PREREQ (do before §6b, one-time setup): MusicBrainz = NO key, just `pip install musicbrainzngs` + set real contact email in `[metadata] musicbrainz_useragent` (MB blocks default/anon UA under load). Discogs = `pip install python3-discogs-client` + free personal token (discogs.com → Settings → Developers → Generate token) into `[metadata] discogs_token`. Providers exist (`metadata/musicbrainz.py`,`discogs.py`) but `available()` False until deps+token present, AND not called anywhere yet — wiring `PROVIDERS` registry into search IS §6b. Setting keys alone does nothing pre-wire.
- §4 Simpler editor [DECIDED full scope]: new `gui/simpler_pane.py` REPLACES waveform/preview zone (preview+editor dual role). Pure `audio/editor.py::render_edit` (numpy+soundfile: region/reverse/gain/fade/ADSR) + `write_wav`. Edits render→temp WAV→ffplay (AudioPlayer can't play numpy). Export→`paths.saved_dir` (new config, scanned root, source='edit', `💾 Saved` branch); drag-from-waveform renders to Saved + drops URL to DAW. Worker `request_render`/`renderReady`.

## Next session TODO (carry-over, pre-v2)
- Modernize GUI styling (Foleyard-like) once feature set lands.
- GUI download live-test via Qt UI (worker thread / download pane) — manager-level path verified; Qt worker path still pending.
- sources.archive live-test (untested backend).
- Consider hnswlib ANN for large libraries (deferred — brute force fine at personal scale).
- MEDIUM: `classify_pending` churn on large libs (re-processes None-class rows every run).
- MEDIUM: batch `get_samples_by_ids` to replace k separate `get_sample` calls in `request_similar`.
- LOW: remove redundant standalone `als_explorer/` folder (logic now lives in `cratedig/als/`).
- LOW: decide whether to remove dead `scan_vst_plugins`/`_vst_dirs`/`_collect_stems` from parser.py (unused by GUI; kept for tests).

## Authoritative files
- ARCHITECTURE.md — full design + roadmap
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

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
| db | ✅ | sqlite3, schema.sql, dataclasses; `samples.instrument_class` + `samples.category` (repurposed) columns added via `_ensure_sample_columns`; `metadata_cache` table + DB helpers added for incremental track metadata; `set_classification(id, category, instrument_class)` added; all prior schema migrations idempotent |
| scan | ✅ | walk+probe, sha1, upsert; sets both `category` + `instrument_class` from filename; prunes deleted files under scanned roots |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude to sub-slices; `aspect_topk` (per-aspect cosine + mean); `cosine_topk` unchanged |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm` + `zcr` for audio fallback |
| audio.category | ✅ | `classify_category` (keywords→category), `classify_instrument` (keywords→class), `classify_from_audio(duration_sec, centroid_norm, zcr)` audio fallback |
| index.py | ✅ | `analyze_pending` writes both fields via `COALESCE(?,col)` (never wipes good values); `classify_pending` fills both filename-only; `find_similar_aspects` thin wrapper |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | browse uses real collapsible Textual Tree; breadcrumb + DataTable per folder; hit tables show Year/Album and use matched metadata artist/title; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI + GUI |
| gui | ✅ | Favorite moved to checkable `_fav_btn` QPushButton in preview bar (shortcut F, replaces toolbar action); Find Similar has own row + 5 aspect QCheckBoxes (`_aspect_boxes`, Overall default-checked); toolbar holds Duplicates (D); ALS Explorer is now an embedded page via left sidebar navigator (Samples/Ableton `QStackedWidget`); Roadmap v2 §5/§2 done |
| gui.sample_table | ✅ | columns: Filename/Class/Category/BPM/Key/SR/Tags/Duration/Similarity (Extension removed); `SimilarityBarDelegate` paints bar from `Qt.UserRole`; `set_samples(samples, tags, scores, show_path)` — scores clamped [0,1]; similar-mode Filename shows `logic.similar_name` + full-path tooltip; drag emits selected samples as local file URLs |
| gui.metadata_panel | ✅ | NEW: compact read-only widget under preview; shows scan+analyze fields + embedded file tags (mutagen easy=True); `worker.metadataReady` / `request_metadata`; seq-guarded by `_current_seq`; tags list maxHeight 90 |
| gui.worker | ✅ | `similarReady` is 4-arg (seq, samples, source_id, scores); `request_similar` takes aspects via `@Slot(int,int,int,object)` and batch-resolves hits with `db.get_samples_by_ids`; `request_metadata` added; `Signal(int,int,int,object)` used (NOT Q_ARG(object)) |
| gui.download_pane | ✅ | permanent bottom section; `_search_seq` guard; hit table columns are Title/Artist/Year/Album/Duration/Backend and use matched metadata artist/title/album/year when available |
| gui.als_explorer | ✅ | `AlsExplorerPanel(QWidget)`: embedded page inside MainWindow, reached via left sidebar "Ableton" nav button (index 1 of `QStackedWidget`); native Qt theme; drag&drop .als; RU/EN i18n; 3-tab QTabWidget (Instruments/Plugins/Tracks); info area + tabs split by vertical QSplitter (user-draggable); VST-scan tab/button REMOVED |
| als (parser) | ✅ | `cratedig/als/parser.py`; stdlib-only (gzip+xml.etree); `parse_als(path)→dict`; AU plugin support (`AuPluginDevice`, classified via ComponentType fourcc `aumu`=instrument); VST3 via `DeviceType` (1=inst,2=fx); VST2 via `NumAudioInputs` fallback; every track dict + `main` dict now include aggregated `instruments: list[str]` and `plugins: list[str]` (names tagged `[VST2]/[VST3]/[AU]/[M4L]`); Ableton Live 10/11/12; racks depth ≤2; no new deps |
| sources.yandex | ✅ | live-tested |
| sources.youtube | ✅ | live-tested; ffmpeg on PATH required |
| sources.freesound | ✅ | live-tested; proxy-bypass session |
| sources.archive | ⚠️ | implemented, untested |
| sources.manager | ✅ | modes: samples→FreeSound, tracks→merged Yandex+YouTube hits; tracks search now runs MusicBrainz/Discogs incremental-cache ranking via `cratedig/metadata/ranking.py`; explicit backend mode unchanged |
| metadata (mb/discogs) | ⚠️ | Roadmap v2 §6b/§6c core wiring done: providers registered, incremental `metadata_cache` lookup/rank path wired into tracks search; `SearchHit.extra` enriches title/artist/album/year/score; MusicBrainz UA set to `sufee@proton.me`; Discogs token user-filled; live lookup now bounded/throttled for broad searches |

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
- `db.get_samples_by_ids(ids)` exists; `worker.request_similar` uses it instead of k separate `get_sample` calls.
- Audio-derived class uses DB `duration_sec` (present after scan); `Descriptors` has no duration field.
- Re-running scan prunes stale rows under each scanned root.
- Folder keys from `tui.browser.build_folder_tree` are root-relative slash-joined strings; out-of-root falls back to "other/<basename>".
- `_tree_rows` in tui/app.py is live — used in non-browse `refresh_results` path.
- SQLite connection shared by threads; all `db.conn` access must be guarded by `Database.lock`.
- Windows console cp1251 breaks Unicode — use `$env:PYTHONIOENCODING="utf-8"`.
- FreeSound token = HQ mp3 previews only (full originals need OAuth2, skipped). Use "Client secret/Api key" as token.
- Metadata cache is incremental/local-first only (no full Discogs/MusicBrainz dumps); TTL is `metadata.cache_ttl_days=30`.
- Metadata live lookup is intentionally bounded: `search_live_lookup_min_words=2`, `search_max_live_lookup_hits=3`, one-word searches like `eminem` use cache only; negative misses are cached as `{}` to avoid repeated API calls.
- MusicBrainz requires a real UA/contact and is configured as `sufee@proton.me`; Discogs still needs a user-supplied personal token in `[metadata] discogs_token`.
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
- `pytest -q` ok: 252 passed, 29 ALS parser DeprecationWarnings (`ElementTree` truthiness at `parser.py:798`).
- Focused checks this session: `pytest tests/test_database.py tests/test_sources_manager.py tests/test_gui_logic.py -q` 130 passed.
- Prior GUI/ALS smoke: `AlsExplorerPanel` OK (`acceptDrops()` True, 3 tabs after `_load_file`, QSplitter present); GUI smoke on `example/minor rnb kazakh 93bpm.als`: 13 instrument rows / 14 plugin rows / 17 track rows; AU plugins (Kontakt 7, LABS, RC-20, etc.) now appear. `MainWindow` smoke OK (pre-v2: 10 table cols, 5 aspect boxes Overall-checked, `_fav_btn` checkable, MetadataPanel present, QStackedWidget 2 pages, sidebar switches to ALS page).

## Roadmap v2 — planned epics (design locked 2026-06; see ARCHITECTURE.md "Roadmap v2")
Build order 5→2→1→3→6→4 (cheap surgical first, Simpler last). All schema deltas additive.
- §5 DONE: `Extension` removed from `sample_table._COLUMNS`; Duration/BPM/Key removed from `logic.format_metadata`; tests expect 9 columns/no duplicated metadata rows.
- §2 DONE: sample table drag enabled; selected rows become local file URLs via `QMimeData.setUrls`; pure `logic.file_urls(samples)` added and tested. No schema.
- §1 Smart character tags [DECIDED DSP, no ML]: new pure `audio/descriptors.py::derive_character_tags`; stored as TAGS (reuse tags/sample_tags). `index.tag_pending`. ADD `sample_tags.source` col (auto vs manual). GOTCHA: `wide` tag needs STEREO decode (features.py loads mono). genre labels (vinyl/jazz/soul/acoustic) stay keyword-only (ML deferred).
- §3 Crates [DECIDED]: new tables `crates` + `crate_samples`; db CRUD; synthetic `📦 Crates` branch in `logic.tree_rows` (like Favorites); context-menu "Add to crate ▸"; whole-crate drag = all member URLs.
- §6 Tracks search fix [DECIDED incremental cache]: 6a DONE (`manager.search` tracks mode gathers both Yandex and YouTube hits; used label is `yandex+youtube` when both contribute, single backend name when only one contributes). 6b/6c PARTIAL/core wiring DONE: `metadata_cache` table + DB helpers, MB/Discogs providers registered, `metadata/ranking.py` ranks merged track hits through incremental local-first cache, and `SearchHit.extra` enriches title/artist/album/year/score for GUI/TUI display. MusicBrainz = NO key; UA/contact configured as `sufee@proton.me`. Discogs = `pip install python3-discogs-client` + free personal token in `[metadata] discogs_token`. Runtime latency guard added after live test: one-word searches use cache only; live metadata lookup is limited to the first `metadata.search_max_live_lookup_hits=3` hits; misses are negative-cached. TTL is `metadata.cache_ttl_days=30`; NOT a full Discogs/MusicBrainz dump.
- §4 Simpler editor [DECIDED full scope]: new `gui/simpler_pane.py` REPLACES waveform/preview zone (preview+editor dual role). Pure `audio/editor.py::render_edit` (numpy+soundfile: region/reverse/gain/fade/ADSR) + `write_wav`. Edits render→temp WAV→ffplay (AudioPlayer can't play numpy). Export→`paths.saved_dir` (new config, scanned root, source='edit', `💾 Saved` branch); drag-from-waveform renders to Saved + drops URL to DAW. Worker `request_render`/`renderReady`.

## Next session TODO (carry-over, pre-v2)
- Modernize GUI styling (Foleyard-like) once feature set lands.
- GUI download live-test via Qt UI (worker thread / download pane) — manager-level path verified; Qt worker path still pending.
- sources.archive live-test (untested backend).
- Consider hnswlib ANN for large libraries (deferred — brute force fine at personal scale).
- MEDIUM: `classify_pending` churn on large libs (re-processes None-class rows every run).
- LOW: remove redundant standalone `als_explorer/` folder (logic now lives in `cratedig/als/`).
- LOW: decide whether to remove dead `scan_vst_plugins`/`_vst_dirs`/`_collect_stems` from parser.py (unused by GUI; kept for tests).

## Authoritative files
- ARCHITECTURE.md — full design + roadmap
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

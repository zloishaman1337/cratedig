# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound/Archive into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config; `paths.saved_dir` (default `data/_saved`) for Simpler exports |
| db | ✅ | sqlite3, schema.sql, dataclasses; `samples.instrument_class` + `samples.category` + `samples.classify_attempted`; `metadata_cache`; `sample_tags.source` manual/auto; `crates`+`crate_samples`; all schema migrations idempotent |
| scan | ✅ | walk+probe, sha1, upsert; sets category+class from filename; prunes deleted files; `scan_libraries` also scans `paths.saved_dir` with source='edit' |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude; `aspect_topk`+`cosine_topk` |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` for audio fallback |
| audio.playback | ✅ | `decode_waveform_mono_samples(path, sample_rate=44100)` true mono float32 PCM via ffmpeg with soundfile fallback; `level_gain_db(ref,target)=20*log10(ref/target)` RMS linear loudness helper |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio(duration_sec,centroid_norm,zcr)` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; DSP tags: punchy/soft/clicky/subby/thin/noisy/clean/crunchy/metallic/tonal/percussive/long-tail/tight/muddy/airy/mono; helpers `_crest_factor/_attack_time/_band_flatness`; mutually-exclusive pairs enforced; tape/vinyl deferred-ML |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`/`default_export_name`/`dated_export_dir`; `detect_transients`/`normalize_peak`/`trim_silence`/`snap_to_zero_crossing`/`auto_slice`/`_frames_rms`; flat/zero-signal guard; fade overlap fixed: `fo=min(n-fi,...)` so fade_in+fade_out>n no longer compound-attenuates |
| health | ✅ | `HealthReport` dataclass + `library_health` + `missing_sample_ids` + `format_report`; `cratedig health` CLI; GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan`/`plan_resolution`/`plan_all`/`is_generated_edit`; `cratedig dedup` dry-run CLI |
| index.py | ✅ | `analyze_pending`/`classify_pending`/`tag_pending`/`find_similar_aspects`/`scan_libraries`; `classify_pending` WHERE now `AND classify_attempted=0` |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI+GUI |
| gui | ✅ | Fav=checkable `_fav_btn`; Find Similar has 5 aspect QCheckBoxes; ALS Explorer + Health Dashboard as sidebar pages; QStackedWidget now 3 pages (Samples/Ableton/Health); `DuplicatesDialog` modeless reveal/keep/resolve; `_ab_state` A/B audition (ABState frozen dataclass); `_ab_toggle_action` shortcut 'X' |
| gui.logic | ✅ | `backend_badge(source)->(label,hex)`; `ABState(slot_a,slot_b,current)` frozen dataclass with set_a/set_b/toggle/active_id; `match_als_samples(names,index)->{found,candidates,unresolved}` |
| gui.sample_table | ✅ | 9 cols: Filename/Class/Category/BPM/Key/SR/Tags/Duration/Similarity; drag emits file URLs; context menu Add to crate/New crate |
| gui.metadata_panel | ✅ | compact read-only widget; mutagen easy tags; `worker.metadataReady`/`request_metadata`; seq-guarded |
| gui.simpler_pane | ✅ | Draggable region+fade handles; loop pink region; ADSR overlay; live rendered-preview waveform; zoomable/pannable; playhead; Space toggle; Reverse/Loop/Gain/ADSR knobs; drag-export CopyAction only; Sensitivity knob; Markers checkbox; Normalize/Trim/Snap/Slice; `_staged_render_path`/`_stage_seq`/`_staged_key` pre-render for drag; `request_stage_render`/`set_staged_render_path`/`_consume_staged` |
| gui.health_panel | ✅ | QStackedWidget page index 2; 2-col Metric/Value QTableWidget; Refresh + Remove Missing buttons; signals: `refresh_requested`, `remove_missing_requested` |
| gui.worker | ✅ | `request_render`/`request_index_saved`/`request_delete`/`request_peaks`/`request_metadata`/`request_similar(aspects)`/`request_health`/`request_remove_missing`/`request_als_match`; NEW: `previewReady`+`request_preview_render` (throwaway temp); `stageReady`+`request_stage_render` (drag pre-render); `alsMatchReady` signal; `treeReady` 7-arg |
| gui.download_pane | ✅ | `QProgressBar` 4 states: idle/busy-indeterminate/ok-green/fail-red; `set_progress(pct\|None)` float→determinate/None→indeterminate; `_refresh_meta_btn`+`refresh_metadata_requested` signal; `show_notification(text)`; `set_backend(source)`+`_backend_label` |
| gui.als_explorer | ✅ | embedded page, sidebar "Ableton" nav; 3-tab QTabWidget Instruments/Plugins/Tracks + optional Library Match tab (added after match only); drag&drop .als; RU/EN i18n; `set_match_result`/`matchRequested`/`_btn_match` wired |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; racks depth ≤2 |
| sources.base | ✅ | `safe_filename`+`unique_path`; strips Windows-illegal chars, keeps unicode/cyrillic, caps 120 chars |
| sources.yandex | ✅ | `<TRACK> - <ARTIST>.mp3` via `safe_filename`+`unique_path` |
| sources.youtube | ✅ | ffmpeg on PATH required; `safe_filename`+`unique_path`; path from `requested_downloads[0].filepath` with glob fallback |
| sources.freesound | ✅ | proxy-bypass session; `safe_filename`+`unique_path` |
| sources.archive | ⚠️ | untested; keeps archive's own filename |
| sources.manager | ✅ | samples→FreeSound; tracks→merged Yandex+YouTube; MusicBrainz/Discogs incremental-cache ranking |
| metadata (mb/discogs) | ⚠️ | core wiring done; incremental `metadata_cache`; MB UA=`sufee@proton.me`; Discogs token user-filled; live lookup bounded/throttled |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound + archive.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily.
- yandex-music v3.0.0 (`[download]` extra) — mp3 direct, no ffmpeg needed for Yandex.
- yamdl.exe REMOVED.

## Gotchas
- ffmpeg required on PATH for YouTube extraction and waveform decode (falls back to soundfile).
- ffplay required on PATH for TUI/GUI playback and GUI download preview.
- Similarity vector 193-dim; re-run `cratedig analyze` after vector-dim changes; mixed-dim candidates skipped.
- `ASPECT_BLOCKS` slice boundaries: Spectrum [0,80) logmel, Timbre [80,134) mfcc+contrast, Pitch [134,158) chroma, Amplitude [158,193) envelope+scalars.
- Aspect cosine scores can be negative; clamped [0,1] only at UI store time.
- `MainWindow._similar_requested = Signal(int,int,int,object)` — aspects list as Python object via QueuedConnection; `Q_ARG(object,…)` raises QMetaType error.
- `classify_pending` churn PARTIALLY fixed: dominant fully-unrecognizable churn fixed via `classify_attempted=1` guard; partial rows (instrument hit but no category, e.g. kick_01.wav) still re-process every run because WHERE keeps `category IS NULL` — intentional/tested (test_database.py:320-322).
- SQLite connection shared by threads; all `db.conn` access must be guarded by `Database.lock`.
- Windows console cp1251 breaks Unicode — use `$env:PYTHONIOENCODING="utf-8"`.
- FreeSound token = HQ mp3 previews only (full originals need OAuth2). Use "Client secret/Api key" as token.
- Metadata cache TTL is `metadata.cache_ttl_days=30`; one-word searches use cache only; misses are negative-cached.
- MusicBrainz UA/contact configured as `sufee@proton.me`; Discogs needs user-supplied personal token.
- Local VPN proxy (127.0.0.1:2080) breaks TLS → empty results. freesound.py uses `trust_env=False`.
- `db.toggle_favorite` re-enters same RLock — safe (Python RLock is reentrant per-thread).
- send2trash is a `[gui]` extra; Saved/editor exports (`source='edit'` or under `paths.saved_dir`) physically unlinked directly.
- Explorer reveal: single command string with quoted path (list-arg form breaks for paths with spaces).
- `worker.treeReady` signal has 7 args (`nodes, favorites, crates, crate_samples_by_id, samples, tags_by_id, all_tags`).
- `sample_tags.source`: `manual` for user tags, `auto` for DSP-derived; `Database.set_auto_tags_for` replaces only auto tags.
- `paths.saved_dir` is required on `Paths` dataclass — direct `Paths(...)` construction in tests must pass it.
- `logic.tree_rows` emits `(None, "__library__", "Library", False)` after favorites; root nodes reparented under `"__library__"`.
- ALS parser: `live_set.find("MasterTrack") or live_set.find("MainTrack")` triggers ElementTree truthiness DeprecationWarning (harmless).
- ALS Explorer `_LANG` is module-global; single-panel-instance contract.
- SimplerPane drag trigger = mouse move beyond `startDragDistance()` on canvas without grabbing a handle; `exported`+file committed only on `CopyAction`, cancelled drops unlink the orphan.
- SimplerPane rendered-preview/ADSR/loop paint uses unclamped `_region_view_x()`; handle picking uses clamped `_handle_x()`.
- SimplerPane: `set_mono` auto-recomputes transients at current sensitivity; Slice button cycles region through `auto_slice()` regions; `_slices`/`_slice_idx` reset on `set_sample`.
- Health page auto-refreshes on sidebar open (`_on_nav_clicked` idx==2); Remove Missing deletes DB rows for files absent on disk.
- Downloaded files named `<TRACK> - <ARTIST>.<ext>` via `sources.base.safe_filename`; archive.py exempt.
- `cfg.metadata` is a plain `dict` — read keys with `.get(...)`, NOT `getattr`.
- `DuplicatesDialog` does not live-refresh after deletes; user re-opens via "D" toolbar action to re-query.
- GUI thread blocking: `_on_preview_edit` + `SimplerPane._render_to_saved` call `render_edit`+`write_wav` on GUI thread; explicit export goes via worker; preview+drag now also go via worker (`request_preview_render`/`request_stage_render`) but real DAW end-to-end still needs manual verification.
- A/B audition: loudness-leveling gain is COMPUTED in `MainWindow._play_ab_active` (via `level_gain_db`) but NOT applied to ffplay (AudioPlayer.play has no gain arg) — leveling is inert/deferred.
- Download UX: `worker.request_refresh_metadata` emits `failed(...)` when manager has no `refresh_metadata_cache` (no false success); real re-enrich NOT implemented (DownloadManager.refresh_metadata_cache missing).
- `match_als_samples` 'found' entry shape is inconsistent: single match → unwrapped Sample, multi → list — codified by tests; reveal-in-explorer and crate-from-match are deferred.
- Temp renders (`cratedig_preview_`/`cratedig_stage_<seq>.wav`) cleaned up by unlinking previous-seq file only; a few stragglers may remain in %TEMP% across crashes.

## Verification
- `python -m compileall cratedig` ok.
- `pytest -q` → 552 passed (was 457), 29 ALS DeprecationWarnings. New test files this session: `tests/test_ab_audition.py`, `tests/test_download_pane.py`, `tests/test_als_library_matching.py`; additions to `test_editor.py`, `test_database.py`, `test_gui_logic.py`, `test_simpler_pane.py`.
- `cratedig health` and `cratedig dedup` smoke-run OK on real 653-sample DB.

## Pre-redesign stabilization roadmap — LOCKED 2026-06-06
Do these before visual redesign; see ARCHITECTURE.md for acceptance details.
- Cleanup/docs: DONE.
- Drag-to-DAW reliability: DONE (render-before-exec correct; CopyAction only; cancelled drops unlink orphan; pre-render via `request_stage_render`). REMAINING: manual real-DAW end-to-end with spaces/non-ASCII paths.
- Download/metadata UX: MOSTLY DONE — progress bar+colored completion, `<TRACK> - <ARTIST>` naming, `set_progress`, `show_notification`, `set_backend`/`_backend_label`, `refresh_metadata_requested` signal, `backend_badge`. REMAINING: real metadata re-enrich backend; progress % real only for yt-dlp (others indeterminate).
- Simpler editing intelligence: DONE — live transient markers; Sensitivity knob; Normalize/Trim/Snap/Slice; pre-render for drag.
- Duplicates resolver: DONE. REMAINING: dialog does not live-refresh after deletes.
- Library health dashboard: DONE.
- Expanded character auto-tags: DONE (27 tags; tape/vinyl deferred-ML).
- ALS Explorer library matching: DONE core — `match_als_samples`, worker slot, panel Library Match tab. REMAINING: reveal-in-explorer and crate-from-match not wired.
- A/B audition workflow: MOSTLY DONE — `ABState` dataclass, set_a/set_b/toggle, shortcut 'X', `apply_loudness_leveling` flag. REMAINING: loudness leveling inert (AudioPlayer.play has no gain arg).
- Classify_pending churn: DONE for fully-unrecognized rows (classify_attempted column). Partial-churn intentional/tested.
- Render→worker: DONE — `request_preview_render`/`previewReady`, `request_stage_render`/`stageReady`; SimplerPane uses staged-or-sync fallback.
- Redesign gate: NOT YET — remaining items above must close first.

## Deferred/backlog
- sources.archive live-test (untested backend).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).
- A/B loudness leveling: apply computed gain to ffplay (AudioPlayer.play needs gain arg).
- Download metadata re-enrich: implement DownloadManager.refresh_metadata_cache.
- ALS match reveal-in-explorer + crate-from-match not yet wired.
- `match_als_samples` found-entry shape inconsistency (single→unwrapped vs multi→list) — codified, may need unification.

## Authoritative files
- ARCHITECTURE.md — full design + roadmap
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

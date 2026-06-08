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
| scan | ✅ | walk+probe, sha1, upsert; sets category+class from filename; prunes deleted files; `scan_libraries` also scans `paths.saved_dir` with source='edit'; scan builds desktop mono waveform PCM cache best-effort for local + Saved/edit samples |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude; `aspect_topk`+`cosine_topk` |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` for audio fallback |
| audio.playback | ✅ | `decode_waveform_mono_samples(path, sample_rate=44100)` true mono float32 PCM via ffmpeg with soundfile fallback; desktop waveform cache helpers `mono_preview_cache_path`/`load_mono_preview_cache`/`save_mono_preview_cache`/`ensure_mono_preview_cache`; `AudioPlayer.play` supports `start_sec`/`duration_sec`; `level_gain_db(ref,target)=20*log10(ref/target)` RMS linear loudness helper |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio(duration_sec,centroid_norm,zcr)` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; DSP tags: punchy/soft/clicky/subby/thin/noisy/clean/crunchy/metallic/tonal/percussive/long-tail/tight/muddy/airy/mono; helpers `_crest_factor/_attack_time/_band_flatness`; mutually-exclusive pairs enforced; tape/vinyl deferred-ML |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`/`default_export_name`/`dated_export_dir`; `render_edit` reads only the selected source region from soundfile when `region` is provided, then applies DSP to that slice (preview/export equivalence preserved); `detect_transients`: per-frame PEAK+RMS hybrid, ~5ms hop, smoothed positive first-diff novelty, local-max guard, local median/MAD adaptive floor + percentile/max relative floor, duration-scaled safety cap; `_frames_rms` retained for other callers; `normalize_peak`/`trim_silence`/`snap_to_zero_crossing`/`auto_slice`; fade overlap fixed |
| health | ✅ | `HealthReport` dataclass + `library_health` + `missing_sample_ids` + `format_report`; `cratedig health` CLI; GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan`/`plan_resolution`/`plan_all`/`is_generated_edit`; `cratedig dedup` dry-run CLI |
| index.py | ✅ | `analyze_pending`/`classify_pending`/`tag_pending`/`find_similar_aspects`/`scan_libraries`; `classify_pending` WHERE now `AND classify_attempted=0`; `scan_libraries`/`scan_directory` build mono waveform cache best-effort during scan |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI+GUI |
| gui | ✅ | Fav=checkable `_fav_btn`; top `QToolBar` removed; left sidebar has `Settings`, `Duplicates`, `AB Toggle`, Samples/Ableton/Health buttons; Settings opens in-app `SettingsDialog`; auto-preview on sample selection is persisted via `QSettings` key `playback/auto_preview_on_select` (default true) and gates playback from mouse/arrow selection only; Find Similar has 5 aspect QCheckBoxes in compact grid beside narrowed Metadata panel; ALS Explorer + Health Dashboard as sidebar pages; QStackedWidget now 3 pages (Samples/Ableton/Health); `DuplicatesDialog` modeless reveal/keep/resolve; `_ab_toggle_btn` shortcut 'X'; connects `set_ab_a_requested`/`set_ab_b_requested` from sample_table to `set_ab_slot_a`/`set_ab_slot_b`; `_on_search_progress` maps phases to labels on download pane; `MainWindow` plays simple region previews directly through ffplay start/duration when no reverse/gain/fade/ADSR is active and reconnects `preview_params_changed` to `_on_preview_edit` so active preview restarts/adapts while playing; stop preview invalidates pending preview seq so late `previewReady` is ignored; status bar has compact `_operation_progress` QProgressBar for worker progress (scan indeterminate with processed count when total unknown, analyze/tag determinate done/total percent, done hides after 2s) |
| gui.logic | ✅ | `backend_badge(source)->(label,hex)`; `ABState(slot_a,slot_b,current)` frozen dataclass with set_a/set_b/toggle/active_id; `match_als_samples(names,index)->{found,candidates,unresolved}`; `compute_peaks` uses vectorized `np.reduceat` |
| gui.sample_table | ✅ | 9 cols: Filename/Class/Category/BPM/Key/SR/Tags/Duration/Similarity; Filename stretches, compact fixed metadata cols; Tags hidden by default; Similarity hidden until scores are shown; drag emits file URLs; context menu Add to crate/New crate/"Set as A"/"Set as B"; `set_ab_a_requested(sample_id)`/`set_ab_b_requested(sample_id)` signals |
| gui.metadata_panel | ✅ | compact read-only widget; mutagen easy tags; `worker.metadataReady`/`request_metadata`; seq-guarded |
| gui.settings_dialog | ✅ | `SettingsDialog` with first setting: `Auto-preview selected samples`; emits `auto_preview_changed(bool)` for `MainWindow` persistence |
| gui.simpler_pane | ✅ | Draggable region+fade handles; loop pink region; ADSR overlay; compact live rendered-preview waveform; rendered edit overlay caches peak data and records the source region used, so stale yellow/orange edited preview stays anchored to `_rendered_source_region` during boundary drags instead of stretching/disappearing, and recomputes after handle release rather than every drag move; two-row controls (edit knobs/toggles, then markers/actions/status/export); zoomable/pannable; playhead; Space toggle; Reverse/Loop/Gain/ADSR knobs; Sensitivity knob; Markers checkbox; Normalize/Trim/Snap/Slice; emits `preview_params_changed` when preview-affecting params change while preview is playing (region, Trim/Snap/Slice, Reverse/Loop, Gain, ADSR); clears old mono/transients on `set_sample`; live render debounced and visual-capped; `_staged_render_path`/`_stage_seq`/`_staged_key` pre-render for drag with debounce; `request_stage_render`/`set_staged_render_path`/`_consume_staged`; drag keeps service export regardless of returned drop action and sends a temp absolute local file URL named from the original stem |
| gui.health_panel | ✅ | QStackedWidget page index 2; 2-col Metric/Value QTableWidget; Refresh + Remove Missing buttons; signals: `refresh_requested`, `remove_missing_requested` |
| gui.worker | ✅ | `request_render`/`request_index_saved`/`request_delete`/`request_peaks`/`request_metadata`/`request_similar(aspects)`/`request_health`/`request_remove_missing`/`request_als_match`; `IndexWorker.request_peaks` reads mono cache by sample `file_hash` first, falls back to ffmpeg decode, then saves cache; `previewReady`+`request_preview_render`; `stageReady`+`request_stage_render`; `alsMatchReady`; `treeReady` 7-arg; `searchProgress = Signal(int, str)` emitted with phase label during `search()`; passes progress callback into `DownloadManager.search` |
| gui.download_pane | ✅ | `QProgressBar` 4 states: idle/busy-indeterminate/ok-green/fail-red; `set_progress(pct\|None)` float→determinate/None→indeterminate; `_refresh_meta_btn`+`refresh_metadata_requested` signal; `show_notification(text)`; `set_backend(source)`+`_backend_label` |
| gui.als_explorer | ✅ | embedded page, sidebar "Ableton" nav; 3-tab QTabWidget Instruments/Plugins/Tracks + optional Library Match tab (added after match only); drag&drop .als; RU/EN i18n; `set_match_result`/`matchRequested`/`_btn_match` wired |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; racks depth ≤2 |
| sources.base | ✅ | `safe_filename`+`unique_path`; strips Windows-illegal chars, keeps unicode/cyrillic, caps 120 chars |
| sources.yandex | ✅ | `<TRACK> - <ARTIST>.mp3` via `safe_filename`+`unique_path` |
| sources.youtube | ✅ | ffmpeg on PATH required; `safe_filename`+`unique_path`; path from `requested_downloads[0].filepath` with glob fallback |
| sources.freesound | ✅ | proxy-bypass session; `safe_filename`+`unique_path` |
| sources.archive | ⚠️ | untested; keeps archive's own filename |
| sources.manager | ✅ | samples→FreeSound; tracks→merged Yandex+YouTube; MusicBrainz/Discogs incremental-cache ranking; `DownloadManager.search(...)` accepts optional `progress: Callable[[str], None]`; calls `progress("hits")` before fetch and `progress("metadata")` before rank_track_hits enrichment |
| metadata (mb/discogs) | ⚠️ | core wiring done; incremental `metadata_cache`; MB UA=`sufee@proton.me`; Discogs token user-filled; live lookup bounded/throttled |

## Stack decisions
- Python + PySide6/Textual; librosa+cosine kNN; download = yt-dlp + yandex-music + freesound + archive.
- librosa is OPTIONAL (`[analysis]` extra), imported lazily.
- yandex-music v3.0.0 (`[download]` extra) — mp3 direct, no ffmpeg needed for Yandex.
- yamdl.exe REMOVED.

## Gotchas
- ffmpeg required on PATH for YouTube extraction and waveform decode (falls back to soundfile).
- Desktop waveform previews use a mono PCM cache on disk at `cfg.paths.db.parent / "waveform_cache"` keyed by sample `file_hash`; text `waveform_preview` is NOT used by desktop and remains only the TUI compact preview.
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
- SimplerPane drag: service export is always kept and `exported` signal emitted even when `QDrag.exec` returns `IgnoreAction`, because external Windows apps can report Ignore while consuming the file URL and may read the file after `exec` returns. The MIME URL must be absolute (`Path.resolve()`); Telegram showed relative `data/_saved/...` paths as empty. External drag payload is a temp WAV copy under `%TEMP%/cratedig_drag/<uuid>/` named from the original stem, with repeated `_edit_HHMMSS` suffixes stripped.
- SimplerPane rendered-preview/ADSR/loop paint uses unclamped `_region_view_x()`; handle picking uses clamped `_handle_x()`; rendered edit overlay stores its source region so stale preview peaks stay timeline-anchored during boundary drags; yellow rendered preview recomputes after handle release, not on every drag move.
- SimplerPane: `set_mono` auto-recomputes transients at current sensitivity; Slice button cycles region through `auto_slice()` regions; `_slices`/`_slice_idx` reset on `set_sample`.
- `detect_transients` uses a per-frame PEAK+RMS hybrid so sample-scale spikes survive averaging but short tonal files flood less; local median/MAD + relative floor prevent noisy long-file flooding; safety cap scales with duration instead of a fixed 64; higher sensitivity = fewer, more prominent onsets.
- A/B audition: right-click sample → "Set as A" / "Set as B" to assign slots; press X to toggle-audition. Loudness leveling is COMPUTED (via `level_gain_db`) but NOT applied to ffplay (AudioPlayer.play has no gain arg) — leveling is inert/deferred.
- Preview playback: simple region previews bypass worker temp-WAV rendering and use ffplay `start_sec`/`duration_sec` immediately when reverse/gain/fade/ADSR are inactive; edited previews still render through the worker. While preview is playing, SimplerPane emits `preview_params_changed` on region/control changes (including Gain + ADSR) and MainWindow routes it to `_on_preview_edit` so active preview restarts/adapts to the new params.
- Health page auto-refreshes on sidebar open (`_on_nav_clicked` idx==2); Remove Missing deletes DB rows for files absent on disk.
- Downloaded files named `<TRACK> - <ARTIST>.<ext>` via `sources.base.safe_filename`; archive.py exempt.
- `cfg.metadata` is a plain `dict` — read keys with `.get(...)`, NOT `getattr`.
- `DuplicatesDialog` does not live-refresh after deletes; user re-opens via "D" toolbar action to re-query.
- GUI thread blocking: explicit export/preview/stage render go via worker (`request_render`/`request_preview_render`/`request_stage_render`); drag falls back to synchronous `_render_to_saved` only if staged render is not ready. Live visual render is debounced/capped in GUI thread. Real DAW/Telegram end-to-end still needs manual verification.
- Download UX: `worker.request_refresh_metadata` emits `failed(...)` when manager has no `refresh_metadata_cache` (no false success); real re-enrich NOT implemented (DownloadManager.refresh_metadata_cache missing).
- `match_als_samples` 'found' entry shape is inconsistent: single match → unwrapped Sample, multi → list — codified by tests; reveal-in-explorer and crate-from-match are deferred.
- Temp renders (`cratedig_preview_`/`cratedig_stage_<seq>.wav`) cleaned up by unlinking previous-seq file only; a few stragglers may remain in %TEMP% across crashes.

## Verification
- `python -m compileall cratedig` ok.
- `python -m pytest -q tests/test_editor.py tests/test_gui_logic.py tests/test_playback.py` → 170 passed, 3 warnings.
- `python -m pytest -q` → 570 passed, 32 warnings.
- `python -m pytest -q tests/test_playback.py tests/test_scanner.py tests/test_gui_logic.py` → 134 passed, 3 warnings (deprecated QMouseEvent constructors).
- `python -m pytest -q tests/test_gui_logic.py` → 127 passed, 3 warnings.
- `python -m pytest -q tests/test_ab_audition.py::TestABGUISmoke::test_main_window_has_ab_toggle_shortcut tests/test_gui_logic.py` → 128 passed, 3 warnings.
- `python -m pytest -q tests/test_gui_logic.py::test_main_window_sample_selection_respects_auto_preview_setting tests/test_gui_logic.py::test_main_window_auto_preview_setting_is_saved tests/test_gui_logic.py::test_settings_dialog_exposes_auto_preview_toggle` → 3 passed.
- Focused preview/progress/playback tests → 5 passed.
- `python -m compileall cratedig/gui/main_window.py cratedig/gui/simpler_pane.py` ok.
- `python -m compileall cratedig/gui/main_window.py cratedig/gui/settings_dialog.py` ok.
- `python -m pytest -q tests/test_gui_logic.py::TestSimplerPane::test_region_change_restarts_current_preview tests/test_gui_logic.py::TestSimplerPane::test_gain_and_adsr_change_restart_current_preview tests/test_gui_logic.py::TestSimplerPane::test_live_render_updates_when_gain_changes` → 3 passed.
- `python -m compileall cratedig/gui/simpler_pane.py` ok.
- Recent tests: `tests/test_search_progress.py`; `tests/test_editor.py` covers `TestTransientLongFile` and `render_edit` region equivalence; `tests/test_gui_logic.py` covers drag IgnoreAction keep-file, absolute drag file URL, original-facing drag filename, SampleTable filename visibility, stale mono clearing, rendered-preview source-region anchoring, direct simple region preview without worker render, and stop invalidating pending `previewReady`.
- `cratedig health` and `cratedig dedup` smoke-run OK on real 653-sample DB.

## Pre-redesign stabilization roadmap — LOCKED 2026-06-06
Do these before visual redesign; see ARCHITECTURE.md for acceptance details.
- Cleanup/docs: DONE.
- Drag-to-DAW reliability: DONE (render-before-exec correct; file kept regardless of returned drop action; pre-render via debounced `request_stage_render`). REMAINING: manual real-DAW/Telegram end-to-end with spaces/non-ASCII paths.
- Download/metadata UX: MOSTLY DONE — progress bar+colored completion, `<TRACK> - <ARTIST>` naming, `set_progress`, `show_notification`, `set_backend`/`_backend_label`, `refresh_metadata_requested` signal, `backend_badge`, search phase progress labels ("Searching backends…"/"Enriching metadata…"). REMAINING: real metadata re-enrich backend; progress % real only for yt-dlp (others indeterminate).
- Simpler editing intelligence: DONE — live transient markers (peak+RMS hybrid, local median/MAD, duration-scaled cap); Sensitivity knob; Normalize/Trim/Snap/Slice; debounced pre-render for drag.
- Duplicates resolver: DONE. REMAINING: dialog does not live-refresh after deletes.
- Library health dashboard: DONE.
- Expanded character auto-tags: DONE (27 tags; tape/vinyl deferred-ML).
- ALS Explorer library matching: DONE core — `match_als_samples`, worker slot, panel Library Match tab. REMAINING: reveal-in-explorer and crate-from-match not wired.
- A/B audition workflow: DONE — `ABState` dataclass, set_a/set_b/toggle, shortcut 'X', right-click "Set as A"/"Set as B" context menu. REMAINING: loudness leveling inert (AudioPlayer.play has no gain arg).
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

# COMPACT.md — cratedig

## TL;DR
Local standalone fork of Sononym: PySide6 desktop GUI (primary) + Textual TUI. Index
sample library (SQLite), search by BPM/key/mood/tags, similarity search (librosa
features + cosine kNN), download new audio from YouTube/Yandex/FreeSound/Archive into
the library. Python 3.11+. Personal use. Web UI REMOVED (pivot to standalone desktop).

## Module status
| module | state | note |
|---|---|---|
| config | ✅ | TOML → typed Config (stdlib `tomllib`, read-only, frozen); `paths.saved_dir` (default `data/_saved`) for Simpler exports |
| config_writer | ✅ | NEW; **tomlkit** comment-preserving writer; `load_document`/`write_document` (atomic temp+`os.replace`, `newline=""` byte round-trip); seeds from `config.example.toml` if target missing (next to target only); mutators set paths/audio.extensions/metadata/sources tokens; `source_token_status`→`TokenStatus(name,configured,via_file)` static presence check, token value NEVER in repr |
| db | ✅ | sqlite3, schema.sql, dataclasses; `samples.instrument_class` + `samples.category` + `samples.classify_attempted`; `metadata_cache`; `sample_tags.source` manual/auto; `crates`+`crate_samples`; all schema migrations idempotent |
| scan | ✅ | walk+probe, sha1, upsert; sets category+class from filename; prunes deleted files; `scan_libraries` also scans `paths.saved_dir` with source='edit'; scan builds desktop mono waveform PCM cache best-effort for local + Saved/edit samples |
| audio.features/similarity | ✅ | 193-dim vector; `ASPECT_BLOCKS` maps Overall/Spectrum/Timbre/Pitch/Amplitude; `aspect_topk`+`cosine_topk` |
| audio.analyzer | ✅ | BPM/key/loudness/waveform; `Descriptors` has `centroid_norm`+`zcr` for audio fallback |
| audio.playback | ✅ | `decode_waveform_mono_samples(path, sample_rate=44100)` true mono float32 PCM via ffmpeg with soundfile fallback; desktop waveform cache helpers `mono_preview_cache_path`/`load_mono_preview_cache`/`save_mono_preview_cache`/`ensure_mono_preview_cache`; `AudioPlayer.play` supports `start_sec`/`duration_sec`/**`gain_db`** (appends ffplay `-af volume=<db>dB` when non-zero); `level_gain_db(ref,target)=20*log10(ref/target)` RMS linear loudness helper; `gui.player.Player.play` forwards `gain_db`, `apply_loudness_leveling` flag |
| audio.category | ✅ | `classify_category`, `classify_instrument`, `classify_from_audio(duration_sec,centroid_norm,zcr)` audio fallback |
| audio.descriptors | ✅ | `derive_character_tags` → 27 tags; DSP tags: punchy/soft/clicky/subby/thin/noisy/clean/crunchy/metallic/tonal/percussive/long-tail/tight/muddy/airy/mono; helpers `_crest_factor/_attack_time/_band_flatness`; mutually-exclusive pairs enforced; tape/vinyl deferred-ML |
| audio.editor | ✅ | pure-numpy: `apply_edit`/`render_edit`/`write_wav`/`ADSR`/`default_export_name`/`dated_export_dir`; `render_edit` reads only the selected source region from soundfile when `region` is provided, then applies DSP to that slice (preview/export equivalence preserved); `detect_transients`: per-frame PEAK+RMS hybrid, ~5ms hop, smoothed positive first-diff novelty, local-max guard, local median/MAD adaptive floor + percentile/max relative floor, duration-scaled safety cap; `_frames_rms` retained for other callers; `normalize_peak`/`trim_silence`/`snap_to_zero_crossing`/`auto_slice`; fade overlap fixed |
| health | ✅ | `HealthReport` dataclass + `library_health` + `missing_sample_ids` + `format_report`; `cratedig health` CLI; GUI dashboard wired |
| dedup | ✅ | pure/deterministic no DB writes; `group_duplicates`/`pick_best`/`ResolutionPlan`/`plan_resolution`/`plan_all`/`is_generated_edit`; `cratedig dedup` dry-run CLI |
| index.py | ✅ | `analyze_pending`/`classify_pending`/`tag_pending`/`find_similar_aspects`/`scan_libraries`; `classify_pending` WHERE now `AND classify_attempted=0`; `scan_libraries`/`scan_directory` build mono waveform cache best-effort during scan |
| search.query | ✅ | parameterized SQL filters incl. category |
| tui | ✅ | collapsible Tree; breadcrumb+DataTable per folder; `b` fav; `u` duplicates; `c` classify; auto-preview |
| tui.browser | ✅ | `build_folder_tree` shared by TUI+GUI |
| gui | ✅ | Fav=checkable `_fav_btn`; top `QToolBar` removed; left sidebar has `Settings`, `Duplicates`, `A/B Compare`, Samples/Ableton/Health buttons; Settings opens in-app `SettingsDialog`; auto-preview on sample selection is persisted via `QSettings` key `playback/auto_preview_on_select` (default true) and gates playback from mouse/arrow selection only; Find Similar has 5 aspect QCheckBoxes in compact grid beside narrowed Metadata panel; ALS Explorer + Health Dashboard as sidebar pages; QStackedWidget now 3 pages (Samples/Ableton/Health); `DuplicatesDialog` modeless reveal/keep/resolve; `_ab_compare_btn` opens `ABCompareDialog`; `_open_ab_compare()` builds dialog with `_nodes`/`_crates`/`_worker`/`_player` and wires crate signals; `_on_search_progress` maps phases to labels on download pane; `MainWindow` plays simple region previews directly through ffplay start/duration when no reverse/gain/fade/ADSR is active and reconnects `preview_params_changed` to `_on_preview_edit` so active preview restarts/adapts while playing; stop preview invalidates pending preview seq so late `previewReady` is ignored; status bar has compact `_operation_progress` QProgressBar; `self._toasts = ToastManager(central)` — all `_status_bar.showMessage` also surface as bottom-right toasts via `_on_status_message` (progress ticks matching `\d+/\d+` or ending "processed" stay bar-only; messages containing "error"/"failed" → red toast); `resizeEvent` repositions toasts; `_on_als_match_ready` wires 3 ALS panel signals to `_reveal_path`/`_on_add_to_crate`/`_on_create_crate` once (guarded `_als_match_actions_wired`, init False) and calls `set_crates` |
| gui.toast | ✅ | `ToastManager(host)` + `_Toast(QFrame)` — bottom-right stacked fade toasts; levels info/ok/error; auto-dismiss with fade-out animation |
| gui.ab_dialog | ✅ | `ABCompareDialog(QDialog)` modal A/B compare workspace; midnight-commander two-panel layout (`_SlotPanel` A left, B right); each panel is a QStackedWidget: page0 = folder-tree picker (`QTreeWidget` from `_nodes` FolderNode dict + `QLineEdit` filter), page1 = loaded (filename QLabel + `_MiniWave` + Remove + Add-to-crate `QToolButton` menu); single-click / arrow-key on tree leaf emits `audition(Sample)` → `_on_audition` → `player.play` (live preview while browsing); double-click tree leaf loads into slot; `pulse()` plays a `QGraphicsColorizeEffect`+`QPropertyAnimation` glow on the active panel; shared "A/B Toggle" alternates `player.play` and pulses the active panel; "Reset" clears both, stops; peaks routed by `_PEAK_SEQ_BASE=9_000_000`; emits `add_to_crate_requested(Sample,int)`/`create_crate_requested(Sample)`; A/B loudness leveling WIRED: `_on_peaks_ready` stores per-panel `_loudness` (RMS of mono); when `player.apply_loudness_leveling`, `_toggle`/`_on_audition` pass `gain_db=ab_level_gain_db(active,other)` to boost quieter slot |
| gui.logic | ✅ | `backend_badge(source)->(label,hex)`; `ABState(...)` frozen dataclass; `match_als_samples(...)`; `compute_peaks` vectorized `np.reduceat`; `ab_level_gain_db(active,other)`→dB to boost quieter slot to louder ref (0 if active louder or any input≤0); `should_preview_hit(hit)`→`bool(hit.preview_url)` |
| gui.platform_files | ✅ | NEW; `reveal_in_file_manager(path)`: win32 `explorer /select,"<path>"` (single string), darwin `open -R <path>`, else `xdg-open <dirname>`; all exceptions swallowed; `main_window._reveal_path` delegates here |
| gui.sample_table | ✅ | 9 cols: Filename/Class/Category/BPM/Key/SR/Tags/Duration/Similarity; Filename stretches, compact fixed metadata cols; **Tags VISIBLE by default** (pref `browser/show_tags_column`); Similarity hidden until scores shown; `settings` param + `set_tags_visible`/`save_column_state`/`_restore_column_state` (gated by `browser/remember_column_*`); drag emits file URLs; context menu Add to crate/New crate |
| gui.metadata_panel | ✅ | compact read-only widget; mutagen easy tags; `worker.metadataReady`/`request_metadata`; seq-guarded |
| gui.settings_dialog | ✅ | 3-tab `SettingsDialog` (Preferences/Project Config/Paths); signals `preferences_changed(str,object)` + `config_written()` + legacy `auto_preview_changed(bool)` shim; ctor `SettingsDialog(auto_preview_enabled, settings=QSettings, parent)`; MainWindow passes `settings=self._settings` (shared store) |
| gui.settings_tabs | ✅ | NEW package: `_keys.py` (QSettings key constants + `DEFAULTS` + `TYPES`, single source of truth); `preferences_tab.py` (QSettings-backed, 4 groupboxes, emits `preference_changed`); `project_config_tab.py` + `paths_tab.py` (config_writer-backed, Save→`write_document`→`config_written`; read display values WITHOUT creating config.toml; token fields Password echo, empty=leave-unchanged, `_CLEAR` sentinel; backend ✅/❌ status, no token values) |
| gui.simpler_pane | ✅ | Draggable region+fade handles; loop pink region; ADSR overlay; compact live rendered-preview waveform; rendered edit overlay caches peak data and records the source region used, so stale yellow/orange edited preview stays anchored to `_rendered_source_region` during boundary drags instead of stretching/disappearing, and recomputes after handle release rather than every drag move; two-row controls (edit knobs/toggles, then markers/actions/status/export); zoomable/pannable; playhead; Space toggle; Reverse/Loop/Gain/ADSR knobs; Sensitivity knob; Markers checkbox; Normalize/Trim/Snap/Slice; emits `preview_params_changed` when preview-affecting params change while preview is playing; `_staged_render_path`/`_stage_seq`/`_staged_key`; `_Knob` wraps a `_KnobDial(QDial)` subclass that overrides mousePress/Move/Release/DoubleClick directly (no event filter): left-press starts relative vertical drag and suppresses the native angle jump; double-click emits `doubleClicked` → `_Knob._reset_to_default()` sets knob to `_default` (Gain/A/D/R=0, Sustain=1, Sens=0.5); applies to all 6 editor knobs |
| gui.health_panel | ✅ | QStackedWidget page index 2; 2-col Metric/Value QTableWidget; Refresh + Remove Missing buttons; signals: `refresh_requested`, `remove_missing_requested` |
| gui.worker | ✅ | `request_render`/`request_index_saved`/`request_delete`/`request_peaks`/`request_metadata`/`request_similar(aspects)`/`request_health`/`request_remove_missing`/`request_als_match`; `IndexWorker.request_peaks` reads mono cache by sample `file_hash` first, falls back to ffmpeg decode, then saves cache; `previewReady`+`request_preview_render`; `stageReady`+`request_stage_render`; `alsMatchReady`; `treeReady` 7-arg; `searchProgress = Signal(int, str)` emitted with phase label during `search()`; passes progress callback into `DownloadManager.search`; `request_delete` reads `safety/recycle_bin_for_saved` (default True) → saved/edit files now go to recycle bin (trash before `db.delete_sample`; trash failure leaves file+row intact); `request_touch_recent_folder`; `request_refresh_metadata` calls `mgr.refresh_metadata_cache()` and emits `searchReady(self._last_search_seq, hits, "metadata refreshed")` only when hits non-empty; `_last_search_seq` initialized to 0 in __init__ |
| gui.download_pane | ✅ | `QProgressBar` 4 states: idle/busy-indeterminate/ok-green/fail-red; `set_progress(pct\|None)` float→determinate/None→indeterminate; `_refresh_meta_btn`+`refresh_metadata_requested` signal; `show_notification(text)`; `set_backend(source)`+`_backend_label`; `settings` param → default mode from `search/default_download_mode` (persists on change); `_on_row_changed` auto-emits `preview_requested` when `playback/preview_download_on_row_select` (default off) AND `should_preview_hit(hit)` |
| gui.als_explorer | ✅ | embedded page, sidebar "Ableton" nav; 3-tab QTabWidget Instruments/Plugins/Tracks + optional Library Match tab (added after match only); drag&drop .als; RU/EN i18n; `set_match_result`/`matchRequested`/`_btn_match` wired; NEW signals `reveal_requested(str)`/`add_to_crate_requested(object,int)`/`create_crate_requested(object)` + normalizers `_emit_reveal_for`/`_emit_add_to_crate_for`/`_emit_create_crate_for` (`_normalize_entry` returns None for empty list → emitters skip); per-found-row context menu (Reveal / New crate / Add to crate submenu); `set_crates(crates)` |
| als (parser) | ✅ | stdlib-only; `parse_als(path)→dict`; AU/VST2/VST3/M4L; racks depth ≤2 |
| sources.base | ✅ | `safe_filename`+`unique_path`; strips Windows-illegal chars, keeps unicode/cyrillic, caps 120 chars |
| sources.yandex | ✅ | `<TRACK> - <ARTIST>.mp3` via `safe_filename`+`unique_path` |
| sources.youtube | ✅ | ffmpeg on PATH required; `safe_filename`+`unique_path`; path from `requested_downloads[0].filepath` with glob fallback |
| sources.freesound | ✅ | proxy-bypass session; `safe_filename`+`unique_path` |
| sources.archive | ⚠️ | hardened: fetch wrapped in try/except→DownloadResult(ok=False,error=…); `item.files` materialized via list(); live archive.org test still pending |
| sources.manager | ✅ | samples→FreeSound; tracks→merged Yandex+YouTube; MusicBrainz/Discogs incremental-cache ranking; `DownloadManager.search(...)` accepts optional `progress: Callable[[str], None]`; calls `progress("hits")` / `progress("metadata")`; retains `_last_query`/`_last_mode`/`_last_hits`; NEW `refresh_metadata_cache()->list[SearchHit]` re-ranks last hits with force_live=True |
| metadata (mb/discogs) | ✅ | core wiring done; incremental `metadata_cache`; MB UA=`sufee@proton.me`; Discogs token user-filled; live lookup bounded/throttled; `rank_track_hits(..., force_live=False)`: True bypasses cache TTL short-circuit AND min-words/specificity gate, forces provider.lookup (still respects provider.available()); False path unchanged |

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
- Explorer reveal: `gui/platform_files.py` `reveal_in_file_manager(path)` — single command string with quoted path (list-arg form breaks paths with spaces); macOS uses `open -R`; Linux uses `xdg-open <dirname>`.
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
- A/B quick-audition (X shortcut / right-click "Set as A"/"Set as B") REMOVED from GUI. `ABState` (logic.py) + `level_gain_db` (playback.py) kept as pure tested helpers but are now unused by the GUI.
- A/B Compare dialog: single-click or arrow-key on tree leaf auditions (plays) the sample immediately; double-click loads into slot; "A/B Toggle" alternates playback and pulses (`QGraphicsColorizeEffect` glow) the active panel.
- Notifications appear as bottom-right toasts (`ToastManager` in `gui/toast.py`) mirroring status-bar messages; progress tick messages matching `\d+/\d+` or ending "processed" stay bar-only and are not toasted.
- `_Knob` dial jump suppression and double-click reset are implemented via a `_KnobDial(QDial)` subclass overriding mouse handlers DIRECTLY — an `installEventFilter`-based approach was tried first and reverted because it passed offscreen QTest but failed on real Windows (native double-click bypassed the filter, leaving the angle jump).
- Preview playback: simple region previews bypass worker temp-WAV rendering and use ffplay `start_sec`/`duration_sec` immediately when reverse/gain/fade/ADSR are inactive; edited previews still render through the worker. While preview is playing, SimplerPane emits `preview_params_changed` on region/control changes (including Gain + ADSR) and MainWindow routes it to `_on_preview_edit` so active preview restarts/adapts to the new params.
- Health page auto-refreshes on sidebar open (`_on_nav_clicked` idx==2); Remove Missing deletes DB rows for files absent on disk.
- Downloaded files named `<TRACK> - <ARTIST>.<ext>` via `sources.base.safe_filename`; archive.py exempt.
- `cfg.metadata` is a plain `dict` — read keys with `.get(...)`, NOT `getattr`.
- `DuplicatesDialog` does not live-refresh after deletes; user re-opens via "D" toolbar action to re-query.
- GUI thread blocking: explicit export/preview/stage render go via worker (`request_render`/`request_preview_render`/`request_stage_render`); drag falls back to synchronous `_render_to_saved` only if staged render is not ready. Live visual render is debounced/capped in GUI thread. Real DAW/Telegram end-to-end still needs manual verification.
- `rank_track_hits(force_live=True)` is the metadata "refresh" path; refresh re-ranks `manager._last_hits` and the pane updates via `searchReady` reusing the last search seq; empty result → no searchReady emitted (avoids clobbering the pane).
- ALS match found-entry shape (single Sample vs list[Sample]) normalized by `_normalize_entry`; empty list → None → action skipped (no IndexError).
- Temp renders (`cratedig_preview_`/`cratedig_stage_<seq>.wav`) cleaned up by unlinking previous-seq file only; a few stragglers may remain in %TEMP% across crashes.
- Settings: QSettings org/app `("cratedig","cratedig")` NATIVE format; all keys + defaults live in `gui/settings_tabs/_keys.py` (`DEFAULTS`/`TYPES`) — read via `_keys` constant, never a literal. MainWindow passes `settings=self._settings` so dialog/tabs/worker share ONE store.
- Settings behavior-change defaults (intentional, tested): Tags column VISIBLE, library tree NO auto-expand, Health NO auto-refresh on open, saved/edit deletes → recycle bin. config.toml edits require app restart (frozen Config, no live worker reload).
- tomlkit is a runtime dep (config_writer); config.py stays on stdlib tomllib for reads.

## Verification
- `python -m compileall cratedig` ok.
- `python -m pytest -q` → 752 passed (was 706; +test_platform_files, +test_metadata_refresh, +test_archive, +test_als_match_actions).
- `python -m compileall cratedig/gui/toast.py cratedig/gui/ab_dialog.py cratedig/gui/main_window.py cratedig/gui/sample_table.py cratedig/gui/simpler_pane.py cratedig/gui/platform_files.py` ok.
- Offscreen smoke: ABCompareDialog audition+toggle+pulse OK; MainWindow toast routing OK (info/error toast, progress filtered); AB toggle attrs gone; `_KnobDial` double-click reset OK; ALS panel reveal+crate signals wired OK.
- `cratedig health` and `cratedig dedup` smoke-run OK on real 653-sample DB.

## Pre-redesign stabilization roadmap — LOCKED 2026-06-06
Do these before visual redesign; see ARCHITECTURE.md for acceptance details.
- Cleanup/docs: DONE.
- Drag-to-DAW reliability: DONE (render-before-exec correct; file kept regardless of returned drop action; pre-render via debounced `request_stage_render`). REMAINING: manual real-DAW/Telegram end-to-end with spaces/non-ASCII paths.
- Download/metadata UX: DONE — progress bar+colored completion, `<TRACK> - <ARTIST>` naming, `set_progress`, `show_notification`, `set_backend`/`_backend_label`, `refresh_metadata_requested` signal, `backend_badge`, search phase progress labels; real metadata re-enrich implemented (`refresh_metadata_cache` force-live re-rank of last hits). REMAINING: progress % real only for yt-dlp (others indeterminate).
- Simpler editing intelligence: DONE — live transient markers (peak+RMS hybrid, local median/MAD, duration-scaled cap); Sensitivity knob; Normalize/Trim/Snap/Slice; debounced pre-render for drag; knob vertical-drag + double-click reset; no slam-to-max on click.
- Duplicates resolver: DONE. REMAINING: dialog does not live-refresh after deletes.
- Library health dashboard: DONE.
- Expanded character auto-tags: DONE (27 tags; tape/vinyl deferred-ML).
- ALS Explorer library matching: DONE — `match_als_samples`, worker slot, panel Library Match tab, reveal-in-explorer and crate-from-match wired via `gui/platform_files.py` + ALS panel signals.
- A/B audition workflow: DONE — `ABCompareDialog` modal (tree picker, per-slot `_MiniWave`, single-click audition, double-click load, panel pulse glow, Remove, Add-to-crate, A/B Toggle, Reset). Quick-audition (X shortcut / Set as A/B context menu) REMOVED. Loudness leveling now WIRED: `AudioPlayer.play(gain_db=)` ffplay `-af volume`, `ab_level_gain_db` boosts quieter slot, gated by `playback/ab_loudness_leveling` pref.
- Settings window: DONE — 3-tab `SettingsDialog` (Preferences via QSettings, Project Config + Paths via `config_writer`/tomlkit). ~25 settings wired. Path/config edits = write config.toml + "restart required" toast (NO live worker reload). See docs/SETTINGS_DESIGN.md.
- Classify_pending churn: DONE for fully-unrecognized rows (classify_attempted column). Partial-churn intentional/tested.
- Render→worker: DONE — `request_preview_render`/`previewReady`, `request_stage_render`/`stageReady`; SimplerPane uses staged-or-sync fallback.
- Cross-platform reveal: DONE — `gui/platform_files.py` macOS-portable (`open -R`); REMAINING: full macOS runtime verification of the app (user has a Mac, pending manual run).
- Redesign gate: PRE-REDESIGN STEPS 1+2 COMPLETE. Next session = FINAL GLOBAL REDESIGN (step 3).

## Deferred/backlog
- sources.archive live-test (hardened but archive.org live run still pending).
- Consider hnswlib ANN for large libraries (brute force fine at personal scale).
- Settings restore-last-folder: only `browser/last_folder` persisted (full recent-folders UI minimal); A/B loudness uses downsampled-mono RMS proxy (not true LUFS).
- `match_als_samples` found-entry shape inconsistency (single→unwrapped vs multi→list) — codified, may need unification.
- Full macOS runtime verification (real-DAW/Telegram drag, archive.org live test).
- Duplicates dialog live-refresh after deletes.

## Authoritative files
- ARCHITECTURE.md — full design + roadmap
- docs/SETTINGS_DESIGN.md — Settings dialog + config_writer blueprint (QSettings key table, mutator API)
- cratedig/db/schema.sql — data model
- config.example.toml — all settings + OAuth token setup instructions

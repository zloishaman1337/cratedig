# PLAN — cratedig 0.5.0 (implementation blueprint)

> **Status:** PLANNING COMPLETE — no code written yet. Next `/update` session: say
> «продолжаем» and execute the phases below in order.
> **Version target:** `0.4.1` → **`0.5.0`** (minor — user-visible features). Bump
> `pyproject.toml` + `cratedig/__init__.__version__` together, ONCE, in the
> implementation session (UPDATE_RULES §2). Shipped-surface IS touched → full
> release stage fires (Win installer this session, mac handoff after).
> **Session mode when implementing:** Session 1 «Change + Windows».

This release delivers four features. Feature 4 is gated behind a research spike
and may slip to 0.6.0 if the closed formats prove unparseable — features 1–3 are
the committed scope.

---

## Feature 1 — Installed-plugin detection for Ableton projects

**Goal:** when an `.als` is loaded, mark each referenced plugin as ✓ installed /
✗ missing on this system. Scan all standard plugin dirs per OS across all formats
(VST2/VST3/AU/AAX), plus user-configured custom dirs.

**UX decision (locked):** inline ✓/✗ badge per row in the existing **Plugins** and
**Instruments** tabs of `als_explorer.py`. Scan runs once, cached to disk; manual
**Rescan plugins** button to refresh.

### New module: `cratedig/plugins/scanner.py`

Pure + thin-I/O layer (mirror `updater.py` split: pure helpers unit-testable, I/O
isolated).

- `standard_plugin_dirs() -> dict[str, list[Path]]` — keyed by format
  (`vst2`/`vst3`/`au`/`aax`), branches on `sys.platform`. Only return dirs that
  exist.
  - **Windows:**
    - vst3: `%CommonProgramFiles%\VST3` (`C:\Program Files\Common Files\VST3`)
    - vst2: `C:\Program Files\VSTPlugins`, `C:\Program Files\Steinberg\VSTPlugins`,
      `%CommonProgramFiles%\VST2` (VST2 has no canonical dir → custom dirs matter most)
    - aax: `%CommonProgramFiles%\Avid\Audio\Plug-Ins`
  - **macOS:**
    - vst3: `/Library/Audio/Plug-Ins/VST3`, `~/Library/Audio/Plug-Ins/VST3`
    - vst2: `/Library/Audio/Plug-Ins/VST`, `~/Library/Audio/Plug-Ins/VST`
    - au:   `/Library/Audio/Plug-Ins/Components`, `~/Library/Audio/Plug-Ins/Components`
    - aax:  `/Library/Application Support/Avid/Audio/Plug-Ins`
- `scan_installed(dirs: list[Path]) -> InstalledIndex` — walk dirs (shallow, plus
  one level), collect plugin files/bundles by extension:
  `.vst3`, `.dll` (win vst2), `.vst`/`.component` (mac bundles), `.aaxplugin`.
  Build a normalized set of **stems** (lowercased, strip extension, strip common
  noise like ` x64`, version suffixes). Return a dataclass holding `stems: set[str]`
  + per-format breakdown + a `signature` (sorted dir mtimes+counts) for cache
  invalidation.
- `match_installed(display_name: str, index: InstalledIndex) -> bool` — reuse the
  fuzzy approach already in `als/parser.py:833 _match_plugin` (exact stem, then
  substring both directions). **Move `_match_plugin` into this module** and have
  the parser import it (single source of truth — see analyst note below).
- Disk cache: `user_data_dir()/plugin_index.json` (`paths.user_data_dir()`).
  `load_or_scan(custom_dirs, force=False)` returns cached index when `signature`
  matches; rescans on mismatch or `force=True`.

### Config: custom plugin dirs

- `config.example.toml`: add
  ```toml
  [plugins]
  scan_dirs = []   # extra directories to scan for installed plugins
  ```
- `config.py`: extend the typed `Config` with `plugins.scan_dirs: list[str]`
  (read via stdlib `tomllib`, default `[]`). Follow the existing pattern; keep
  read-only.
- `config_writer.py`: nothing structural — tomlkit round-trips the new table. The
  Settings UI writes `scan_dirs` through the existing `write_document` path.
- **Settings UI:** add a dir-list editor. Reuse the add/remove-directory widget
  pattern from `cratedig/gui/settings_tabs/paths_tab.py`. Put it on the **Paths**
  tab (new "Plugin scan folders" group) — avoids a whole new tab. On save it
  triggers `_on_config_written()` → which already prompts restart; but plugin
  index should just rescan, so wire a lighter path (rescan on next project load).

### GUI wiring (`als_explorer.py` + worker)

- Scanning is potentially slow → run on the **worker thread**, never the UI thread.
  Mirror the existing `matchRequested`/`request_als_match`/`alsMatchReady` signal
  triad in `main_window.py:384-389` and `worker.py`. Add:
  - `IndexWorker.scan_plugins(custom_dirs, force)` → emits `pluginIndexReady(index)`.
  - `AlsExplorerPanel` gains `set_plugin_index(index)` and renders badges in
    `_collect_rows` / `_build_tab_widget` (the row already has a free column —
    append a fixed-width ✓/✗ label colored `C_OK`/`C_ERR`).
- Trigger: on project load (`_load_file`/`_render`), request a cached index
  (`force=False`); also add a **Rescan plugins** button in the header bar
  (next to "Match library") that requests `force=True` + a toast.
- Native Live devices (Operator, EQ Eight, …) are always "installed" → mark them
  ✓ unconditionally (they ship with Live; only 3rd-party VST2/VST3/AU rows get a
  real disk check). M4L: treat as ✓ if Live present — note in UI as "n/a" to avoid
  false ✗.
- **AAX caveat:** Ableton never references AAX plugins (Pro Tools only), so AAX
  dirs are scanned per the request but will rarely match an `.als` row. Document,
  don't special-case.

### Tests (`tests/test_plugin_scanner.py`)

TDD — write first:
- `standard_plugin_dirs` returns the right keys per platform (monkeypatch
  `sys.platform`).
- `scan_installed` over a tmp tree with fake `.vst3`/`.dll`/`.component` files →
  expected stems; bundles (dirs ending `.vst3`/`.component`) counted as one.
- `match_installed`: exact, substring, case-insensitive, no-match.
- cache: signature stable when dirs unchanged; invalidates on new file.
- `config.py` parses `[plugins].scan_dirs`; missing table → `[]`.

---

## Feature 2 — Waveform editor performance (zoom / pan / playhead)

**Root cause (confirmed in code):** `_WaveCanvas.paintEvent` →
`_draw_waveform` → `compute_peaks(clean, width)` **rebins from raw samples on
every repaint**. The 30 ms playhead poll (`main_window.py:358-363`) calls
`set_playhead` → `update()` → full repaint → full rebin. For a 4-min file
(~10M float32 samples) every cursor tick rebins millions of samples. Pan/zoom
likewise rebin live.

**Fix strategy — three independent wins:**

1. **Precomputed multi-resolution peak cache (mip pyramid).** On `set_mono`,
   build a small pyramid of (min,max) pairs at decreasing resolutions (e.g.
   base = decimate to N levels, each ÷2). Store in the canvas. `paintEvent`
   picks the level whose bin count ≥ pixel width, then does a cheap rebin of the
   already-reduced level (thousands of pairs, not millions). Build the pyramid
   **on the worker thread** (it already decodes mono via
   `decode_waveform_mono_samples`) and hand peaks to the canvas, OR build lazily
   once on first paint and cache. Keep raw `_mono` only for the sub-3-samples/px
   exact polyline path (already guarded at `samples_per_px <= 3.0`).
   - Add a pure helper to `logic.py`: `build_peak_pyramid(samples, levels) ->
     list[np.ndarray]` (each level an (n,2) array) — unit-testable, no Qt.
   - `paintEvent` interval rebinning then operates on the chosen level via
     `np.minimum.reduceat`/`maximum.reduceat` (same math as `compute_peaks`, but
     on ~10⁴ inputs).

2. **Playhead as a cheap overlay, not a full rebin.** Cache the rendered
   waveform envelope as a `QPixmap` (or cache the computed `QPolygonF`s) keyed by
   `(view, width, rendered_peaks_version)`. On playhead-only changes, repaint
   blits the cached pixmap + draws the single playhead line. Invalidate the cache
   on view/zoom/region/edit change. This removes per-tick rebinning entirely.
   - Optional refinement: `update(QRect)` only the old+new playhead columns
     instead of the whole widget — but pixmap-blit is simpler and sufficient.

3. **Pan = pure view shift (already partly done).** `_set_view` already skips
   `_recompute_rendered` when span is unchanged (`simpler_pane.py:140-153`). With
   the pyramid + pixmap cache, pan just changes `view` and blits a translated
   slice; rebin only when the visible level's bin density changes meaningfully.

**Target:** 4-min sample pans/zooms/scrubs at ≥30 fps with no visible jank.

### Tests (`tests/test_simpler_perf.py` + extend `tests/test_logic*.py`)

- `build_peak_pyramid`: correct level count, each level ≈ half the previous,
  level 0 preserves global min/max, empty/short inputs safe.
- Pyramid-based rebin equals `compute_peaks` envelope within tolerance for a
  known signal (ensures no visual regression).
- Behavioral: simulate N `set_playhead` calls and assert the envelope rebin
  function is **not** called (cache hit) — guards the regression that caused the
  lag. (Use a counter/spy on the rebin path.)

---

## Feature 3 — Version label + update-available notice (bottom-left)

**Goal:** always show app version bottom-left; show an "update available" hint
when the startup check finds a newer release.

- `QStatusBar` exists (`main_window.py:350`). Add a permanent widget on the LEFT
  via `self._status_bar.addWidget(...)` (left-aligned; `addPermanentWidget` is
  right side — use `addWidget` for bottom-left).
  - Label text: `cratedig 0.5.0` (read `cratedig.__version__`).
- Update hint: the silent check already emits `found(release)` →
  `_on_update_available` (`main_window.py:633-661`). Add: on `found`, change the
  bottom-left label to a clickable link style — e.g. `cratedig 0.5.0 · ⬆ 0.5.1
  available` colored `ACCENT`. Clicking it re-opens the existing update dialog
  (`_on_update_available(release)` / `_start_update_download`).
- Dev (non-frozen) builds never run the check (`_maybe_check_updates` guards on
  `sys.frozen`) → label shows version only. That's fine.

### Tests
- Pure: a tiny formatter `version_status_text(current, latest|None) -> str` in
  `logic.py` (no Qt) → `"cratedig 0.5.0"` when latest is None, with update suffix
  otherwise. Unit-test both branches.

---

## Feature 4 — Bitwig (.bwproject) + Nuendo (.npr) scanning  ⚠️ RESEARCH SPIKE FIRST

**Reality check:** Ableton `.als` is gzipped **XML** (`als/parser.py` uses
`gzip` + `ElementTree`). **Bitwig `.bwproject` and Nuendo `.npr` are proprietary
BINARY formats, undocumented.** "Copy the Ableton functionality" is not a
copy-paste — each needs its own parser, and full per-track device trees may be
impossible to recover reliably.

**Decision (locked): spike before committing.** The implementation session for
Feat 4 BEGINS by inspecting **real sample project files YOU provide**:

1. **You provide:** at least one real `.bwproject` and one `.npr` (ideally each
   with known VST/sample content so we can verify extraction).
2. **Spike (read-only investigation):**
   - `.bwproject` is a ZIP container → unzip, list members, inspect `contents`
     (Bitwig stores a binary `.bwproject` blob; sometimes plugin/sample paths
     appear as readable strings). Grep for plugin names / sample paths as UTF-8/
     UTF-16 strings.
   - `.npr` (Nuendo/Cubase) → binary; scan for embedded plugin identifiers
     (VST3 GUIDs, plugin name strings) and referenced media paths.
   - Determine realistically extractable signal: (a) referenced sample files,
     (b) plugin name strings, (c) maybe track names. Per-track device chains are
     likely NOT recoverable.
3. **Then decide depth** and implement to that bar — best-effort extraction
   surfaced in new tabs, reusing the `als_explorer.py` panel structure and the
   Feat 1 installed-plugin matcher.

**Architecture once depth is known:**
- New parsers: `cratedig/bitwig/parser.py`, `cratedig/nuendo/parser.py`, each
  exposing `parse_*(path) -> dict` shaped like `parse_als`'s return (subset is
  fine — `tracks`/`plugins`/`samples`/`version`).
- New panels: generalize `AlsExplorerPanel` into a reusable base
  (`ProjectExplorerPanel`) parameterized by parser + file extension + labels;
  `als_explorer` becomes one instance. Bitwig/Nuendo panels = new instances.
- New nav buttons + stacked pages in `main_window.py` (the sidebar nav at
  `:272-322` and `QStackedWidget` at `:266-270` — add "Bitwig" and "Nuendo"
  buttons/pages; extend `_nav_group` ids and `_on_nav_clicked`).
- Feature 1's installed-plugin matcher is format-agnostic → reused directly.

**If the spike shows the formats yield too little:** ship Feat 4 as
"samples-only" project checkers (referenced media existence, like the existing
`_check_samples`) and defer device detection, or punt to 0.6.0. Features 1–3
still ship as 0.5.0.

---

## Execution order (implementation session)

Per `rules/agents.md` pipeline (planner done → this doc). Suggested phase order,
each gated by `tester` green before moving on:

1. **Feat 2 (waveform perf)** — self-contained, highest daily-use value, no new
   deps. tester → developer → tester.
2. **Feat 1 (plugin scan)** — new module + config + UI + worker wiring.
3. **Feat 3 (version label)** — small, depends on nothing.
4. **Feat 4 spike** — ONLY after you supply sample files; investigate → reassess
   scope → implement or defer.
5. **reviewer** over the full diff → **documentation** updates COMPACT.md.
6. **Release stage (Session 1):** bump to 0.5.0, `build_all.ps1 0.5.0`, tier via
   manifest diff (new module + assets likely → could be delta if no dep change;
   `config.example.toml` change is a bundled-asset change → may force FULL —
   confirm via `make_manifest` diff), smoke-launch, write macOS HANDOFF block.

## Open items to confirm at implementation time
- Sample `.bwproject` / `.npr` files from you (blocks Feat 4 entirely).
- Whether the `config.example.toml` addition forces tier=full (manifest diff
  decides; not a blocker, just affects Win delta-vs-full).

## Pointers (entry files for each feature)
- Feat 1: `cratedig/als/parser.py` (`_match_plugin` :833), `als_explorer.py`
  (`_collect_rows` :728, `_build_tab_widget` :666), `config.py`,
  `config.example.toml`, `gui/settings_tabs/paths_tab.py`, `gui/worker.py`.
- Feat 2: `cratedig/gui/simpler_pane.py` (`_WaveCanvas.paintEvent` :475,
  `_draw_waveform` :233, `_recompute_rendered` :202), `gui/logic.py`
  (`compute_peaks` :140), `main_window.py` playhead poll :358.
- Feat 3: `main_window.py` status bar :350, update flow :633-689,
  `cratedig/__init__.py`.
- Feat 4: `als/parser.py` + `als_explorer.py` as the template; `main_window.py`
  nav/pages :264-322.

# PLAN_0.6.0.md — cratedig 0.6.0 feature blueprint

Status: **DESIGN — approved scope, implementation pending.**
Release tier expectation: code + new dep (`pyaaf2`) + assets → **FULL** (Session 1 Windows).

Four features ship together in 0.6.0:

1. Delta-over-the-wire (make full/delta classification work end-to-end).
2. Fix crate sample preview/playback.
3. Unify the 9 DAW explorers into one **Project Checker** with auto-detect by extension.
4. **Convert** — DAW→DAW project conversion (Reaper / Ableton / AAF output).

---

## 1. Delta-over-the-wire

**Problem today:** build auto-picks delta (`make_manifest.decide_tier`) but the client
hardcodes `tier="full"` (`download_and_verify` default) and the Windows delta `.exe`
carries no machine-readable `from_versions`. So every code-only release forces a manual
full rebuild + delete-delta dance.

**Decision (user):** *Always publish full + delta when possible.* Every release publishes
the full installer (fresh installs + fallback); code-only releases ALSO publish the delta.
Client prefers delta when compatible, else full. No other update-logic change.

### Design

A small **signed** sidecar describes what tiers a release offers and what the delta applies
onto. Uniform across OS (Windows `.exe` can't embed a manifest; mac `.zip` already can, but
we use the sidecar for both so the client can decide BEFORE downloading).

`release-meta-<ver>.json` (uploaded as a release asset + `.minisig`):
```json
{ "version": "X.Y.Z",
  "tiers": ["full", "delta"],          // which assets exist on this release
  "delta": { "from_versions": ["X.Y.W"] } | null }
```

Client flow (`UpdateCheckThread` / new `select_tier` in updater):
1. `fetch_latest_release` (existing).
2. Download + minisign-verify `release-meta-<ver>.json`.
3. `tier = "delta"` iff meta lists delta AND `current_version ∈ delta.from_versions`
   AND a delta asset for this OS exists; else `tier = "full"`.
4. `download_and_verify(release, dest, tier=tier)` (already supports `tier`).
5. Apply (`_on_update_downloaded` branches by asset name/suffix):
   - `*.exe` → `os.startfile` + quit (Win full & delta — identical).
   - `*.dmg` → `apply_dmg_update` (mac full).
   - `*-mac.zip` → `apply_update(zip, current_version)` (mac delta).

### Build/publish changes
- `make_manifest.py`: new `emit-release-meta` subcommand writing `release-meta-<ver>.json`.
- `build_all.ps1` / `build_all.sh`: when tier=delta, build BOTH full and delta, publish
  both + `release-meta`; when tier=full, build+publish full + `release-meta` (no delta).
  Drop the manual `-Tier full` override workaround from the runbook.

### Tests
- `select_tier`: delta when compatible; full when current ∉ from_versions; full when no
  delta on release; full when meta missing/unverifiable.
- meta sign/verify round-trip; `_on_update_downloaded` branch by suffix (unit, mocked).

---

## 2. Crate preview bug

**Root cause:** `SampleTable.set_samples` repopulates rows but never resets the current
cell. Qt keeps the prior current row index; clicking that same index emits no
`currentCellChanged` → `sample_selected` never fires → no audio/waveform. Hits crates most
(small lists, user clicks row 0 which is usually already current).

**Fix:** in `set_samples`, after repopulate, reset current cell to none (signals blocked) so
the next click on ANY row — including row 0 — fires `currentCellChanged`.

**Test:** populate list A, select row 0; repopulate with list B; clicking row 0 must emit
`sample_selected` with B[0].

---

## 3. Unify DAW explorers → Project Checker

**Today:** 9 nav buttons + 9 stacked pages (Ableton + 8 DAW panels), one per format,
each its own `AlsExplorerPanel(parser=…, file_exts=…)`. `_daw_specs` already maps
`(parser, normalizer, exts, filter, bare_is_native)`.

**Target:** ONE "Project Checker" nav entry + one panel with a single "Open project…" file
picker (all-formats filter). On open, detect by extension → dispatch to the right parser →
normalize → render (existing tab UI unchanged). Removes 8 nav buttons + 8 pages.

### Design
- New `cratedig/projects_fmt/detect.py`: `REGISTRY: dict[ext, FormatSpec]` +
  `parser_for(path) -> FormatSpec | None`. `FormatSpec = {name, parser, normalizer,
  bare_is_native}`. `.als` routes to `als.parser.parse_als`; the 8 others to their
  `parse_*`. Single source of truth for extension→parser (replaces `_daw_specs`).
- `AlsExplorerPanel` gains a "detect mode": no fixed parser; picks via `parser_for` on open.
  Shows detected DAW name in the summary card.
- `main_window`: collapse nav (Samples · Project Checker · Health · …) and stacked pages;
  keep `_checker_panels` = `[project_checker_panel]` for the shared plugin-scan wiring.
- The **Convert** button (Feature 4) lives in this panel's toolbar.

### Tests
- `parser_for` returns correct spec per extension (incl. `.cpr`→nuendo parser, `.rpp-bak`,
  `.als`); unknown ext → None.
- Panel detect-open routes a fixture to the right parser (reuse existing skipif fixtures).

---

## 4. Convert — DAW→DAW project conversion

**Decision (user):** outputs = **Reaper `.RPP` + Ableton `.als` + AAF `.aaf`**; fidelity =
metadata + **copy referenced sample files** into `<project>_converted/`.

### Intermediate representation (IR)
Already 90% present. Define `cratedig/convert/ir.py`:
```
ProjectIR(
  source_format, bpm, length, key, version,
  tracks: [TrackIR(name, type, instruments:[str], plugins:[str])],
  samples_found: [abs_path], samples_missing: [basename],
)
```
Built from any parser's flat dict + `resolve_samples_on_disk` (existing). One adapter
`ir_from_parsed(parsed, project_path)`.

### Writers (`cratedig/convert/writers/`)
- `reaper.py` — emit `.RPP` text: `<REAPER_PROJECT>` + `TEMPO`, one `<TRACK NAME "…">`
  per track, sample refs as `<ITEM … <SOURCE WAVE <FILE "…">>>` at position 0, plugin
  names as comment/FX placeholder lines. Pure stdlib. Highest fidelity, easiest.
- `ableton.py` — emit gzipped `.als` XML: minimal but valid `<Ableton><LiveSet>` with
  `<Tempo>`, audio tracks, names, clip refs to copied samples, plugin names as track
  device labels. Mirror the structure `als.parser` already reads. Pure stdlib (`gzip`,
  `xml.etree`).
- `aaf.py` — write AAF via **pyaaf2** (new dep): a CompositionMob with a tempo/edit-rate,
  one timeline MobSlot per track, SourceMobs for each found sample file. Importable by
  Cubase/Pro Tools/Logic/Reaper/Premiere. Plugin/effect names recorded as user comments
  (AAF can't carry arbitrary plugin state). Degrades gracefully if pyaaf2 missing
  (`[convert]` extra; bundled in release builds).

### Sample copy
`gather_samples(ir, out_dir)` copies `samples_found` into `<project>_converted/media/`,
rewrites writer file refs to the copied relative paths. Missing samples are listed in a
`MISSING.txt` report.

### UI — Convert modal
- "Convert…" button in the Project Checker toolbar (enabled once a project is loaded).
- `ConvertDialog` (in-app modal): target-DAW dropdown (Reaper / Ableton Live / AAF
  interchange); checkboxes for what to transfer (Tempo · Tracks · Sample files · Plugin
  names · Effects). Output path picker (defaults next to source). Runs on the worker
  thread; toast on done with "Reveal in Explorer".

### Dependency / packaging
- `pyaaf2` → new `[convert]` extra in `pyproject.toml`; add to the build venv install line
  in both build scripts; verify it freezes cleanly into the onedir (PyInstaller hidden
  imports if needed). This makes 0.6.0 a **FULL** release (dep change).

### Tests
- `ir_from_parsed` shape from each parser's dict.
- Reaper writer: round-trip parse our own `.RPP` back through `parse_rpp` → tempo/tracks
  preserved. ALS writer: `parse_als` reads back our output → tempo/tracks/samples.
- AAF writer: `skipif` pyaaf2 absent; assert file opens + has the expected mob/slot count.
- `gather_samples`: copies found, reports missing, rewrites refs.

---

## Sequencing
2 (bug, smallest) → 3 (unify, enables Convert button placement) → 1 (delta) → 4 (convert,
largest). Each: tester writes failing tests → developer → tester verifies → reviewer.
Then release stage (Session 1 Windows, FULL tier) → documentation updates COMPACT.md +
writes macOS HANDOFF PENDING.

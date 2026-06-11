# PLAN — cratedig 0.5.2 (implementation blueprint)

> **Status:** PLANNING ONLY — no code written. Next implementing `/update` session:
> say «делаем 0.5.2» and execute the phases below in order.
> **Version target:** `0.5.1` → **`0.5.2`** (minor — user-visible features). Bump
> `pyproject.toml` + `cratedig/__init__.__version__` together, ONCE, in the
> implementation session (UPDATE_RULES §2). Shipped-surface IS touched → full
> release stage fires (Win installer that session, mac handoff after).
> **Session mode when implementing:** Session 1 «Change + Windows».

This release adds **six more project explorers** — Pro Tools, FL Studio, Cubase,
Reaper, Logic Pro, Studio One — each reusing the **generic checker panel** that
0.5.1 already built. Functionality matches the Ableton (ALS) explorer **as far as
each format allows**; the closed/encrypted formats (Pro Tools, Logic) are
best-effort and may slip if unparseable.

---

## 0. Infrastructure already in place (from 0.5.1) — DO NOT rebuild

0.5.1 generalised the Ableton panel into a reusable checker. Adding an explorer is
now **just a parser + a few wiring lines**. The building blocks:

- **`cratedig/gui/als_explorer.py` → `AlsExplorerPanel`** is generic. Construct with:
  `parser`, `normalizer`, `title`, `file_exts`, `file_filter`, `bare_is_native`.
  Gives the full GUI for free: header (Open / Match library / Rescan plugins),
  RU/EN toggle, drag&drop, file bar + version, MAIN CHANNEL + summary cards,
  found/missing samples, Instruments/Plugins/Tracks tabs, Library-Match tab,
  install ✓/✗/M4L badges, per-sample context menu (Reveal / New crate / Add to crate).
- **`cratedig/projects_fmt/common.py`**:
  - `read_project_bytes` — 256 MB cap (reuse for every binary parser).
  - `extract_sample_basenames` — bounded audio-filename scan over a blob.
  - `read_be_string` — length-prefixed BE string reader.
  - `resolve_samples_on_disk(basenames, project_path)` — found/missing vs the
    project's folder (recursive, bounded 20 000 files).
  - `to_checker_data(data, path)` — adapts a flat `{version, plugins, samples,
    tracks}` parser result into the rich schema the panel renders.
- **Match library** reuses `match_als_samples` (basename-keyed) via the worker — any
  explorer's `samples` flow through unchanged.
- **`bare_is_native`** badge rule: `True` when a suffix-less device name is a bundled
  native device (✓); `False` when format is unknown so no badge is drawn.

### Parser contract (every new module returns this)
```python
{ "format": "<daw>",            # short id
  "version": "<App X.Y>",       # best-effort
  "plugins": [ "<name>[ <fmt>]" , ... ],   # fmt suffix in [VST2]/[VST3]/[AU]/[AAX] when known
  "samples": [ "<basename.ext>", ... ],    # referenced audio basenames
  "tracks":  [] }               # [] → to_checker_data synthesises one "Project" track
```
For formats where we CAN recover tracks (Reaper, Studio One), return rich tracks
directly — `[{ "name", "type", "instruments": [...], "plugins": [...] }]` — and use
a thin normalizer that keeps them (see §8) instead of the synthetic track.

### Wiring checklist (per explorer, in `gui/main_window.py`)
1. Import the parser.
2. Construct `AlsExplorerPanel(parser=…, normalizer=to_checker_data, title=…,
   file_exts=…, file_filter=…, bare_is_native=…)`.
3. `self._pages.addWidget(panel)` — new stacked index.
4. Add a sidebar `QPushButton` + nav handler switching to that index.
5. `self._worker.pluginIndexReady.connect(panel.set_plugin_index)`.
6. Append the panel to the two existing 3-panel loops (matchRequested wiring +
   pluginScanRequested wiring) — make them iterate a single `self._checker_panels`
   list to avoid drift as panels multiply.
7. Update `test_als.py::test_main_window_has_stacked_pages` (page count + sidebar).

> **Refactor first (cheap):** before adding six panels, replace the hard-coded
> `(als, bitwig, nuendo)` tuples in `main_window.py` with one
> `self._checker_panels` list built once, and drive all wiring loops + stacked
> pages + sidebar from it. Keeps the six additions to ~3 lines each.

---

## 1. Format-by-format extraction plan

| DAW | Ext(s) | Container | Plugins | Samples | Tracks | `bare_is_native` | Difficulty |
|---|---|---|---|---|---|---|---|
| Reaper | `.rpp` (`.rpp-bak`) | **plain text** | `<VST "name">` lines | `FILE "path"` in `<SOURCE WAVE/…>` | full (`<TRACK`/`NAME`) | False | **Easy** |
| Studio One | `.song` | **ZIP** (+XML) | device nodes in `Song/Devices` | `mediapool` / `Audio Files/` | partial | False | Easy–Med |
| FL Studio | `.flp` | binary FLhd/FLdt events | text events (channel/mixer plugin names) | sample-path events | partial | mixed | Medium |
| Cubase | `.cpr` | RIFF tagged tree | **already parsed by `nuendo.py`** | same | — | False | **Done-ish** |
| Logic Pro | `.logicx` | macOS **bundle dir** | scan `ProjectData` printable runs (AU) | enumerate bundle `Media`/`Audio Files/` | none | False | Hard (mac) |
| Pro Tools | `.ptx` (`.ptf`) | proprietary, partly obfuscated | printable-run scan (AAX names) | printable-run audio refs | none | False | Hard |

### 1a. Reaper `.rpp` — `projects_fmt/reaper.py` (highest parity)
Plain-text S-expression. Read as text (size-capped). Extract:
- **version:** first line `<REAPER_PROJECT 0.1 "7.16/win64" …` → `Reaper 7.16`.
- **tracks:** each `<TRACK … / NAME "Drums"`; per-track `<FXCHAIN>` blocks with
  `<VST "VST3: Serum (Xfer)" …>`, `<AU …>`, `<CLAP …>`, `<JS …>` → split native (JS)
  vs 3rd-party (VST/VST3/AU/CLAP) with `[VST2]/[VST3]/[AU]` suffixes.
- **samples:** `<SOURCE WAVE>`…`FILE "kick.wav"` (also MP3/FLAC/etc).
- Return **rich tracks** → real Instruments/Plugins/Tracks tabs, true ALS parity.
- Pure stdlib regex/line parsing; bound line count.

### 1b. Studio One `.song` — `projects_fmt/studioone.py`
`.song` is a ZIP. Open with `zipfile` (reuse the zip-bomb caps already used in
`bitwig.py`: cap entry count, never decompress blindly, read only needed members).
- **version:** from `Song/Song` head or `metainfo.xml` (`appVersion`).
- **plugins:** parse the device/insert XML nodes (`pluginAudioProcessor` /
  `className`); suffix VST2/VST3 from node attrs.
- **samples:** `mediapool` entries + `Audio Files/` member names → basenames.
- Optional rich tracks if the track XML is cheap to walk.

### 1c. FL Studio `.flp` — `projects_fmt/flstudio.py`
Binary `FLhd` (header: version, channel count) + `FLdt` event stream. Events are
`<id:byte><data>`; ids ≥ 192 are length-prefixed (text/data). Decode the relevant
text events:
- **version:** FLhd `Version` event (`FLVersion`/`ProjectTime`), e.g. `FL Studio 21`.
- **plugins:** `PluginName` / generator+effect `Plugin` events; native FL plugins
  (Sytrus, GMS…) → bundled ✓; wrapped 3rd-party → VST2/VST3 suffix from the wrapper
  flags. (Port the minimal event walk; do **not** add PyFLP as a runtime dep —
  keep stdlib-only, mirror our other parsers.)
- **samples:** `SampleFileName`/`ChannelSamplePath` events → basenames.

### 1d. Cubase `.cpr` — already covered
`nuendo.py` already parses `.cpr` (same RIFF tree; the 0.5.1 Nuendo panel's
`file_exts` already include `.cpr`). For 0.5.2 either: **(a)** leave Cubase merged
into the "Nuendo / Cubase" page (lowest effort, already shipping), or **(b)** add a
dedicated "Cubase" sidebar page pointing at the same `parse_npr` with a Cubase
title. Recommend **(a)** unless users want a separate entry. No new parser needed.

### 1e. Logic Pro `.logicx` — `projects_fmt/logic.py` (macOS-centric)
`.logicx` is a **package directory**, not a file. The file dialog must allow
selecting the bundle (`QFileDialog` directory or `*.logicx`). Inside:
`Alternatives/000/ProjectData` (binary) + a `Media`/`Audio Files/` folder.
- **samples:** enumerate the bundle's media folder directly (real files) — trivial,
  high accuracy; `resolve_samples_on_disk` points at the bundle.
- **plugins:** scan `ProjectData` printable runs for AU plugin names (best-effort;
  no reliable format/version). `bare_is_native=False`.
- **version:** from `ProjectData`/`DisplayState` if a marker is found, else "Logic".
- Caveat: opaque binary; treat as best-effort, like Pro Tools.

### 1f. Pro Tools `.ptx` — `projects_fmt/protools.py` (lowest yield)
`.ptx` is proprietary and **partly obfuscated/encrypted** in modern versions, so
full parsing is out of scope. Best-effort only:
- **plugins:** printable-run scan for AAX plugin names (`extract`-style, denylist
  routing names). `bare_is_native=False`; add `[AAX]` when a marker is adjacent.
- **samples:** `extract_sample_basenames` over the blob (Audio Files refs).
- **version:** header marker if present, else "Pro Tools".
- Legacy `.ptf` (pre-PT10) is more open — support if cheap. Clearly label results
  as best-effort. **This format may be cut from 0.5.2 if the scan yields noise.**

---

## 2. Security (mandatory, mirrors bitwig/nuendo)
- Every binary parser goes through `read_project_bytes` (256 MB cap).
- ZIP formats (Studio One, and the ZIP tail pattern): cap central-directory entry
  count, never decompress untrusted members blindly, read only what's needed
  (reuse `bitwig.py::_preset_count` discipline).
- All regexes length-bounded (no catastrophic backtracking) — copy the
  `{1,160}` token-bounding style from `common.py::_AUDIO_RE`.
- Bundle/dir formats (Logic): bound the directory walk (depth + file count) exactly
  like `resolve_samples_on_disk`.

## 3. Testing (TDD, ≥80% per `rules/testing.md`)
- One `tests/test_projects_fmt_<daw>.py` per parser with a tiny synthetic fixture
  (hand-built `.rpp` text; minimal ZIP for `.song`; crafted FLhd/FLdt bytes;
  fixture media folder for Logic). Assert version/plugins/samples extraction +
  malformed-input raises cleanly.
- Extend `test_project_checker.py` for any new normalizer behaviour (rich-tracks
  passthrough, §8).
- Update `test_als.py::test_main_window_has_stacked_pages` for the new page count
  and sidebar buttons.

## 4. Suggested order (ship value early, defer the hard ones)
1. **Refactor** `main_window` panels → single `self._checker_panels` list.
2. **Reaper** (easy, full parity) — proves rich-tracks path.
3. **Studio One** (ZIP+XML).
4. **FL Studio** (binary events).
5. **Cubase** — decide merge vs dedicated page (likely zero-code).
6. **Logic Pro** (mac, best-effort).
7. **Pro Tools** (best-effort; cut if noisy).

## 5. Rich-tracks normalizer (for Reaper/Studio One)
`to_checker_data` synthesises a single "Project" track from flat `plugins`. For
parsers that already emit real tracks, add a sibling that preserves them:
```python
def to_checker_data_rich(data, path):
    out = to_checker_data(data, path)         # main/arrangement/samples defaults
    if data.get("tracks"):
        out["tracks"] = data["tracks"]        # already in rich shape
    return out
```
Pick the normalizer per panel. Keep both in `projects_fmt/common.py`.

## 6. Out of scope for 0.5.2
- Decrypting Pro Tools / Logic binary internals (reverse-engineering effort).
- Per-track fader/arrangement for binary formats (no reliable data).
- Delta-over-the-wire client (tracked separately in COMPACT Backlog / 0.6.0+).

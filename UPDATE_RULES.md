# UPDATE_RULES.md — cratedig release/update pipeline

**Authoritative, binding project rule.** Extends the agent pipeline in
`rules/agents.md` with a mandatory **release (update) stage**. Loaded by the
`/update` session-start command. If anything here conflicts with a casual
instruction, this file wins for release matters.

---

## 0. Why this file exists

Every shipped change must end as an **installable update for BOTH Windows and
macOS**. Updates are **TWO-TIER** (see §7 for full design):

| tier | OS | file | when |
|---|---|---|---|
| **Full** | Windows | `packaging/windows/Output/cratedig-setup-<ver>.exe` (Inno) | first install; deps/Python/ffmpeg/assets changed |
| **Full** | macOS | `dist/cratedig-<ver>.dmg` | first install; deps/Python/ffmpeg/assets changed |
| **Delta** | Windows | `packaging/windows/Output/cratedig-update-<ver>.exe` (small Inno installer) | code-only release (runtime identical) |
| **Delta** | macOS | `dist/cratedig-update-<ver>-mac.zip` (in-app apply) | code-only release (runtime identical) |

**Delta delivery differs per OS (by design — path of least resistance):**
- **Windows delta = a small Inno "update" installer** the user double-clicks. Same
  `AppId` as the full installer → it finds the install dir, overwrites only the
  changed files, and (being an external process) closes the app, swaps locked
  `.exe`/`.dll`, and relaunches. Reuses the existing Inno toolchain; no in-app code.
- **macOS delta = a `.zip` applied in-app** via **Help → "Apply update from file…"**
  (`cratedig/updater.py`, planned). Chosen over `.pkg` to stay fully offline with
  no Apple Dev ID / notarization.

**OFFLINE / LOCAL-FILE ONLY — HARD CONSTRAINT.** The app/installer NEVER contacts a
server, NEVER checks a repo/appcast, NEVER auto-downloads. No network in the update
path. The user receives the update file by hand (USB / share / manual download) and
either runs it (Windows `.exe`) or applies it in-app (macOS `.zip`). Any design that
phones home (tufup, Sparkle appcast, electron-updater feeds) is **forbidden** here.

User data in `%APPDATA%\cratedig` / `~/Library/Application Support/cratedig` is
never touched by install/update, so reinstalling or patching is always safe.

**Per-user install (REQUIRED for UAC-free patching):** the app installs to
`%LOCALAPPDATA%\Programs\cratedig` (Windows, `PrivilegesRequired=lowest`) and
`~/Applications` (macOS), so the offline updater overwrites files in place
without elevation. (Implementation of this `cratedig.iss` switch is a future
shipped-surface release — see §7.)

**Full installers CANNOT be built in one session** — Inno needs Windows, `.dmg`
needs macOS. So a release cycle spans **two ordered sessions** (§3). Delta files
are produced in the same session as their OS's build.

---

## 1. When the update pipeline fires (trigger scope — STRICT)

The release stage is **mandatory** when a session changes the **shipped surface**
(anything that alters what ends up inside the installed app):

- `cratedig/**` (app source)
- installer definitions that change output contents: `packaging/cratedig.spec`,
  `packaging/windows/cratedig.iss`
- runtime dependencies in `pyproject.toml` (`[project].dependencies` or extras)
- bundled assets (icons, schema, `config.example.toml`, staged ffmpeg/ffplay)

The release stage is **skipped** (no version bump, no build) when a session
touches ONLY the **meta/tooling surface** (does not change installed contents):

- `*.md` anywhere (README, ARCHITECTURE, PACKAGING, COMPACT, this file)
- `rules/**`, `.claude/**`, `docs/**`
- build-driver scripts: `packaging/**/build_all.*`, `packaging/macos/make_dmg.sh`,
  `packaging/render_icons.py`

This is the only exemption. A change that touches both surfaces is a
shipped-surface change → release stage fires. No other loopholes.

---

## 2. Version = single source of truth

- **SSOT = `pyproject.toml` → `[project].version`.** Nothing else stores a
  version literal that must be hand-synced; the build tools READ it:
  - Windows: `iscc /DVersion=<version> packaging\windows\cratedig.iss`
  - macOS:   `bash packaging/macos/build_all.sh <version>`
  - (`cratedig.iss` and `build_all.sh` keep `0.1.0` only as a fallback default —
    always pass `<version>` explicitly so the SSOT governs.)
- **Bump rule (per release cycle, once, in Session 1):**
  - patch (`0.1.0 → 0.1.1`) — fixes, internal changes (default)
  - minor (`0.1.0 → 0.2.0`) — user-visible feature
  - major (`0.1.0 → 1.0.0`) — breaking change to data/config layout
- Windows installer and macOS `.dmg` of the SAME release MUST carry the SAME
  version string. The macOS build session reads the version from `pyproject.toml`
  (or the handoff block §4), never invents its own.

---

## 3. The two-session release cycle (ORDER IS BINDING)

> Run order is fixed: **Windows session FIRST, macOS session SECOND.** The Win
> session bumps the version and writes the macOS handoff into COMPACT.md; the
> macOS session only consumes it. Never build the `.dmg` before the Windows
> installer exists for that version.

### Session 1 — "Change + Windows" (on the Windows dev machine)

1. Implement the actual change via the standard pipeline
   (`planner → explorer ∥ analyst → architect? → tester → developer → tester →
   reviewer → documentation`).
2. **Bump** `pyproject.toml` version per §2.
3. **Build the onedir + pick the tier** (§7): run
   `pwsh packaging/windows/build_all.ps1 <version>`, then diff the new
   `dist/cratedig` against the previous release manifest:
   - runtime/deps/assets unchanged → emit **delta** = small Inno update installer
     `cratedig-update-<version>.exe` (built from `packaging/windows/cratedig-update.iss`
     over just the changed files; same `AppId`).
   - deps/Python/ffmpeg/assets changed, or no previous manifest → emit **full**
     `cratedig-setup-<version>.exe` (Inno).
   Commit the new `packaging/release-manifests/cratedig-<version>-win.json`.
4. **Smoke-launch** the frozen `dist/cratedig/cratedig.exe` — window opens, no crash.
   (For a delta, also smoke-test running `cratedig-update-<version>.exe` onto the
   previous install.)
5. **`documentation` agent updates COMPACT.md** (last step) — including the
   **macOS HANDOFF block** (§4) marking the macOS side as PENDING **and the tier**.
6. Stop. Do NOT build any macOS artifact here. User commits when ready.

**Definition of Done (Session 1):** version bumped · Windows update file (full OR
delta) exists, launches/applies · release manifest committed · COMPACT.md has a
PENDING macOS HANDOFF block (with tier) for `<version>`.

### Session 2 — "macOS build" (on a Mac)

`/update` detects the PENDING handoff block in COMPACT.md and enters macOS-build mode.

1. `git pull` the source changes (source only — never copy `dist/build/.venv`).
2. **Build the onedir** (one shot): `bash packaging/macos/build_all.sh <version>`,
   then pick the tier (§7) the same way Session 1 did, using the macOS release
   manifest baseline:
   - runtime/deps/assets unchanged → emit **delta** `cratedig-update-<version>-mac.zip`.
   - else → emit **full** `dist/cratedig-<version>.dmg`.
   Use the tier recorded in the handoff block as the expectation; if the macOS
   diff disagrees (e.g. an arch-specific binary changed), the macOS diff wins.
   Commit `packaging/release-manifests/cratedig-<version>-mac.json`.
3. **Smoke-launch** `dist/cratedig.app` — seeds user data, process stays alive.
   (For a delta, also smoke-test applying the `.zip` onto the previous `.app`.)
4. **`documentation` agent updates COMPACT.md** — mark the macOS update file DONE
   for `<version>` and **clear the PENDING handoff** (both OSes now shipped).

**Definition of Done (Session 2):** macOS update file (full OR delta) exists and
launches/applies · manifest committed · COMPACT.md shows both OSes DONE for
`<version>` · no PENDING handoff remains.

---

## 4. macOS HANDOFF block (written into COMPACT.md by Session 1)

Single fenced block under a `## macOS HANDOFF — PENDING` heading. Session 2 reads
it; the `documentation` agent removes/zeroes it when the `.dmg` is done.

```
## macOS HANDOFF — PENDING
- version: <X.Y.Z>
- tier: <full | delta>   # expected macOS tier (macOS diff is authoritative, §3)
- windows update: DONE (cratedig-setup-<X.Y.Z>.exe | cratedig-update-<X.Y.Z>-win.zip)
- macos update: PENDING
- source ref: <git commit hash / branch to pull>
- changed files: <list, or "see git diff <hash>">
- new deps/assets: <none | what build_all.sh must fetch beyond ffmpeg/ffplay>
- build command: bash packaging/macos/build_all.sh <X.Y.Z>
- notes: <e.g. delta because only cratedig/** changed; deps untouched>
```

When no release is mid-flight, this section reads `## macOS HANDOFF — none`.

---

## 5. Hard rules (do not violate)

- **OFFLINE ONLY**: the update path must never open a network connection — no
  appcast, no repo fetch, no auto-download. Updates apply from a user-supplied
  local file only (§0, §7).
- macOS session never bumps the version — it consumes Session 1's version.
- Never ship a macOS update whose version has no matching Windows update.
- A **delta** may only be applied onto a version listed in its manifest
  `from_versions`; otherwise the app demands a full installer (§7).
- The `documentation` agent is the ONLY writer of COMPACT.md, including the
  handoff block (CLAUDE.md §5).
- No agent commits or pushes — the user approves all commits.
- Meta-only sessions (§1) MUST NOT bump the version or produce update files.

## 6. Pointers

- `PACKAGING.md` — how each installer is built (toolchain, ffmpeg, §6 mac rebuild).
- `packaging/windows/build_all.ps1` — Windows one-shot build.
- `packaging/macos/build_all.sh` — macOS one-shot build.
- `packaging/release-manifests/` — per-release file-hash manifests (diff baseline, §7).
- `packaging/windows/cratedig-update.iss` *(planned)* — Windows delta = small Inno update installer (§7.3a).
- `cratedig/updater.py` *(planned)* — macOS offline apply-from-file updater + restart helper (§7.3b/7.4).
- `.claude/commands/update.md` — the `/update` session-start command that runs this.

## 7. Two-tier offline update design (full vs delta)

**Goal:** stop re-shipping the ~570 MB onedir for a 1.6 MB code fix. The runtime
(Python, librosa/numba/llvmlite, PySide6, ffmpeg) is byte-identical between
releases unless deps change; only `cratedig/**` moves. So most releases ship a
small **delta**; only dep/runtime changes ship a **full** installer.

### 7.1 Release manifest (diff baseline)
Every release writes `packaging/release-manifests/cratedig-<ver>-<os>.json`:
```
{ "version": "X.Y.Z", "os": "win|mac",
  "files": { "<relpath-from-install-root>": {"sha256": "...", "size": N}, ... } }
```
These are small text files, committed to the repo. Session N diffs the new build
against release N-1's manifest to compute the changed/added/deleted set.

### 7.2 Tier decision (automatic)
- No previous manifest, OR any changed file is a runtime/dep/asset (anything
  outside the app-code set, or `pyproject.toml` deps changed) → **full installer**.
- Else (only app code / data changed) → **delta**.
- Escape hatch: if the delta payload exceeds ~40 MB, fall back to full.

The changed/added/deleted file set (from 7.1) is the same on both OSes; only the
**delivery wrapper** differs.

**Note (file-lock):** a running process can't overwrite its own loaded
`.exe`/`.dll`/`.dylib`. The Windows update installer is an external process, so it
closes the app, swaps, and relaunches for free. The macOS in-app updater must spawn
a small **restart helper** that waits for the app to exit, swaps files, relaunches.

### 7.3a Windows delta = Inno update installer
`cratedig-update-<ver>.exe`, built from a dedicated
`packaging/windows/cratedig-update.iss` (planned):
- same `AppId` as `cratedig.iss` → installs into the existing per-user dir;
- `[Files]` lists ONLY the changed/added files (from the 7.1 diff);
- `[InstallDelete]` removes the deleted files;
- closes the running app, overwrites locked files, relaunches.
No in-app code, no network — the user just double-clicks the `.exe`.

### 7.3b macOS delta = zip + in-app apply
`cratedig-update-<ver>-mac.zip` contains the changed/added files at their
bundle-relative paths plus `update-manifest.json`:
```
{ "to_version": "X.Y.Z",
  "from_versions": ["X.Y.W", ...],   // versions this delta may apply onto
  "files":    [ {"path": "...", "sha256": "...", "size": N}, ... ],
  "deletions": [ "<relpath>", ... ],
  "manifest_sha256": "<hash of the above, excluding this field>" }
```
No bsdiff: whole changed files are shipped (keeps the updater dependency-free) —
still ≪ 470 MB and fully offline. Applied by `cratedig/updater.py` (7.4).

### 7.4 macOS in-app updater (`cratedig/updater.py`, planned)
**Help → "Apply update from file…"** → user picks a local `cratedig-update-*-mac.zip`.
1. Read `update-manifest.json`; verify `manifest_sha256`; require
   `to_version` > current and current ∈ `from_versions` (else: "needs full `.dmg`").
2. Verify every payload file's sha256 matches the manifest.
3. Stage to a temp dir, then hand off to a **restart helper** that: waits for the
   app to quit, copies files (overwrite) into the `.app`, removes `deletions`,
   writes the new version marker, relaunches.
No network at any step. Full installers (`.exe`/`.dmg`) are applied the normal way
(run installer / drag `.app`) for first install and dep-change releases.

### 7.5 Per-user install (prerequisite, future shipped-surface change)
Self-applying a delta in place must not need admin. Switch `cratedig.iss` to
`PrivilegesRequired=lowest` + `DefaultDirName={localappdata}\Programs\cratedig`
(the update `.iss` inherits this via the shared `AppId`); ship the macOS `.app` for
`~/Applications`. Until this lands, delta apply on a Program-Files / `/Applications`
install would require elevation — so this `.iss` change is the first item to
implement when the updater is built.

### 7.5.1 One-time migration to per-user (NO delta can do this)
Going per-user changes the install **location and scope**, not just files, so it
**cannot** be delivered by a delta. The first per-user release is therefore a
**FULL tier** by definition (§7.2 — install-layout change) and requires a one-time
reinstall/relocate:
- **Windows:** uninstall the old Program-Files version (or have the new full
  installer's `[Code]` detect + offer to remove the old per-machine install), then
  run the new per-user `cratedig-setup-<ver>.exe`. After this, all future
  `cratedig-update-*.exe` deltas apply in place, no UAC.
- **macOS:** drag the new `.app` into `~/Applications` (optionally delete the
  `/Applications` copy). After this, delta `.zip`s apply in place, no admin.
- **Data is safe:** user data in `%APPDATA%\cratedig` / `~/Library/Application
  Support/cratedig` is untouched by install/uninstall — only the app relocates.

Document this one-time step for the user in `README.md` when the per-user release
ships (migration section: uninstall-old / drag-to-~/Applications, data preserved).

> Implementation status: design only. Building `packaging/windows/cratedig-update.iss`,
> `cratedig/updater.py` + its restart helper, the delta/manifest step in `build_all.*`,
> and the `.iss` per-user switch is a **shipped-surface release** (a real Session 1),
> not part of this plan-only session.

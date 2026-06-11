# UPDATE_RULES.md — cratedig release/update pipeline

**Authoritative, binding project rule.** Extends the agent pipeline in
`rules/agents.md` with a mandatory **release (update) stage**. Loaded by the
`/update` session-start command. If anything here conflicts with a casual
instruction, this file wins for release matters.

---

## 0. Update model (ONLINE via GitHub Releases — since 0.4.0)

Every shipped change must end as an **installable update for BOTH Windows and
macOS**. Updates are **TWO-TIER** (see §7 for full design):

| tier | OS | file | when |
|---|---|---|---|
| **Full** | Windows | `packaging/windows/Output/cratedig-setup-<ver>.exe` (Inno) | first install; deps/Python/ffmpeg/assets changed |
| **Full** | macOS | `dist/cratedig-<ver>.dmg` | first install; deps/Python/ffmpeg/assets changed |
| **Delta** | Windows | `packaging/windows/Output/cratedig-update-<ver>.exe` (small Inno installer) | code-only release (runtime identical) |
| **Delta** | macOS | `dist/cratedig-update-<ver>-mac.zip` (in-app apply) | code-only release (runtime identical) |

**Both Windows and macOS share the same in-app update flow:** launch → update
dialog → accept → auto download + verify + apply + relaunch. There is no manual
browser step for either OS.

- **Windows full/delta:** `UpdateDownloadThread` downloads + minisign-verifies
  the `.exe`, then `os.startfile(installer_path)` launches it and
  `QApplication.quit()` exits. The Inno installer (external process) closes the
  app, swaps locked files, and relaunches.
- **macOS full:** `UpdateDownloadThread` downloads + minisign-verifies the
  `.dmg`, then `updater.apply_dmg_update(path)` mounts the image
  (`hdiutil attach -nobrowse`), finds `cratedig.app` inside, and spawns a
  dependency-free bash restart helper that: waits for the running app to exit
  (`kill -0`), `ditto`s the new `.app` to `<app>.new`, swaps via two same-volume
  `mv` (effectively atomic), clears quarantine (`xattr -dr`), detaches the image
  (`hdiutil detach`), and relaunches via `open`. Then `QApplication.quit()`.
- **macOS delta:** applied in-app via **Help → "Apply update from file…"**
  (`apply_update` in `cratedig/updater.py`). This offline manual path remains as
  a fallback for local `.zip` files.

**ONLINE — GitHub Releases feed.** Since 0.4.0, the app checks for updates
automatically on startup (frozen builds only) by fetching
`https://api.github.com/repos/zloishaman1337/cratedig/releases/latest`
anonymously (no token required, public repo). The client downloads ONLY the
named OS-specific release asset and its `.minisig` companion — it never clones
the repository or pulls the auto-generated "Source code" archives (`zipball_url`
/ `tarball_url`). Every downloaded asset is verified with minisign before it is
launched or applied. The check is silent on failure or when the install is
already up to date; a dialog appears only when a newer version is found.

**HARDCODED repo slug:** `GITHUB_REPO = "zloishaman1337/cratedig"` in
`cratedig/updater.py`. The local git `origin` has historically been stale, so
this constant must never be auto-detected from the git remote.

**Baseline trap — 0.4.0 distribution:** 0.4.0 is the FIRST online-capable
build. Installs at 0.2.x/0.3.x contain no update-checker and CANNOT pull 0.4.0
automatically. 0.4.0 full installers are therefore distributed manually one last
time (attached to the GitHub release). Automatic over-the-wire updates work from
0.5.0 onward, because every ≥0.4.0 install carries the online checker.

**For 0.4.0 specifically**, the online auto-update path always downloads the
FULL installer (delta-over-the-wire is a future refinement; `select_asset`
already accepts a `tier` argument for when it lands).

User data in `%APPDATA%\cratedig` / `~/Library/Application Support/cratedig` is
never touched by install/update, so reinstalling or patching is always safe.

**Per-user install (required for UAC-free patching):** the app installs to
`%LOCALAPPDATA%\Programs\cratedig` (Windows, `PrivilegesRequired=lowest`) and
`~/Applications` (macOS) so the updater can overwrite files in place without
elevation.

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
- bundled assets (icons, schema, `config.example.toml`, staged ffmpeg/ffplay,
  staged minisign binary)

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

- **SSOT = `pyproject.toml` → `[project].version`.** `cratedig/__init__.__version__`
  MUST be bumped in the same commit (the runtime reads `__version__`; the
  build spec reads it for `info_plist`; the updater compares it against the
  GitHub release tag). They had drifted before 0.2.0 — always bump both together.
- The build tools read `pyproject.toml`:
  - Windows: `pwsh packaging/windows/build_all.ps1 <version>`
  - macOS:   `bash packaging/macos/build_all.sh <version>`
  - (`cratedig.iss` and `build_all.sh` keep `0.1.0` only as a fallback default —
    always pass `<version>` explicitly so the SSOT governs.)
- **Bump rule (per release cycle, once, in Session 1):**
  - patch (`0.4.0 → 0.4.1`) — fixes, internal changes (default)
  - minor (`0.4.0 → 0.5.0`) — user-visible feature
  - major (`0.4.0 → 1.0.0`) — breaking change to data/config layout
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
2. **Bump** `pyproject.toml` version AND `cratedig/__init__.__version__` per §2.
3. **Build the onedir + pick the tier** (§7): run
   `pwsh packaging/windows/build_all.ps1 <version>`, then diff the new
   `dist/cratedig` against the previous release manifest:
   - runtime/deps/assets unchanged → emit **delta** = small Inno update installer
     `cratedig-update-<version>.exe` (built from `packaging/windows/cratedig-update.iss`
     over just the changed files; same `AppId`).
   - deps/Python/ffmpeg/assets changed, or no previous manifest → emit **full**
     `cratedig-setup-<version>.exe` (Inno).
   Commit the new `packaging/release-manifests/cratedig-<version>-win.json`.
4. **Sign + publish** (on release): `pwsh packaging/windows/build_all.ps1 <version> -Sign -Publish`.
   Requires `$env:MINISIGN_PASSWORD` set and `minisign.key` present at repo root.
   The `-Publish` switch creates the GitHub release (via `gh release create`) and
   uploads the installer + `.minisig` (via `gh release upload`).
5. **Smoke-launch** the frozen `dist/cratedig/cratedig.exe` — window opens, no crash.
   (For a delta, also smoke-test running `cratedig-update-<version>.exe` onto the
   previous install.)
6. **`documentation` agent updates COMPACT.md** (last step) — including the
   **macOS HANDOFF block** (§4) marking the macOS side as PENDING **and the tier**.
7. Stop. Do NOT build any macOS artifact here. User commits when ready.

**Definition of Done (Session 1):** version bumped (pyproject + `__init__`) ·
Windows update file (full OR delta) + `.minisig` published to GitHub release ·
release manifest committed · COMPACT.md has a PENDING macOS HANDOFF block (with
tier) for `<version>`.

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
3. **Sign + publish** (on release): `SIGN=1 PUBLISH=1 MINISIGN_PASSWORD=<pw> bash packaging/macos/build_all.sh <version>`.
   Same effect as Windows: signs the `.dmg`/`.zip` + companion `.minisig` and
   uploads both to the existing GitHub release via `gh release upload`.
4. **Smoke-launch** `dist/cratedig.app` — seeds user data, process stays alive.
   (For a delta, also smoke-test applying the `.zip` via Help → "Apply update
   from file…" onto the previous `.app`.)
5. **`documentation` agent updates COMPACT.md** — mark the macOS update file DONE
   for `<version>` and **clear the PENDING handoff** (both OSes now shipped).

**Definition of Done (Session 2):** macOS update file (full OR delta) + `.minisig`
published to GitHub release · manifest committed · COMPACT.md shows both OSes
DONE for `<version>` · no PENDING handoff remains.

---

## 4. macOS HANDOFF block (written into COMPACT.md by Session 1)

Single fenced block under a `## macOS HANDOFF — PENDING` heading. Session 2 reads
it; the `documentation` agent removes/zeroes it when the `.dmg` is done.

```
## macOS HANDOFF — PENDING
- version: <X.Y.Z>
- tier: <full | delta>   # expected macOS tier (macOS diff is authoritative, §3)
- windows update: DONE (cratedig-setup-<X.Y.Z>.exe | cratedig-update-<X.Y.Z>.exe)
- macos update: PENDING
- source ref: <git commit hash / branch to pull>
- changed files: <list, or "see git diff <hash>">
- new deps/assets: <none | what build_all.sh must fetch beyond ffmpeg/ffplay/minisign>
- build command: bash packaging/macos/build_all.sh <X.Y.Z>
- notes: <e.g. delta because only cratedig/** changed; deps untouched>
```

When no release is mid-flight, this section reads `## macOS HANDOFF — none`.

---

## 5. Hard rules (do not violate)

- **ONLINE via GitHub Releases:** the auto-check path fetches
  `LATEST_RELEASE_API` (one anonymous HTTPS GET). Downloads are ONLY named
  release assets — never repo source archives. Every downloaded asset is
  minisign-verified before launch or apply. The macOS **Help → "Apply update
  from file…"** offline path remains as a manual fallback for local `.zip`
  files.
- **Trust = minisign signatures.** Private key (`minisign.key`) stays out of
  the repository (`*.key` in `.gitignore`); never commit it. The public key
  (`MINISIGN_PUBKEY`, key id `54F217219B866BE6`) is embedded as a constant in
  `cratedig/updater.py` and ships inside the app. Every release asset uploaded
  to GitHub MUST have a companion `<asset>.minisig` in the same release.
  Verification is mandatory — `download_and_verify()` always calls
  `verify_signature()` before returning the installer path.
- **Key password** is read from `$env:MINISIGN_PASSWORD` (Windows) /
  `$MINISIGN_PASSWORD` (macOS); piped to `minisign` stdin. Never hardcode it.
  Both `build_all.ps1` and `build_all.sh` auto-load it from a **gitignored `.env`**
  (`MINISIGN_PASSWORD=…` line) at the repo root when the env var is unset, so the
  signer is never prompted. The agent reads `.env` for the password and must not
  ask the user for it. `.env` is in `.gitignore` — never commit it.
- macOS session never bumps the version — it consumes Session 1's version.
- Never ship a macOS update whose version has no matching Windows update
  published on the same GitHub release.
- A **delta** may only be applied onto a version listed in its manifest
  `from_versions`; otherwise the app demands a full installer (§7).
- The `documentation` agent is the ONLY writer of COMPACT.md, including the
  handoff block (CLAUDE.md §5).
- **Commits/pushes are authorized** — the agent MAY `git commit` and `git push`
  release/session changes automatically, without asking. They MUST be made under
  the user's git identity (the repo's configured `user.name`/`user.email` =
  `zloishaman1337`), NEVER under the agent's name: do **not** add a
  `Co-Authored-By: Claude` trailer or any other agent attribution to the commit.
  Never use `--no-verify`/`--no-gpg-sign` or force-push without explicit consent.
- Meta-only sessions (§1) MUST NOT bump the version or produce update files.

---

## 6. Pointers

- `PACKAGING.md` — how each installer is built (toolchain, ffmpeg, §6 mac rebuild).
- `packaging/windows/build_all.ps1` — Windows one-shot build; `-Sign` signs with
  minisign; `-Publish` creates/uploads the GitHub release (implies `-Sign`).
- `packaging/macos/build_all.sh` — macOS one-shot build; `SIGN=1` signs;
  `PUBLISH=1` creates/uploads the GitHub release (implies `SIGN=1`).
- `packaging/release-manifests/` — per-release file-hash manifests (diff baseline, §7).
- `packaging/windows/cratedig-update.iss` — Windows delta = small Inno update
  installer (same `AppId`; `#include update-files.iss`; see §7.3a).
- `cratedig/updater.py` — online feed constants (`GITHUB_REPO`,
  `LATEST_RELEASE_API`, `MINISIGN_PUBKEY`, `_ASSET_NAMES`); pure parsing layer
  (`fetch_latest_release`, `parse_release`, `tag_to_version`, `current_os`,
  `select_asset`, `find_signature`); I/O layer (`download_asset`,
  `minisign_path`, `verify_signature`, `download_and_verify`); macOS apply layer
  (`apply_update` for delta `.zip`; `apply_dmg_update` + `_write_dmg_restart_helper`
  for full `.dmg` auto-apply; see §7.3b/7.4).
- `cratedig/gui/update_check.py` — `UpdateCheckThread` (silent startup check;
  emits `found` only when a newer version exists) + `UpdateDownloadThread`
  (download + verify; emits `done` with verified installer path).
- `cratedig/gui/main_window.py` — `_maybe_check_updates()` kicks the check on
  startup (frozen only); `_on_update_available()` shows the update dialog and
  offers download+install on BOTH Windows and macOS; `_on_update_downloaded()`
  branches: Windows → `os.startfile(installer)` + quit; macOS →
  `updater.apply_dmg_update(path)` + quit.
- `packaging/make_manifest.py` — build-time manifest gen / diff / tier decision /
  delta-zip (mac) / win-include (`update-files.iss`); imports `cratedig.updater`
  for shared schema + hash.
- `.claude/commands/update.md` — the `/update` session-start command that runs this.

---

## 7. Two-tier update design (full vs delta)

**Goal:** stop re-shipping the ~570 MB onedir for a 1.6 MB code fix. The runtime
(Python, librosa/numba/llvmlite, PySide6, ffmpeg, minisign) is byte-identical
between releases unless deps change; only `cratedig/**` moves. So most releases
ship a small **delta**; only dep/runtime changes ship a **full** installer.

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
closes the app, swaps, and relaunches for free. The macOS in-app updater spawns a
small dependency-free **bash restart helper** that waits for the app to exit, uses
`ditto` to copy the staged files, removes deletions, and relaunches via `open`.

### 7.3a Windows delta = Inno update installer
`cratedig-update-<ver>.exe`, built from
`packaging/windows/cratedig-update.iss`:
- same `AppId` as `cratedig.iss` → installs into the existing per-user dir;
- `[Files]` lists ONLY the changed/added files (from the 7.1 diff);
- `[InstallDelete]` removes the deleted files;
- closes the running app, overwrites locked files, relaunches.
In-app: `UpdateDownloadThread` downloads + verifies the `.exe`, then
`os.startfile(installer_path)` launches it and `QApplication.quit()` exits.

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
No bsdiff: whole changed files are shipped (keeps the updater dependency-free).
Applied by `cratedig/updater.py` via **Help → "Apply update from file…"** (7.4).
Each `.zip` uploaded to GitHub has a companion `.zip.minisig` in the same release.

### 7.4 macOS in-app updater (`cratedig/updater.py`)

**Full `.dmg` auto-apply (online update flow):**
`_on_update_downloaded` calls `updater.apply_dmg_update(dmg_path)`. The function
(macOS-only; raises on non-Darwin):
1. Mounts the already-minisign-verified `.dmg` via `hdiutil attach -nobrowse
   -mountpoint <tmp>`.
2. Locates `cratedig.app` inside the mounted volume.
3. Writes a dependency-free bash restart helper (`_write_dmg_restart_helper`)
   that: polls `kill -0 $PARENT_PID` until the app exits, `ditto`s the new
   `.app` to `<current_app>.new`, atomically swaps via two same-volume `mv`,
   clears quarantine (`xattr -dr com.apple.quarantine`), detaches the image
   (`hdiutil detach`), and relaunches via `open`.
4. Spawns the helper detached and returns. The caller then calls
   `QApplication.quit()`.

Signature verification is the caller's responsibility and is always done by
`download_and_verify` before `apply_dmg_update` is called.

**Delta `.zip` manual fallback — Help → "Apply update from file…":**
User picks a local `cratedig-update-*-mac.zip`.
1. Read `update-manifest.json`; verify `manifest_sha256`; require
   `to_version` > current and current ∈ `from_versions` (else: "needs full `.dmg`").
2. Verify every payload file's sha256 matches the manifest.
3. Stage to a temp dir, then hand off to the same **bash restart helper** pattern:
   waits for app to quit, copies files via `ditto`, removes `deletions`, clears
   quarantine, relaunches with `open`.
On return the caller quits via `QApplication.quit()`. Full installers
(`.exe`/`.dmg`) for first install and dep-change releases follow the normal flow
above.

### 7.5 Per-user install (required for delta apply without elevation)
The app installs to `%LOCALAPPDATA%\Programs\cratedig`
(`PrivilegesRequired=lowest` in `cratedig.iss`) on Windows and ships the macOS
`.app` for `~/Applications`, so the updater can overwrite files in place without
admin. This is already implemented; delta apply works without UAC.

### 7.5.1 One-time migration to per-user (NO delta can do this)
Going per-user changes the install **location and scope**, not just files, so it
**cannot** be delivered by a delta. The first per-user release is therefore a
**FULL tier** by definition (§7.2 — install-layout change):
- **Windows:** uninstall the old Program-Files version, then run the new
  per-user `cratedig-setup-<ver>.exe`. After this, all future
  `cratedig-update-*.exe` deltas apply in place, no UAC.
- **macOS:** drag the new `.app` into `~/Applications` (optionally delete the
  `/Applications` copy). After this, delta `.zip`s apply in place, no admin.
- **Data is safe:** user data in `%APPDATA%\cratedig` / `~/Library/Application
  Support/cratedig` is untouched by install/uninstall — only the app relocates.

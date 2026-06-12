# cratedig

**cratedig** is a desktop app for digging through your sample library — like
*Sononym*, but local and entirely yours. Point it at your folders and it indexes
every sample, then lets you:

- 🔎 **Search** by name, tag, category, BPM and key
- 🎯 **Find similar** sounds by how they *sound* (acoustic similarity, not just the filename)
- 🏷️ **Auto-tag and classify** samples (kick / snare / pad / "punchy" / "airy" …)
- 🗂️ **Organize** into crates and favorites
- ⬇️ **Download** new audio from FreeSound, Yandex Music and YouTube straight into your library
- 🎛️ **Slice and export** regions in a Simpler-style editor, then drag them into your DAW
- 🎚️ **A/B compare** two samples with loudness matching
- 🧩 **Inspect DAW projects** (Ableton, Bitwig, Cubase/Nuendo, Reaper, FL Studio, Studio One, Logic, Pro Tools) — see instruments, plugins and tracks, flag plugins you don't have installed, and match the project's samples against your library
- 🔁 **Convert projects** between formats (Reaper `.RPP`, Ableton `.als`, AAF)
- 🩺 **Health dashboard** + **duplicate finder** to keep the library tidy

Everything runs locally. Your library, database and settings stay on your machine.

---

## Installation

### Windows

1. Download **`cratedig-setup-0.6.0.exe`**.
2. Run it. (Windows SmartScreen may warn because the installer isn't signed with
   a certificate — click **More info → Run anyway**.)
3. cratedig installs per-user (no admin/UAC needed). Optionally tick **Create a
   desktop shortcut**, then finish.
4. Launch **cratedig** from the Start menu or the desktop.

ffmpeg/ffplay (needed for playback, waveform previews and YouTube) are **bundled**
inside the app — nothing else to install.

To uninstall: *Settings → Apps* (or *Uninstall cratedig* in the Start menu). Your
library and settings are **preserved** (see *Where your data lives* below).

### macOS

> ⚠️ **This is an unofficial app for personal use.** It is **not signed** with an
> Apple Developer certificate and **not notarized**, so Gatekeeper blocks it by
> default. To install it for yourself you allow it to run once. Two methods are
> shown below: the safe one (this app only) and the broad one (disable the check
> system-wide).

**Requirements:** the build is native **Apple Silicon (arm64)** — it will not run
on Intel Macs. The bundled ffmpeg/ffplay are also native arm64, so **Rosetta is
not required**.

#### 1. Install the app

Open **`cratedig-0.6.0.dmg`** and drag **cratedig** into **Applications**.

#### 2. Allow the unsigned app to run

**Method A — this app only (recommended, safer):**

1. Clear the quarantine flag in Terminal:
   ```bash
   xattr -dr com.apple.quarantine /Applications/cratedig.app
   ```
2. Launch it: right-click **cratedig** → **Open** → **Open**.
   (A plain double-click is blocked the first time; right-click → "Open" allows
   this specific app.)

**Method B — allow any app system-wide (only if Method A fails):**

> 🔒 **Security warning.** The command below disables Gatekeeper **system-wide** —
> macOS stops checking the signature of *every* app. This lowers your protection.
> Use it only if you understand the risk, and **re-enable** the check afterwards
> (see step 3).

1. Disable the Gatekeeper check (admin password required):
   ```bash
   sudo spctl --master-disable
   ```
2. Open **System Settings → Privacy & Security**. Under *Security*, an option
   **"Allow applications downloaded from: Anywhere"** appears — select it.
3. Launch **cratedig** from **Applications** (now a normal double-click).

3. **(For Method B) Turn protection back on.** Once the app has launched
   successfully once, **re-enable Gatekeeper** — it isn't needed to run the
   already-installed cratedig:
   ```bash
   sudo spctl --master-enable
   ```

> **About Xcode.** You **don't need Xcode** to run the prebuilt `.dmg` — it's an
> already-compiled app, nothing to build. Xcode and the *Command Line Tools*
> (`xcode-select --install`) are needed **only** if you choose to build cratedig
> from source yourself (see `README.dev.md`).

---

## Updates

cratedig checks for updates automatically on startup (installed builds only). When
a newer version exists it shows a dialog; accept it and the app downloads, verifies
and installs the update, then relaunches itself — on both Windows and macOS, no
browser step. Every update is fetched from GitHub Releases and verified with a
minisign signature before it is applied. The check is silent when you're already up
to date or when offline.

Most releases ship as a small **delta** (only the changed app code); a **full**
installer is used for first install and when the runtime/dependencies change. Your
data in the user folder (below) is never touched by an update.

On macOS you can also apply a downloaded update file manually via
**Help → "Apply update from file…"**.

---

## First run

On first launch cratedig creates its settings and database automatically. Then:

1. Open **Settings** (sidebar / gear icon).
2. **Paths** tab → add your sample folder(s) under **Library folders**, and set a
   **Download folder** and **Saved folder** if you want custom locations.
3. Click **Scan** — cratedig indexes every audio file in those folders.
4. Click **Analyze** — it computes BPM, key and the acoustic "fingerprint" that
   *Find similar* runs on. (The first pass over a large library takes a while;
   after that it's incremental.)

That's it — browse, search and play.

---

## Where your data lives

cratedig keeps your data in your user folder, **not** in the install folder, so
uninstalling/reinstalling never touches your library:

| What | Windows | macOS |
|------|---------|-------|
| Settings (`config.toml`) | `%APPDATA%\cratedig\` | `~/Library/Application Support/cratedig/` |
| Database | `…\cratedig\data\cratedig.db` | `…/cratedig/data/cratedig.db` |
| Downloads & exports (Saved) | as set in **Settings → Paths** | same |

To back up or move your library, just copy that folder.

---

## Getting tokens

Downloading and metadata enrichment use third-party services. All tokens are
**optional** — the app works without them, the corresponding features are just
unavailable. Enter tokens in **Settings → Project Config** (or directly in
`config.toml` — see *Where your data lives*).

| Service | What for | Token needed? |
|---------|----------|---------------|
| **FreeSound** | Downloading samples | ✅ yes |
| **Yandex Music** | Downloading tracks | ✅ yes |
| **Discogs** | Track metadata enrichment | ⚪ optional |
| **MusicBrainz** | Track metadata enrichment | ❌ no (User-Agent only) |
| **YouTube** | Fallback for track downloads | ❌ no |

### FreeSound (samples)

A free API key for searching and downloading samples.

1. Create an account at **<https://freesound.org>**.
2. Open **<https://freesound.org/apiv2/apply/>** → **Create new API Credentials**.
3. Fill in the form (name and description can be anything, for personal use).
4. Copy the **"Client secret/Api key"** value.
5. Paste it into **Settings → Project Config → FreeSound token**.

> Token-only auth gives HQ-mp3 **preview** downloads (sampling-grade); full
> originals require OAuth2 and are not supported.

### Yandex Music (tracks)

An OAuth token for your Yandex Music account.

1. Sign in at **<https://music.yandex.ru>** in your browser.
2. Open the authorization link (the documented `client_id` of the
   `yandex-music-api` library):

   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d
   ```
3. Yandex redirects you to a page — copy the `access_token=...` value from the
   address bar (URL).
4. Paste it into **Settings → Project Config → Yandex token**.

> The token is tied to your account — don't share it. As an alternative to the
> settings field, save the token on a single line in a file and point to it via
> `token_file` in `config.toml`.

### Discogs (metadata, optional)

A personal token for enriching tracks with metadata (improves naming and ranking).

1. Create an account at **<https://www.discogs.com>**.
2. Open **Settings → Developers** (**<https://www.discogs.com/settings/developers>**).
3. Click **Generate new token** and copy the **Personal access token**.
4. Paste it into **Settings → Project Config → Discogs token**.

### MusicBrainz (metadata, no token)

No token needed — MusicBrainz only requires a descriptive **User-Agent** (e.g.
`your-email@example.com`). It's set in `config.toml`
(`metadata.musicbrainz_useragent`) and already filled with a default.

---

## Features

### Browse and search
A folder tree on the left, a sortable sample table on the right (filename, class,
category, BPM, key, sample rate, tags, duration). Type in the search box to filter
by name; use the tag and category filters to narrow down. Clicking or arrow-keying
through rows instantly **auditions** them; repeating the action starts/stops
playback. Select one or more rows and **drag them straight out** into your DAW,
Finder/Explorer, or any app that accepts files — the real sample files are dropped.
Right-click a row for file management: **Rename**, **Move…**, **Delete** (to the
trash, if enabled), **Reveal in Explorer/Finder**, plus crate and *Find similar*
actions. A side **Metadata** panel shows the selected sample's scan/analyze results
and embedded file tags (format, channels, length, BPM, key, …) at a glance.

### Find similar
Select a sample and click **Find similar** — cratedig ranks the rest of the library
by acoustic closeness. You can bias the match toward specific *aspects* (Overall /
Spectrum / Timbre / Pitch / Amplitude) to find, say, "same timbre, different pitch".

### Auto-tagging and classification
**Classify** guesses the instrument class and category from filenames and audio.
Analysis also derives descriptive character tags (punchy, soft, clicky, subby,
airy, metallic, tonal, percussive, long-tail …). You can add your own tags too —
manual and auto tags are tracked separately.

### Crates and favorites
Group samples into **crates** (right-click a row → *Add to crate / New crate*) and
mark **favorites** with a star. Both show up as pinned branches in the tree. **Drag
a crate** out of the tree to drop every sample it holds into your DAW or a folder
in one gesture — handy for loading a whole curated set at once.

### Downloading new audio
Open the **Download** panel, pick a mode and search:

- **Samples → FreeSound** (needs a free API token)
- **Tracks → Yandex Music** with a **YouTube** fallback (Yandex needs a token; YouTube doesn't)

You can audition results (when the backend provides a preview) and download them
straight into the library, where they're indexed automatically. Track results are
enriched with **MusicBrainz / Discogs** metadata for better naming and ranking.

> **Tokens:** Settings → **Project Config** has fields for FreeSound, Yandex and
> Discogs tokens. Step-by-step instructions for each are in the
> [**Getting tokens**](#getting-tokens) section above.

### Simpler-style editor
Load a sample into the editor panel to set a **region** (one-click **trim silence**,
**snap** the bounds to zero crossings, and **peak-normalize**), **fades**, an
**ADSR** envelope, plus **reverse** and **loop** previews. Detect **transients** and **auto-slice**. **Export** the rendered
region into the *Saved* folder
(auto-indexed) or **drag the edited region straight out** into Ableton / your DAW:
cratedig renders your current edit (region + fades + ADSR + reverse) to a fresh
audio file on the fly and drops that, so what lands in the DAW is exactly what you
shaped — not the untouched original.

### A/B compare
Open two samples side by side and switch between them with **loudness matching**,
so a volume difference doesn't bias your ears.

### Drag & drop everywhere
cratedig is built to feed your DAW without copy-paste detours:

- **Drag samples out** — select rows in the table and drag the actual files into
  Ableton, FL, Reaper, Finder/Explorer, or anything that takes a file.
- **Drag a whole crate out** — grab a crate node in the tree and drop all of its
  samples at once.
- **Drag the edited region out** — from the Simpler-style editor, your live edit is
  rendered to a new audio file and dropped, not the raw original.
- **Drag a project in** — drop a DAW project file (`.als`, `.rpp`, `.flp`, `.ptx`,
  …) onto the Project Checker to load and inspect it.

### Project Checker (multi-DAW)
Drop a DAW project file onto cratedig (or open it via the toolbar) to see its
**instruments, plugins and tracks**.
The format is detected from the file: **Ableton** (`.als`), **Bitwig**, **Cubase/
Nuendo**, **Reaper** (`.rpp`), **FL Studio** (`.flp`), **Studio One**, **Logic**
and **Pro Tools** (`.ptx`). Plugins are recognized as AU/VST2/VST3/M4L, and
cratedig checks each 3rd-party plugin against what's **actually installed on your
machine** — so it flags devices the project needs but you don't have (use **Rescan
plugins** to refresh that installed-plugin index). It also surfaces per-track detail
like plugins on the Main bus and **silent/near-silent tracks**. The **Library
Match** view finds which of the project's samples already exist in your library —
right-click to reveal in the file manager, add to a crate, or build a crate from
them. The Project Checker UI is available in **English and Russian** (EN/RU toggle).

### Convert projects
From the Project Checker, click **Convert…** to export the loaded project to another
format: **Reaper `.RPP`**, **Ableton `.als`**, or **AAF**. Conversion transfers
track/metadata structure and copies the referenced sample files; it does not carry
over plugin state, automation or rendered audio.

### Health and duplicates
The **Health** dashboard shows library statistics and flags issues (e.g. missing
files) with a one-click **Remove Missing** button. The **Duplicates** tool groups
identical files and suggests which copy to keep.

### Settings
Three tabs — **Preferences** (behavior: auto-preview, default download mode, column
visibility, send-to-trash, …), **Project Config** (tokens, metadata, audio file
extensions) and **Paths** (library/download/Saved folders, database). Changing the
library config or tokens may require restarting the app.

---

## Tips & troubleshooting

- **No sound / no waveform:** playback uses the bundled ffmpeg/ffplay; if you run
  from source, make sure `ffmpeg` and `ffplay` are on your PATH.
- **Find similar returns nothing:** run **Analyze** first — similarity needs the
  acoustic fingerprint.
- **Downloads don't work:** check the relevant token in *Settings → Project
  Config*. A local VPN/proxy can also block FreeSound results.
- **Reset everything:** quit cratedig and delete the data folder from the table
  above (this wipes your index and settings, but not the audio files themselves).

---

## License & credits

A personal-use fork inspired by Sononym. Bundles ffmpeg/ffplay (the FFmpeg project)
and is built on PySide6, librosa, yt-dlp and others.

## Contributors

Special thanks to [@OatmillerTools](https://github.com/OatmillerTools) for help
developing the backend of the Project Checker (ALS Explorer) module and valuable
contributions to the project. Original
[Project-Checker-Live](https://github.com/OatmillerTools/Project-Checker-Live).

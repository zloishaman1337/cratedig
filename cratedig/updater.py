"""Offline, local-file update applier (macOS in-app delta apply).

HARD CONSTRAINT (UPDATE_RULES.md §0, §5): no network. Updates are applied from a
user-supplied local ``cratedig-update-<ver>-mac.zip`` only — never fetched.

Two layers live here:
  * pure logic (cross-platform, unit-tested): manifest schema, hashing, version
    gate, payload verification — shared with the build-time ``make_manifest.py``;
  * thin macOS side-effects: extract → verify → spawn a dependency-free restart
    helper that swaps files after the app quits, then relaunch.

Windows deltas do NOT use this module — they ship as an external Inno installer
(``cratedig-update-<ver>.exe``) that closes the app and swaps files itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

UPDATE_MANIFEST_NAME = "update-manifest.json"
_HASH_FIELD = "manifest_sha256"

# GitHub online-update feed (UPDATE_RULES.md online model). Hardcoded on purpose:
# the local `origin` remote has historically been stale, so the feed slug must
# never be auto-detected from git.
GITHUB_REPO = "zloishaman1337/cratedig"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Release-asset names per (os, tier). The client downloads ONLY an asset whose
# name matches exactly, so GitHub's auto-generated "Source code" archives (which
# live in zipball_url/tarball_url, never in assets[]) and the .minisig signatures
# can never be mistaken for the payload.
_ASSET_NAMES = {
    ("win", "full"): "cratedig-setup-{v}.exe",
    ("win", "delta"): "cratedig-update-{v}.exe",
    ("mac", "full"): "cratedig-{v}.dmg",
    ("mac", "delta"): "cratedig-update-{v}-mac.zip",
}
SIGNATURE_SUFFIX = ".minisig"


class UpdateError(Exception):
    """Any reason an offline update cannot be applied safely."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class UpdateManifest:
    to_version: str
    from_versions: tuple[str, ...]
    files: tuple[FileEntry, ...]
    deletions: tuple[str, ...]


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Hex SHA-256 of a file's bytes (streamed, constant memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_version(s: str) -> tuple[int, ...]:
    """``"1.2.3"`` -> ``(1, 2, 3)``. Raise UpdateError on anything non-numeric."""
    try:
        parts = [int(p) for p in str(s).split(".")]
    except (ValueError, AttributeError) as exc:
        raise UpdateError(f"invalid version string: {s!r}") from exc
    if not parts:
        raise UpdateError(f"invalid version string: {s!r}")
    return tuple(parts)


def is_newer(a: str, b: str) -> bool:
    """True when version ``a`` is strictly greater than ``b`` (length-agnostic)."""
    pa, pb = parse_version(a), parse_version(b)
    width = max(len(pa), len(pb))
    pa += (0,) * (width - len(pa))
    pb += (0,) * (width - len(pb))
    return pa > pb


def manifest_sha256(doc: dict) -> str:
    """Hash of the canonical JSON of ``doc`` excluding the ``manifest_sha256`` key.

    Stable across key order; ignores any pre-existing hash field in the input so
    builder and applier agree on the same digest.
    """
    payload = {k: v for k, v in doc.items() if k != _HASH_FIELD}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_update_zip_doc(
    files: list[FileEntry],
    deletions: list[str],
    to_version: str,
    from_versions: list[str],
) -> dict:
    """Assemble the ``update-manifest.json`` document with its hash filled in."""
    doc = {
        "to_version": to_version,
        "from_versions": list(from_versions),
        "files": [{"path": f.path, "sha256": f.sha256, "size": f.size} for f in files],
        "deletions": list(deletions),
    }
    doc[_HASH_FIELD] = manifest_sha256(doc)
    return doc


def load_update_manifest(doc: dict) -> UpdateManifest:
    """Validate structure + integrity hash; return a typed manifest or raise."""
    required = ("to_version", "from_versions", "files", "deletions", _HASH_FIELD)
    missing = [k for k in required if k not in doc]
    if missing:
        raise UpdateError(f"update manifest missing keys: {', '.join(missing)}")

    if manifest_sha256(doc) != doc[_HASH_FIELD]:
        raise UpdateError("update manifest integrity check failed (sha256 mismatch)")

    try:
        files = tuple(
            FileEntry(path=str(e["path"]), sha256=str(e["sha256"]), size=int(e["size"]))
            for e in doc["files"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError(f"malformed file entry in update manifest: {exc}") from exc

    return UpdateManifest(
        to_version=str(doc["to_version"]),
        from_versions=tuple(str(v) for v in doc["from_versions"]),
        files=files,
        deletions=tuple(str(d) for d in doc["deletions"]),
    )


def check_compatible(manifest: UpdateManifest, current_version: str) -> None:
    """Raise unless the delta is newer AND applies onto the installed version."""
    if not is_newer(manifest.to_version, current_version):
        raise UpdateError(
            f"update {manifest.to_version} is not newer than installed "
            f"{current_version}; nothing to apply."
        )
    if current_version not in manifest.from_versions:
        raise UpdateError(
            f"this delta only applies onto {list(manifest.from_versions)}, but "
            f"installed version is {current_version}. Install the full .dmg instead."
        )


def verify_payload(manifest: UpdateManifest, staged_dir: str | os.PathLike[str]) -> None:
    """Every manifest file must exist under ``staged_dir`` with matching size+hash."""
    root = Path(staged_dir)
    for entry in manifest.files:
        target = root / entry.path
        if not target.is_file():
            raise UpdateError(f"update payload missing file: {entry.path}")
        if target.stat().st_size != entry.size:
            raise UpdateError(f"update payload size mismatch: {entry.path}")
        if sha256_file(target) != entry.sha256:
            raise UpdateError(f"update payload sha256 mismatch: {entry.path}")


# --------------------------------------------------------------------------- #
# GitHub online-update feed (pure parsing/selection; no network in this layer) #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    assets: tuple[ReleaseAsset, ...]


def tag_to_version(tag: str) -> str:
    """``"v0.4.0"``/``"V0.4.0"``/``"0.4.0"`` -> ``"0.4.0"`` (strip a leading v)."""
    t = str(tag).strip()
    if t[:1] in ("v", "V"):
        t = t[1:]
    return t


def current_os() -> str:
    """``"win"`` or ``"mac"``; raise on any other platform (no online build there)."""
    if sys.platform == "win32":
        return "win"
    if sys.platform == "darwin":
        return "mac"
    raise UpdateError(f"online update is unsupported on platform {sys.platform!r}")


def parse_release(doc: dict) -> Release:
    """Parse a GitHub ``/releases/latest`` payload into a typed :class:`Release`.

    Reads ONLY ``assets[]`` — the source-code archives (``zipball_url`` /
    ``tarball_url``) are deliberately never touched, so the client cannot pull
    repository source, only uploaded release assets.
    """
    tag = doc.get("tag_name")
    if not tag:
        raise UpdateError("release payload missing tag_name")
    assets: list[ReleaseAsset] = []
    for a in doc.get("assets", []):
        try:
            assets.append(
                ReleaseAsset(
                    name=str(a["name"]),
                    download_url=str(a["browser_download_url"]),
                    size=int(a.get("size", 0)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError(f"malformed release asset: {exc}") from exc
    return Release(version=tag_to_version(tag), tag=str(tag), assets=tuple(assets))


def select_asset(release: Release, os_name: str, tier: str = "full") -> ReleaseAsset:
    """Return the release asset matching ``(os_name, tier)`` exactly, else raise.

    Matching by exact filename means signature files and wrong-OS assets are
    never selected, and there is no fuzzy fallback to a "Source code" archive.
    """
    template = _ASSET_NAMES.get((os_name, tier))
    if template is None:
        raise UpdateError(f"no asset naming rule for os={os_name!r} tier={tier!r}")
    want = template.format(v=release.version)
    for a in release.assets:
        if a.name == want:
            return a
    raise UpdateError(
        f"release {release.version} has no {tier} asset for {os_name} "
        f"(expected {want!r})"
    )


def find_signature(release: Release, asset: ReleaseAsset) -> ReleaseAsset:
    """Return the ``<asset>.minisig`` companion asset, or raise if it is absent."""
    want = asset.name + SIGNATURE_SUFFIX
    for a in release.assets:
        if a.name == want:
            return a
    raise UpdateError(f"release {release.version} is missing signature {want!r}")


# --------------------------------------------------------------------------- #
# macOS in-app apply (thin side-effecting layer; not exercised on Windows CI)  #
# --------------------------------------------------------------------------- #

def read_zip_manifest(zip_path: str | os.PathLike[str]) -> dict:
    """Read and JSON-parse ``update-manifest.json`` out of the update zip."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(UPDATE_MANIFEST_NAME) as fh:
                return json.loads(fh.read().decode("utf-8"))
    except KeyError as exc:
        raise UpdateError(f"{UPDATE_MANIFEST_NAME} not found in update zip") from exc
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
        raise UpdateError(f"cannot read update zip: {exc}") from exc


def app_bundle_root() -> Path:
    """The ``cratedig.app`` directory containing the running frozen executable.

    Frozen macOS layout: ``cratedig.app/Contents/MacOS/cratedig``. Walk up to the
    ``.app``. Raises off macOS / non-frozen where in-app apply is unsupported.
    """
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        raise UpdateError("in-app update apply is only supported in the macOS app build")
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    raise UpdateError("could not locate the .app bundle from the running executable")


def _write_restart_helper(
    helper_path: Path, app_root: Path, staged_dir: Path, deletions: list[str]
) -> None:
    """Write a dependency-free bash helper that swaps files after the app exits.

    It waits for the parent (the running app) to quit, copies the staged files
    over the bundle, removes deletions, then relaunches via ``open``.
    """
    del_lines = "\n".join(
        f'rm -rf "$APP/{d}"' for d in deletions if d and ".." not in d
    )
    script = f"""#!/bin/bash
set -e
PARENT_PID="$1"
APP="{app_root}"
STAGED="{staged_dir}"
# wait for the app to fully exit so its files are no longer locked/loaded
while kill -0 "$PARENT_PID" 2>/dev/null; do sleep 0.2; done
# copy staged payload over the bundle (ditto preserves symlinks/permissions)
ditto "$STAGED" "$APP"
{del_lines}
# clear quarantine so the patched, unsigned bundle launches cleanly
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
open "$APP"
rm -rf "$STAGED" "$0"
"""
    helper_path.write_text(script, encoding="utf-8")
    helper_path.chmod(0o755)


def apply_update(
    zip_path: str | os.PathLike[str],
    current_version: str,
    app_root: Path | None = None,
) -> None:
    """Validate + stage a macOS delta zip and spawn the restart helper.

    On return the caller MUST quit the app (e.g. ``QApplication.quit()``); the
    detached helper waits for exit, swaps files, and relaunches. Raises
    UpdateError before any file is touched if the delta is invalid/incompatible.
    """
    root = app_root or app_bundle_root()
    doc = read_zip_manifest(zip_path)
    manifest = load_update_manifest(doc)
    check_compatible(manifest, current_version)

    staged = Path(tempfile.mkdtemp(prefix="cratedig-update-"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(staged)
    verify_payload(manifest, staged)

    helper = Path(tempfile.gettempdir()) / "cratedig-apply-update.sh"
    _write_restart_helper(helper, root, staged, list(manifest.deletions))
    subprocess.Popen(
        ["/bin/bash", str(helper), str(os.getpid())],
        start_new_session=True,
    )

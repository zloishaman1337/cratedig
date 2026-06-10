"""Build-time release-manifest + delta tooling (UPDATE_RULES.md §7).

Not shipped inside the app. Imports ``cratedig.updater`` so the hash/schema the
builder writes is byte-identical to what the in-app applier verifies.

Subcommands:
  generate <root> <version> <win|mac> <out.json>
      Walk an install root, write the §7.1 release manifest (sha256+size per file).
  diff <old.json> <new.json>
      Print changed/added/deleted counts and the auto tier (full|delta).
  build-delta-zip <old.json> <new.json> <root> <out.zip>
      macOS delta: zip changed/added files + update-manifest.json (§7.3b).
  build-win-include <old.json> <new.json> <out.iss>
      Windows delta: emit [Files]/[InstallDelete] include for cratedig-update.iss.

Tier rule (§7.2): full if no prior manifest, OR any changed/added/deleted path is
outside the app-owned set, OR the delta payload exceeds the size budget; else delta.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

# allow `python packaging/make_manifest.py ...` from a repo checkout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cratedig import updater  # noqa: E402

# Files an app-code-only release may change. In the PyInstaller onedir build the
# Python source is frozen into the main executable's archive, so a code edit moves
# the exe (and possibly our bundled data files) but none of the runtime libs.
#
# base_library.zip is allowlisted because PyInstaller rewrites it on EVERY build
# with fresh zip-entry mtimes — the content (and byte size) stays identical, only
# the sha256 churns. Observed validating the first real code-only diff (0.4.0 →
# 0.4.1): the only changed files were cratedig.exe and _internal/base_library.zip.
# A genuine stdlib/Python change moves the python3*.dll runtime libs too (not
# allowlisted → still forces full), so this stays safe.
DEFAULT_APP_PATHS = (
    "cratedig.exe",
    "cratedig",
    "Contents/MacOS/cratedig",
    "config.example.toml",
    "_internal/config.example.toml",
    "cratedig/db/schema.sql",
    "_internal/cratedig/db/schema.sql",
    "_internal/base_library.zip",
    "Contents/Frameworks/base_library.zip",
)

DELTA_SIZE_BUDGET = 40 * 1024 * 1024  # §7.2 escape hatch: bigger -> full


def build_manifest(root: str, version: str, os_name: str) -> dict:
    """Walk ``root`` and produce the §7.1 release manifest dict."""
    base = Path(root)
    if not base.is_dir():
        raise SystemExit(f"install root not found: {root}")
    files: dict[str, dict] = {}
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = PurePosixPath(p.relative_to(base).as_posix())
            files[str(rel)] = {
                "sha256": updater.sha256_file(p),
                "size": p.stat().st_size,
            }
    return {"version": version, "os": os_name, "files": files}


def diff_manifests(old: dict, new: dict) -> dict:
    """Return {'changed','added','deleted'} relpath lists between two manifests."""
    old_files = old.get("files", {})
    new_files = new.get("files", {})
    added = sorted(set(new_files) - set(old_files))
    deleted = sorted(set(old_files) - set(new_files))
    changed = sorted(
        p for p in set(old_files) & set(new_files)
        if old_files[p]["sha256"] != new_files[p]["sha256"]
    )
    return {"changed": changed, "added": added, "deleted": deleted}


def _is_app_path(rel: str, app_paths: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in app_paths)


def decide_tier(
    diff: dict,
    new: dict,
    app_paths: tuple[str, ...] = DEFAULT_APP_PATHS,
    size_budget: int = DELTA_SIZE_BUDGET,
) -> str:
    """'delta' if every touched path is app-owned and payload fits budget; else 'full'."""
    touched = diff["changed"] + diff["added"] + diff["deleted"]
    if not touched:
        return "delta"  # nothing changed; trivially deliverable as an (empty) delta
    if any(not _is_app_path(p, app_paths) for p in touched):
        return "full"
    new_files = new.get("files", {})
    payload = sum(new_files[p]["size"] for p in diff["changed"] + diff["added"])
    if payload > size_budget:
        return "full"
    return "delta"


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_generate(args) -> int:
    manifest = build_manifest(args.root, args.version, args.os)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"manifest: {out} ({len(manifest['files'])} files)")
    return 0


def _cmd_diff(args) -> int:
    old, new = _load(args.old), _load(args.new)
    d = diff_manifests(old, new)
    tier = decide_tier(d, new)
    print(f"changed={len(d['changed'])} added={len(d['added'])} deleted={len(d['deleted'])}")
    print(f"tier={tier}")
    return 0


def _cmd_build_delta_zip(args) -> int:
    old, new = _load(args.old), _load(args.new)
    d = diff_manifests(old, new)
    if decide_tier(d, new) == "full":
        raise SystemExit("diff requires a FULL installer, not a delta zip")
    root = Path(args.root)
    payload = d["changed"] + d["added"]
    entries = [
        updater.FileEntry(path=p, sha256=new["files"][p]["sha256"], size=new["files"][p]["size"])
        for p in payload
    ]
    doc = updater.build_update_zip_doc(
        files=entries,
        deletions=d["deleted"],
        to_version=new["version"],
        from_versions=[old["version"]],
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in payload:
            zf.write(root / rel, rel)
        zf.writestr(updater.UPDATE_MANIFEST_NAME, json.dumps(doc, indent=2))
    print(f"delta zip: {out} ({len(payload)} files, {len(d['deleted'])} deletions)")
    return 0


def _cmd_build_win_include(args) -> int:
    old, new = _load(args.old), _load(args.new)
    d = diff_manifests(old, new)
    if decide_tier(d, new) == "full":
        raise SystemExit("diff requires a FULL installer, not a delta include")
    lines = ["[Files]"]
    for rel in d["changed"] + d["added"]:
        win_rel = rel.replace("/", "\\")
        sub = str(PurePosixPath(rel).parent)
        dest = "{app}" if sub == "." else "{app}\\" + sub.replace("/", "\\")
        lines.append(
            f'Source: "{{#DistDir}}\\{win_rel}"; DestDir: "{dest}"; '
            f"Flags: ignoreversion"
        )
    if d["deleted"]:
        lines.append("")
        lines.append("[InstallDelete]")
        for rel in d["deleted"]:
            lines.append(f'Type: files; Name: "{{app}}\\{rel.replace("/", "\\")}"')
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"win include: {args.out} ({len(d['changed'] + d['added'])} files)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("root"); g.add_argument("version")
    g.add_argument("os", choices=["win", "mac"]); g.add_argument("out")
    g.set_defaults(func=_cmd_generate)

    df = sub.add_parser("diff")
    df.add_argument("old"); df.add_argument("new")
    df.set_defaults(func=_cmd_diff)

    bz = sub.add_parser("build-delta-zip")
    bz.add_argument("old"); bz.add_argument("new")
    bz.add_argument("root"); bz.add_argument("out")
    bz.set_defaults(func=_cmd_build_delta_zip)

    bi = sub.add_parser("build-win-include")
    bi.add_argument("old"); bi.add_argument("new"); bi.add_argument("out")
    bi.set_defaults(func=_cmd_build_win_include)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

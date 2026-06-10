"""Unit tests for the build-time manifest/delta tooling (packaging/make_manifest.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))
import make_manifest as mm  # noqa: E402


def _manifest(version, files):
    return {"version": version, "os": "win", "files": files}


def test_build_manifest_walks_files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"\x00\x01")
    m = mm.build_manifest(str(tmp_path), "0.3.0", "win")
    assert m["version"] == "0.3.0" and m["os"] == "win"
    assert set(m["files"]) == {"a.txt", "sub/b.bin"}  # posix-normalized keys
    assert m["files"]["a.txt"]["size"] == 5


def test_diff_detects_changed_added_deleted():
    old = _manifest("0.2.0", {
        "keep": {"sha256": "x", "size": 1},
        "edit": {"sha256": "old", "size": 1},
        "gone": {"sha256": "z", "size": 1},
    })
    new = _manifest("0.3.0", {
        "keep": {"sha256": "x", "size": 1},
        "edit": {"sha256": "new", "size": 1},
        "fresh": {"sha256": "w", "size": 1},
    })
    d = mm.diff_manifests(old, new)
    assert d == {"changed": ["edit"], "added": ["fresh"], "deleted": ["gone"]}


def test_tier_delta_when_only_app_paths_change():
    old = _manifest("0.2.0", {"cratedig.exe": {"sha256": "a", "size": 100}})
    new = _manifest("0.3.0", {"cratedig.exe": {"sha256": "b", "size": 100}})
    assert mm.decide_tier(mm.diff_manifests(old, new), new) == "delta"


def test_tier_delta_when_only_exe_and_base_library_change():
    # PyInstaller rewrites base_library.zip every build (mtime churn, identical
    # content/size); a code-only diff is exactly {cratedig.exe, base_library.zip}.
    old = _manifest("0.4.0", {
        "cratedig.exe": {"sha256": "a", "size": 100},
        "_internal/base_library.zip": {"sha256": "z1", "size": 1401781},
    })
    new = _manifest("0.4.1", {
        "cratedig.exe": {"sha256": "b", "size": 101},
        "_internal/base_library.zip": {"sha256": "z2", "size": 1401781},
    })
    assert mm.decide_tier(mm.diff_manifests(old, new), new) == "delta"


def test_tier_full_when_runtime_file_changes():
    old = _manifest("0.2.0", {"_internal/python311.dll": {"sha256": "a", "size": 100}})
    new = _manifest("0.3.0", {"_internal/python311.dll": {"sha256": "b", "size": 100}})
    assert mm.decide_tier(mm.diff_manifests(old, new), new) == "full"


def test_tier_full_when_payload_exceeds_budget():
    big = mm.DELTA_SIZE_BUDGET + 1
    old = _manifest("0.2.0", {"cratedig.exe": {"sha256": "a", "size": big}})
    new = _manifest("0.3.0", {"cratedig.exe": {"sha256": "b", "size": big}})
    assert mm.decide_tier(mm.diff_manifests(old, new), new) == "full"


def test_build_win_include_emits_files_and_deletes(tmp_path):
    old = _manifest("0.2.0", {
        "cratedig.exe": {"sha256": "a", "size": 1},
        "_internal/config.example.toml": {"sha256": "c", "size": 1},
    })
    new = _manifest("0.3.0", {"cratedig.exe": {"sha256": "b", "size": 1}})
    old_f = tmp_path / "old.json"; new_f = tmp_path / "new.json"
    out = tmp_path / "update-files.iss"
    import json
    old_f.write_text(json.dumps(old)); new_f.write_text(json.dumps(new))
    rc = mm.main(["build-win-include", str(old_f), str(new_f), str(out)])
    assert rc == 0
    text = out.read_text()
    assert "[Files]" in text and "cratedig.exe" in text
    assert "[InstallDelete]" in text
    assert "_internal\\config.example.toml" in text


def test_build_delta_zip_roundtrips_through_updater(tmp_path):
    import json
    import zipfile
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cratedig import updater

    root = tmp_path / "app"
    root.mkdir()
    (root / "cratedig.exe").write_bytes(b"new-code")
    h = updater.sha256_file(root / "cratedig.exe")
    old = _manifest("0.2.0", {"cratedig.exe": {"sha256": "old", "size": 1}})
    new = _manifest("0.3.0", {"cratedig.exe": {"sha256": h, "size": len(b"new-code")}})
    old_f = tmp_path / "old.json"; new_f = tmp_path / "new.json"
    out = tmp_path / "delta.zip"
    old_f.write_text(json.dumps(old)); new_f.write_text(json.dumps(new))

    rc = mm.main(["build-delta-zip", str(old_f), str(new_f), str(root), str(out)])
    assert rc == 0
    with zipfile.ZipFile(out) as zf:
        doc = json.loads(zf.read(updater.UPDATE_MANIFEST_NAME))
    manifest = updater.load_update_manifest(doc)  # verifies integrity hash
    assert manifest.to_version == "0.3.0"
    assert manifest.from_versions == ("0.2.0",)

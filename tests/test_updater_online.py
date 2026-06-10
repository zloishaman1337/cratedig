"""Tests for the GitHub online-update feed client (pure logic, no network).

These cover the part that guarantees "releases-only, no excess": parsing the
GitHub Releases API JSON and selecting the correct OS asset by name while
structurally ignoring source-code archives and signature files.
"""

from __future__ import annotations

import pytest

from cratedig import updater


# --------------------------------------------------------------------------- #
# tag -> version                                                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "tag, expected",
    [
        ("0.4.0", "0.4.0"),
        ("v0.4.0", "0.4.0"),
        ("V0.4.0", "0.4.0"),
        ("v1.2.3", "1.2.3"),
    ],
)
def test_tag_to_version_strips_v_prefix(tag, expected):
    assert updater.tag_to_version(tag) == expected


def test_repo_slug_is_hardcoded():
    # Backlog: origin may be stale; the feed slug must NOT be auto-detected.
    assert updater.GITHUB_REPO == "zloishaman1337/cratedig"
    assert updater.GITHUB_REPO in updater.LATEST_RELEASE_API
    assert updater.LATEST_RELEASE_API.startswith("https://api.github.com/")


# --------------------------------------------------------------------------- #
# parse_release                                                               #
# --------------------------------------------------------------------------- #

def _api_doc():
    """A realistic /releases/latest payload (assets[] never contains source code)."""
    return {
        "tag_name": "v0.4.0",
        "name": "CRATEDIG 0.4.0",
        # GitHub puts source archives in these fields, NOT in assets[]:
        "zipball_url": "https://api.github.com/repos/zloishaman1337/cratedig/zipball/v0.4.0",
        "tarball_url": "https://api.github.com/repos/zloishaman1337/cratedig/tarball/v0.4.0",
        "assets": [
            {
                "name": "cratedig-setup-0.4.0.exe",
                "browser_download_url": "https://github.com/zloishaman1337/cratedig/releases/download/v0.4.0/cratedig-setup-0.4.0.exe",
                "size": 167788239,
            },
            {
                "name": "cratedig-setup-0.4.0.exe.minisig",
                "browser_download_url": "https://github.com/zloishaman1337/cratedig/releases/download/v0.4.0/cratedig-setup-0.4.0.exe.minisig",
                "size": 178,
            },
            {
                "name": "cratedig-0.4.0.dmg",
                "browser_download_url": "https://github.com/zloishaman1337/cratedig/releases/download/v0.4.0/cratedig-0.4.0.dmg",
                "size": 171392676,
            },
            {
                "name": "cratedig-0.4.0.dmg.minisig",
                "browser_download_url": "https://github.com/zloishaman1337/cratedig/releases/download/v0.4.0/cratedig-0.4.0.dmg.minisig",
                "size": 178,
            },
        ],
    }


def test_parse_release_reads_version_and_assets():
    rel = updater.parse_release(_api_doc())
    assert rel.version == "0.4.0"
    assert rel.tag == "v0.4.0"
    names = {a.name for a in rel.assets}
    assert "cratedig-setup-0.4.0.exe" in names
    assert "cratedig-0.4.0.dmg" in names


def test_parse_release_ignores_source_archive_fields():
    # The parser must only read assets[]; zipball/tarball must never become assets.
    rel = updater.parse_release(_api_doc())
    urls = {a.download_url for a in rel.assets}
    assert not any("zipball" in u or "tarball" in u for u in urls)


def test_parse_release_missing_tag_raises():
    with pytest.raises(updater.UpdateError):
        updater.parse_release({"assets": []})


# --------------------------------------------------------------------------- #
# select_asset — the "no excess" guarantee                                    #
# --------------------------------------------------------------------------- #

def test_select_asset_win_full():
    rel = updater.parse_release(_api_doc())
    a = updater.select_asset(rel, "win", "full")
    assert a.name == "cratedig-setup-0.4.0.exe"
    assert a.download_url.endswith("cratedig-setup-0.4.0.exe")


def test_select_asset_mac_full():
    rel = updater.parse_release(_api_doc())
    a = updater.select_asset(rel, "mac", "full")
    assert a.name == "cratedig-0.4.0.dmg"


def test_select_asset_never_returns_signature():
    rel = updater.parse_release(_api_doc())
    a = updater.select_asset(rel, "win", "full")
    assert not a.name.endswith(".minisig")


def test_select_asset_missing_raises():
    # No delta assets uploaded -> asking for one must raise, not silently fall back.
    rel = updater.parse_release(_api_doc())
    with pytest.raises(updater.UpdateError):
        updater.select_asset(rel, "win", "delta")


def test_select_asset_rejects_unknown_os():
    rel = updater.parse_release(_api_doc())
    with pytest.raises(updater.UpdateError):
        updater.select_asset(rel, "linux", "full")


def test_find_signature_returns_matching_minisig():
    rel = updater.parse_release(_api_doc())
    asset = updater.select_asset(rel, "win", "full")
    sig = updater.find_signature(rel, asset)
    assert sig.name == "cratedig-setup-0.4.0.exe.minisig"


def test_find_signature_missing_raises():
    doc = _api_doc()
    doc["assets"] = [a for a in doc["assets"] if not a["name"].endswith(".minisig")]
    rel = updater.parse_release(doc)
    asset = updater.select_asset(rel, "win", "full")
    with pytest.raises(updater.UpdateError):
        updater.find_signature(rel, asset)


# --------------------------------------------------------------------------- #
# current_os helper                                                           #
# --------------------------------------------------------------------------- #

def test_current_os_known(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    assert updater.current_os() == "win"
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    assert updater.current_os() == "mac"


def test_current_os_unsupported_raises(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    with pytest.raises(updater.UpdateError):
        updater.current_os()


# --------------------------------------------------------------------------- #
# I/O layer (network + verify) with injected fakes                            #
# --------------------------------------------------------------------------- #

import io
import json
import contextlib


@contextlib.contextmanager
def _fake_response(payload: bytes):
    yield io.BytesIO(payload)


def test_fetch_latest_release_parses(monkeypatch):
    doc = _api_doc()

    def opener(req, timeout=None):
        # the request must target the hardcoded feed URL
        assert req.full_url == updater.LATEST_RELEASE_API
        return _fake_response(json.dumps(doc).encode("utf-8"))

    rel = updater.fetch_latest_release(opener=opener)
    assert rel.version == "0.4.0"


def test_fetch_latest_release_network_error_raises():
    def opener(req, timeout=None):
        raise OSError("no route to host")

    with pytest.raises(updater.UpdateError):
        updater.fetch_latest_release(opener=opener)


def test_fetch_latest_release_bad_json_raises():
    def opener(req, timeout=None):
        return _fake_response(b"<html>not json</html>")

    with pytest.raises(updater.UpdateError):
        updater.fetch_latest_release(opener=opener)


def test_download_asset_writes_and_checks_size(tmp_path):
    body = b"x" * 1024
    asset = updater.ReleaseAsset(name="cratedig-setup-0.4.0.exe", download_url="http://h/a", size=len(body))

    def opener(req, timeout=None):
        return _fake_response(body)

    out = updater.download_asset(asset, tmp_path, opener=opener)
    assert out.read_bytes() == body


def test_download_asset_size_mismatch_raises(tmp_path):
    asset = updater.ReleaseAsset(name="a.exe", download_url="http://h/a", size=999)

    def opener(req, timeout=None):
        return _fake_response(b"short")

    with pytest.raises(updater.UpdateError):
        updater.download_asset(asset, tmp_path, opener=opener)


class _Proc:
    def __init__(self, rc, err=""):
        self.returncode = rc
        self.stderr = err
        self.stdout = ""


def test_verify_signature_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "minisign_path", lambda: "minisign")
    f = tmp_path / "a.exe"; f.write_bytes(b"data")
    s = tmp_path / "a.exe.minisig"; s.write_text("sig")
    captured = {}

    def runner(cmd, capture_output=None, text=None):
        captured["cmd"] = cmd
        return _Proc(0)

    updater.verify_signature(f, s, runner=runner)
    assert "-V" in captured["cmd"] and updater.MINISIGN_PUBKEY in captured["cmd"]


def test_verify_signature_bad_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "minisign_path", lambda: "minisign")
    f = tmp_path / "a.exe"; f.write_bytes(b"data")
    s = tmp_path / "a.exe.minisig"; s.write_text("sig")

    def runner(cmd, capture_output=None, text=None):
        return _Proc(1, err="Signature verification failed")

    with pytest.raises(updater.UpdateError):
        updater.verify_signature(f, s, runner=runner)


def test_download_and_verify_happy_path(monkeypatch, tmp_path):
    rel = updater.parse_release(_api_doc())
    monkeypatch.setattr(updater, "minisign_path", lambda: "minisign")

    def fake_download(asset, dest_dir, **kw):
        p = tmp_path / asset.name
        p.write_bytes(b"payload")
        return p

    monkeypatch.setattr(updater, "download_asset", fake_download)
    monkeypatch.setattr(updater, "verify_signature", lambda *a, **k: None)

    out = updater.download_and_verify(rel, tmp_path, os_name="win", tier="full")
    assert out.name == "cratedig-setup-0.4.0.exe"


# --------------------------------------------------------------------------- #
# macOS full-dmg in-app apply                                                 #
# --------------------------------------------------------------------------- #

def test_apply_dmg_update_non_darwin_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    with pytest.raises(updater.UpdateError):
        updater.apply_dmg_update(tmp_path / "x.dmg")


def test_dmg_restart_helper_script_shape(tmp_path):
    from pathlib import Path

    helper = tmp_path / "h.sh"
    updater._write_dmg_restart_helper(
        helper,
        Path("/Users/x/Applications/cratedig.app"),
        Path("/tmp/mnt"),
        Path("/tmp/mnt/cratedig.app"),
    )
    text = helper.read_text()
    # waits for the parent to exit, copies safely, swaps, detaches, relaunches
    assert 'kill -0 "$PARENT_PID"' in text
    assert 'ditto "$SRC" "$APP.new"' in text
    assert 'mv "$APP.new" "$APP"' in text
    assert "hdiutil detach" in text
    assert "open \"$APP\"" in text

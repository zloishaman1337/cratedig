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

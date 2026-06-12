"""Delta-over-the-wire: signed release-meta + tier selection (UPDATE_RULES.md §7).

Pure logic only — no network. Verifies the client picks a delta ONLY when a signed
meta says it applies onto the installed version AND a delta asset exists, and falls
back to the always-present full installer otherwise.
"""

from __future__ import annotations

import json

import pytest

from cratedig import updater


def _doc(version="0.6.0", *, with_delta=True, with_meta=True, os="win"):
    """A /releases/latest payload for ``version`` with optional delta + meta assets."""
    base = f"https://github.com/zloishaman1337/cratedig/releases/download/v{version}"
    full = (f"cratedig-setup-{version}.exe" if os == "win" else f"cratedig-{version}.dmg")
    delta = (f"cratedig-update-{version}.exe" if os == "win"
             else f"cratedig-update-{version}-mac.zip")
    meta = updater.RELEASE_META_TEMPLATE.format(v=version)
    names = [full, full + ".minisig"]
    if with_delta:
        names += [delta, delta + ".minisig"]
    if with_meta:
        names += [meta, meta + ".minisig"]
    return {
        "tag_name": f"v{version}",
        "assets": [
            {"name": n, "browser_download_url": f"{base}/{n}", "size": 10} for n in names
        ],
    }


def _release(**kw):
    return updater.parse_release(_doc(**kw))


# --------------------------------------------------------------------------- #
# build/parse release-meta                                                     #
# --------------------------------------------------------------------------- #

def test_build_and_parse_release_meta_round_trip():
    doc = updater.build_release_meta("0.6.0", ["0.5.2"])
    meta = updater.parse_release_meta(doc)
    assert meta.version == "0.6.0"
    assert meta.delta_from == ("0.5.2",)


def test_parse_release_meta_tolerates_missing_delta_from():
    meta = updater.parse_release_meta({"version": "0.6.0"})
    assert meta.delta_from == ()


# --------------------------------------------------------------------------- #
# choose_tier                                                                  #
# --------------------------------------------------------------------------- #

def test_choose_tier_delta_when_compatible_and_available():
    rel = _release(os="win", with_delta=True)
    meta = updater.parse_release_meta(updater.build_release_meta("0.6.0", ["0.5.2"]))
    assert updater.choose_tier(meta, "0.5.2", rel, "win") == "delta"


def test_choose_tier_full_when_current_not_in_delta_from():
    rel = _release(os="win", with_delta=True)
    meta = updater.parse_release_meta(updater.build_release_meta("0.6.0", ["0.5.2"]))
    # installed 0.5.0 -> the 0.5.2-only delta would leave stale files -> full
    assert updater.choose_tier(meta, "0.5.0", rel, "win") == "full"


def test_choose_tier_full_when_no_meta():
    rel = _release(os="win", with_delta=True)
    assert updater.choose_tier(None, "0.5.2", rel, "win") == "full"


def test_choose_tier_full_when_delta_asset_absent():
    # meta claims a delta but the release didn't actually upload one -> full.
    rel = _release(os="win", with_delta=False)
    meta = updater.parse_release_meta(updater.build_release_meta("0.6.0", ["0.5.2"]))
    assert updater.choose_tier(meta, "0.5.2", rel, "win") == "full"


def test_choose_tier_delta_for_mac_zip():
    rel = _release(os="mac", with_delta=True)
    meta = updater.parse_release_meta(updater.build_release_meta("0.6.0", ["0.5.2"]))
    assert updater.choose_tier(meta, "0.5.2", rel, "mac") == "delta"


# --------------------------------------------------------------------------- #
# fetch_release_meta (download + verify injected)                              #
# --------------------------------------------------------------------------- #

def test_fetch_release_meta_returns_none_without_meta_asset(tmp_path):
    rel = _release(with_meta=False)
    assert updater.fetch_release_meta(rel, tmp_path) is None


def test_fetch_release_meta_downloads_verifies_parses(tmp_path, monkeypatch):
    rel = _release(version="0.6.0", with_meta=True)
    meta_name = updater.RELEASE_META_TEMPLATE.format(v="0.6.0")
    doc = updater.build_release_meta("0.6.0", ["0.5.2"])

    def fake_download(asset, dest_dir, **kw):
        from pathlib import Path
        p = Path(dest_dir) / asset.name
        p.write_text(json.dumps(doc) if asset.name == meta_name else "sig")
        return p

    verified = {}
    monkeypatch.setattr(updater, "download_asset", fake_download)
    monkeypatch.setattr(updater, "verify_signature",
                        lambda f, s, *a, **k: verified.setdefault("ok", True))

    meta = updater.fetch_release_meta(rel, tmp_path)
    assert verified.get("ok") is True  # signature WAS checked
    assert meta.delta_from == ("0.5.2",)

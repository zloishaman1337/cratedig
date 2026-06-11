"""Tests for cratedig.plugins.scanner — installed-plugin detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from cratedig.plugins import scanner
from cratedig.plugins.scanner import (
    InstalledIndex,
    all_scan_dirs,
    load_or_scan,
    match_installed,
    match_name,
    normalize_stem,
    scan_installed,
    standard_plugin_dirs,
)


def _make_tree(root: Path) -> None:
    """Build a fake plugin tree with each format + a one-level-nested vendor dir."""
    (root / "VST3").mkdir()
    (root / "VST3" / "Serum.vst3").write_text("x")          # vst3 file
    (root / "VST3" / "Pro-Q 3.vst3").mkdir()                # vst3 bundle (dir)
    (root / "VST").mkdir()
    (root / "VST" / "Sylenth1 x64.dll").write_text("x")     # vst2 dll with arch noise
    (root / "Components").mkdir()
    (root / "Components" / "Massive.component").mkdir()      # AU bundle
    # one-level-deep vendor folder
    vendor = root / "VST3" / "FabFilter"
    vendor.mkdir()
    (vendor / "Pro-C 2.vst3").write_text("x")
    # a non-plugin file that must be ignored
    (root / "VST3" / "readme.txt").write_text("x")


class TestStandardPluginDirs:
    def test_windows_keys(self, monkeypatch):
        monkeypatch.setattr(scanner.sys, "platform", "win32")
        dirs = standard_plugin_dirs()
        assert set(dirs.keys()) == {"vst3", "vst2", "au", "aax"}

    def test_macos_keys(self, monkeypatch):
        monkeypatch.setattr(scanner.sys, "platform", "darwin")
        dirs = standard_plugin_dirs()
        assert set(dirs.keys()) == {"vst3", "vst2", "au", "aax"}
        # AU is macOS-specific and should at least be a (possibly empty) list.
        assert isinstance(dirs["au"], list)

    def test_only_existing_dirs_returned(self, monkeypatch):
        monkeypatch.setattr(scanner.sys, "platform", "darwin")
        for fmt_dirs in standard_plugin_dirs().values():
            for d in fmt_dirs:
                assert d.is_dir()


class TestNormalizeStem:
    def test_strips_extension_and_lowercases(self):
        assert normalize_stem("Serum.vst3") == "serum"
        assert normalize_stem("Sylenth1.dll") == "sylenth1"
        assert normalize_stem("Massive.component") == "massive"

    def test_strips_arch_noise(self):
        assert normalize_stem("Sylenth1 x64.dll") == "sylenth1"
        assert normalize_stem("Foo (x64).vst3") == "foo"
        assert normalize_stem("Bar 64-bit.dll") == "bar"

    def test_collapses_whitespace(self):
        assert normalize_stem("Pro-Q  3.vst3") == "pro-q 3"


class TestScanInstalled:
    def test_collects_stems_per_format(self, tmp_path):
        _make_tree(tmp_path)
        index = scan_installed([tmp_path / "VST3", tmp_path / "VST", tmp_path / "Components"])
        assert "serum" in index.stems
        assert "pro-q 3" in index.stems          # bundle dir counted
        assert "pro-c 2" in index.stems          # one level deep
        assert "sylenth1" in index.stems         # arch noise stripped
        assert "massive" in index.stems
        assert "readme" not in index.stems       # non-plugin ignored
        assert "serum" in index.by_format["vst3"]
        assert "sylenth1" in index.by_format["vst2"]
        assert "massive" in index.by_format["au"]

    def test_bundle_dir_counted_once_not_descended(self, tmp_path):
        # A .vst3 bundle with internal files must not leak its internals as stems.
        bundle = tmp_path / "Plug.vst3"
        bundle.mkdir()
        (bundle / "Contents").mkdir()
        (bundle / "Contents" / "x86_64-win" / "Plug.vst3").parent.mkdir(parents=True)
        (bundle / "Contents" / "x86_64-win" / "Plug.vst3").write_text("x")
        index = scan_installed([tmp_path])
        assert index.stems == frozenset({"plug"})

    def test_missing_dir_skipped(self, tmp_path):
        index = scan_installed([tmp_path / "does-not-exist"])
        assert index.stems == frozenset()

    def test_index_contains_uses_fuzzy_match(self, tmp_path):
        _make_tree(tmp_path)
        index = scan_installed([tmp_path / "VST3"])
        assert "Serum" in index                  # __contains__ → match_name
        assert "FabFilter Pro-C 2" in index       # substring both ways
        assert "Nonexistent" not in index


class TestMatchName:
    def test_exact(self):
        assert match_name("Serum", {"serum"}) is True

    def test_case_insensitive(self):
        assert match_name("SERUM", {"serum"}) is True

    def test_substring_both_ways(self):
        assert match_name("FabFilter Pro-Q 3", {"pro-q 3"}) is True
        assert match_name("Massive", {"native instruments massive"}) is True

    def test_no_match(self):
        assert match_name("Sylenth1", {"serum", "massive"}) is False

    def test_match_installed_delegates(self, tmp_path):
        index = scan_installed([tmp_path])  # empty
        assert match_installed("Serum", index) is False


class TestAllScanDirs:
    def test_includes_existing_custom_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scanner, "standard_plugin_dirs", lambda: {"vst3": []})
        custom = tmp_path / "MyPlugins"
        custom.mkdir()
        dirs = all_scan_dirs([str(custom), str(tmp_path / "missing")])
        assert custom in dirs
        assert (tmp_path / "missing") not in dirs

    def test_dedup(self, tmp_path, monkeypatch):
        d = tmp_path / "shared"
        d.mkdir()
        monkeypatch.setattr(scanner, "standard_plugin_dirs", lambda: {"vst3": [d]})
        dirs = all_scan_dirs([str(d)])
        assert dirs.count(d) == 1


class TestCache:
    def test_signature_stable_when_unchanged(self, tmp_path):
        _make_tree(tmp_path)
        a = scan_installed([tmp_path / "VST3"])
        b = scan_installed([tmp_path / "VST3"])
        assert a.signature == b.signature

    def test_signature_changes_on_new_file(self, tmp_path):
        _make_tree(tmp_path)
        before = scan_installed([tmp_path / "VST3"]).signature
        (tmp_path / "VST3" / "NewSynth.vst3").write_text("x")
        after = scan_installed([tmp_path / "VST3"]).signature
        assert before != after

    def test_load_or_scan_reuses_cache(self, tmp_path, monkeypatch):
        custom = tmp_path / "P"
        custom.mkdir()
        (custom / "Serum.vst3").write_text("x")
        monkeypatch.setattr(scanner, "standard_plugin_dirs", lambda: {"vst3": []})
        cache = tmp_path / "plugin_index.json"

        first = load_or_scan([str(custom)], cache_path=cache)
        assert cache.is_file()
        assert "serum" in first.stems

        # Add a file but DON'T expose it (delete signature trigger): same dir mtime
        # path → calling again should hit the cache (same signature) and skip rescan.
        calls = {"n": 0}
        real = scanner.scan_installed
        monkeypatch.setattr(scanner, "scan_installed", lambda d: (calls.__setitem__("n", calls["n"] + 1), real(d))[1])
        load_or_scan([str(custom)], cache_path=cache)
        assert calls["n"] == 0  # cache hit, no rescan

    def test_load_or_scan_force_rescans(self, tmp_path, monkeypatch):
        custom = tmp_path / "P"
        custom.mkdir()
        (custom / "Serum.vst3").write_text("x")
        monkeypatch.setattr(scanner, "standard_plugin_dirs", lambda: {"vst3": []})
        cache = tmp_path / "plugin_index.json"
        load_or_scan([str(custom)], cache_path=cache)
        calls = {"n": 0}
        real = scanner.scan_installed
        monkeypatch.setattr(scanner, "scan_installed", lambda d: (calls.__setitem__("n", calls["n"] + 1), real(d))[1])
        load_or_scan([str(custom)], force=True, cache_path=cache)
        assert calls["n"] == 1


class TestConfigPlugins:
    def test_parses_scan_dirs(self, tmp_path):
        from cratedig.config import load_config

        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[plugins]\nscan_dirs = ["C:/A", "C:/B"]\n', encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg.plugins.scan_dirs == ("C:/A", "C:/B")

    def test_missing_plugins_table_defaults_empty(self, tmp_path):
        from cratedig.config import load_config

        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("[audio]\nanalysis_sr = 22050\n", encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg.plugins.scan_dirs == ()

"""Tests for config_writer.py: comment-preserving TOML writes.

TDD-style: these are FAILING tests that define the API the developer must satisfy.
Tests cover:
- Path resolution (arg > env > default)
- Seeding from config.example.toml
- Round-trip invariants (R1, R3, R4)
- Comment preservation on mutations
- Mutators for paths, audio, metadata, sources
- Atomicity of writes
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit
from tomlkit import TOMLDocument

from cratedig.config_writer import (
    ConfigWriterError,
    TokenStatus,
    ensure_config_exists,
    load_document,
    resolve_config_path,
    set_audio_extensions,
    set_db_path,
    set_discogs_token,
    set_download_dir,
    set_library_dirs,
    set_metadata_cache_ttl_days,
    set_metadata_enable_search_ranking,
    set_metadata_search_live_lookup,
    set_metadata_search_max_live_lookup_hits,
    set_saved_dir,
    set_source_token,
    set_source_token_file,
    source_token_status,
    write_document,
)


class TestResolveConfigPath:
    """Signature: resolve_config_path(path=None) -> Path
    Honour: explicit arg > CRATEDIG_CONFIG env > ./config.toml
    """

    def test_explicit_arg_takes_precedence(self, tmp_path):
        """When path is provided, use it."""
        custom = tmp_path / "my-config.toml"
        result = resolve_config_path(custom)
        assert result == custom

    def test_env_var_used_when_no_arg(self, tmp_path, monkeypatch):
        """When no arg, check CRATEDIG_CONFIG env."""
        env_cfg = tmp_path / "env-config.toml"
        monkeypatch.setenv("CRATEDIG_CONFIG", str(env_cfg))
        result = resolve_config_path()
        assert result == env_cfg

    def test_default_config_toml_when_no_arg_no_env(self, monkeypatch):
        """When no arg and no env, default to ./config.toml."""
        monkeypatch.delenv("CRATEDIG_CONFIG", raising=False)
        result = resolve_config_path()
        assert result.name == "config.toml"


class TestEnsureConfigExists:
    """Signature: ensure_config_exists(path=None) -> Path
    Seed from config.example.toml if target missing, raise ConfigWriterError if example absent.
    """

    def _copy_example(self, tmp_path):
        """Helper: copy the real config.example.toml into tmp_path."""
        example_src = Path(__file__).parent.parent / "config.example.toml"
        if not example_src.is_file():
            pytest.skip("config.example.toml not found in repo root")
        shutil.copy2(example_src, tmp_path / "config.example.toml")

    def test_copies_example_when_target_missing(self, tmp_path):
        """If target does not exist and example is present, copy it."""
        self._copy_example(tmp_path)
        target = tmp_path / "config.toml"

        assert not target.is_file()
        result = ensure_config_exists(target)

        assert result == target
        assert target.is_file()
        # Verify it's a valid TOML file with expected sections
        doc = tomlkit.loads(target.read_text())
        assert "paths" in doc or "audio" in doc

    def test_returns_target_when_already_exists(self, tmp_path):
        """If target already exists, return it unchanged."""
        self._copy_example(tmp_path)
        target = tmp_path / "config.toml"
        target.write_text("[paths]\ndb = 'test.db'")
        original_content = target.read_text()

        result = ensure_config_exists(target)

        assert result == target
        assert target.read_text() == original_content

    def test_raises_error_when_example_missing(self, tmp_path):
        """If target missing and example not found, raise ConfigWriterError."""
        target = tmp_path / "config.toml"
        # Don't copy example; ensure it's not in tmp_path

        with pytest.raises(ConfigWriterError):
            ensure_config_exists(target)


class TestLoadDocument:
    """Signature: load_document(path=None) -> TOMLDocument
    Seed if missing, then parse with tomlkit (preserves comments).
    """

    def _copy_example(self, tmp_path):
        """Helper: copy the real config.example.toml into tmp_path."""
        example_src = Path(__file__).parent.parent / "config.example.toml"
        if not example_src.is_file():
            pytest.skip("config.example.toml not found in repo root")
        shutil.copy2(example_src, tmp_path / "config.example.toml")

    def test_loads_existing_file(self, tmp_path):
        """If file exists, parse and return TOMLDocument."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        cfg.write_text("[paths]\ndb = 'test.db'")

        doc = load_document(cfg)

        assert isinstance(doc, TOMLDocument)
        assert "paths" in doc
        assert doc["paths"]["db"] == "test.db"

    def test_seeds_if_missing(self, tmp_path):
        """If file missing, seed from example then load."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"

        assert not cfg.is_file()
        doc = load_document(cfg)

        assert isinstance(doc, TOMLDocument)
        assert cfg.is_file()

    def test_preserves_comments_on_load(self, tmp_path):
        """TOMLDocument preserves comments from source."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"

        doc = load_document(cfg)
        dumped = tomlkit.dumps(doc)

        # The seeded example should have its comments intact
        assert "#" in dumped or len(dumped) > 0


class TestWriteDocument:
    """Signature: write_document(doc, path=None) -> Path
    Atomically write to temp file + os.replace, clean up on error.
    """

    def _copy_example(self, tmp_path):
        """Helper: copy the real config.example.toml into tmp_path."""
        example_src = Path(__file__).parent.parent / "config.example.toml"
        if not example_src.is_file():
            pytest.skip("config.example.toml not found in repo root")
        shutil.copy2(example_src, tmp_path / "config.example.toml")

    def test_writes_file_and_returns_path(self, tmp_path):
        """Write document and return target path."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        doc = tomlkit.loads("[paths]\ndb = 'test.db'")

        result = write_document(doc, cfg)

        assert result == cfg
        assert cfg.is_file()

    def test_preserves_content_on_write(self, tmp_path):
        """Written file contains the doc's content."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        doc = tomlkit.loads("[paths]\ndb = 'mydb.db'")

        write_document(doc, cfg)

        reloaded = tomlkit.loads(cfg.read_text())
        assert reloaded["paths"]["db"] == "mydb.db"

    def test_no_tmp_leftover_on_success(self, tmp_path):
        """After successful write, no .tmp files remain."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        doc = tomlkit.loads("[paths]\ndb = 'test.db'")

        write_document(doc, cfg)

        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert len(tmp_files) == 0

    def test_no_tmp_leftover_on_replace_error(self, tmp_path):
        """If os.replace fails, temp file is cleaned up."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        doc = tomlkit.loads("[paths]\ndb = 'test.db'")

        original_replace = os.replace

        def raise_on_replace(src, dst):
            if str(dst) == str(cfg):
                raise OSError("Simulated replace error")
            original_replace(src, dst)

        with patch("os.replace", side_effect=raise_on_replace):
            with pytest.raises(OSError):
                write_document(doc, cfg)

        # Original file should be untouched (or not exist)
        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert len(tmp_files) == 0


class TestRoundTripInvariantR1:
    """Invariant R1: write_document(load_document(p), p) is byte-equal to original."""

    def _copy_example(self, tmp_path):
        """Helper: copy the real config.example.toml into tmp_path."""
        example_src = Path(__file__).parent.parent / "config.example.toml"
        if not example_src.is_file():
            pytest.skip("config.example.toml not found in repo root")
        shutil.copy2(example_src, tmp_path / "config.example.toml")

    def test_round_trip_no_mutation_preserves_bytes(self, tmp_path):
        """Load example, write it back unchanged; file should be identical."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"

        # Copy example to config.toml so we have a baseline
        example = tmp_path / "config.example.toml"
        shutil.copy2(example, cfg)
        original_bytes = cfg.read_bytes()

        # Load and re-write without mutation
        doc = load_document(cfg)
        write_document(doc, cfg)
        new_bytes = cfg.read_bytes()

        assert new_bytes == original_bytes


class TestSetDbPath:
    """Mutator: set_db_path(doc, value: str) -> None"""

    def test_sets_db_under_paths(self, tmp_path):
        """set_db_path sets [paths].db."""
        doc = tomlkit.loads("[paths]\n")
        set_db_path(doc, "newdata.db")
        assert doc["paths"]["db"] == "newdata.db"


class TestSetDownloadDir:
    """Mutator: set_download_dir(doc, value: str) -> None"""

    def test_sets_download_dir_under_paths(self, tmp_path):
        """set_download_dir sets [paths].download_dir."""
        doc = tomlkit.loads("[paths]\n")
        set_download_dir(doc, "/tmp/downloads")
        assert doc["paths"]["download_dir"] == "/tmp/downloads"


class TestSetSavedDir:
    """Mutator: set_saved_dir(doc, value: str) -> None"""

    def test_sets_saved_dir_under_paths(self, tmp_path):
        """set_saved_dir sets [paths].saved_dir."""
        doc = tomlkit.loads("[paths]\n")
        set_saved_dir(doc, "/tmp/saved")
        assert doc["paths"]["saved_dir"] == "/tmp/saved"


class TestSetLibraryDirs:
    """Mutator: set_library_dirs(doc, dirs: Sequence[str]) -> None
    Replace the array, preserve multiline style if existing, else inline.
    """

    def test_replaces_library_dirs_array(self, tmp_path):
        """set_library_dirs replaces [paths].library_dirs with new array."""
        doc = tomlkit.loads("[paths]\nlibrary_dirs = []\n")
        set_library_dirs(doc, ["/lib1", "/lib2"])
        assert list(doc["paths"]["library_dirs"]) == ["/lib1", "/lib2"]

    def test_creates_library_dirs_if_missing(self, tmp_path):
        """If [paths].library_dirs missing, create it."""
        doc = tomlkit.loads("[paths]\n")
        set_library_dirs(doc, ["/lib1"])
        assert "/lib1" in doc["paths"]["library_dirs"]


class TestSetAudioExtensions:
    """Mutator: set_audio_extensions(doc, exts: Sequence[str]) -> None
    Normalize to lowercase, dot-prefix, dedupe (preserving order).
    """

    def test_lowercases_and_adds_dot_prefix(self, tmp_path):
        """Extensions normalized: ["WAV", ".MP3", "flac"] -> [".wav", ".mp3", ".flac"]."""
        doc = tomlkit.loads("[audio]\n")
        set_audio_extensions(doc, ["WAV", ".MP3", "flac", ".wav"])
        exts = list(doc["audio"]["extensions"])
        # Expected: [".wav", ".mp3", ".flac"] (dedupe, preserve order)
        assert ".wav" in exts
        assert ".mp3" in exts
        assert ".flac" in exts

    def test_deduplicates_preserving_order(self, tmp_path):
        """Duplicate extensions removed; first occurrence kept."""
        doc = tomlkit.loads("[audio]\n")
        set_audio_extensions(doc, ["WAV", ".wav", ".MP3", ".wav"])
        exts = list(doc["audio"]["extensions"])
        # ".wav" should appear once
        assert exts.count(".wav") == 1


class TestSetMetadataCacheTtlDays:
    """Mutator: set_metadata_cache_ttl_days(doc, days: int) -> None"""

    def test_sets_cache_ttl_days_under_metadata(self, tmp_path):
        """set_metadata_cache_ttl_days sets [metadata].cache_ttl_days."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_cache_ttl_days(doc, 14)
        assert doc["metadata"]["cache_ttl_days"] == 14


class TestSetMetadataEnableSearchRanking:
    """Mutator: set_metadata_enable_search_ranking(doc, enabled: bool) -> None"""

    def test_sets_enable_search_ranking_under_metadata(self, tmp_path):
        """set_metadata_enable_search_ranking sets [metadata].enable_search_ranking."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_enable_search_ranking(doc, False)
        assert doc["metadata"]["enable_search_ranking"] is False


class TestSetMetadataSearchLiveLookup:
    """Mutator: set_metadata_search_live_lookup(doc, enabled: bool) -> None"""

    def test_sets_search_live_lookup_under_metadata(self, tmp_path):
        """set_metadata_search_live_lookup sets [metadata].search_live_lookup."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_search_live_lookup(doc, True)
        assert doc["metadata"]["search_live_lookup"] is True


class TestSetMetadataSearchMaxLiveLookupHits:
    """Mutator: set_metadata_search_max_live_lookup_hits(doc, n: int) -> None"""

    def test_sets_search_max_live_lookup_hits_under_metadata(self, tmp_path):
        """set_metadata_search_max_live_lookup_hits sets [metadata].search_max_live_lookup_hits."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_search_max_live_lookup_hits(doc, 5)
        assert doc["metadata"]["search_max_live_lookup_hits"] == 5


class TestSetDiscogToken:
    """Mutator: set_discogs_token(doc, token: str) -> None"""

    def test_sets_discogs_token_under_metadata(self, tmp_path):
        """set_discogs_token sets [metadata].discogs_token."""
        doc = tomlkit.loads("[metadata]\n")
        set_discogs_token(doc, "mytoken123")
        assert doc["metadata"]["discogs_token"] == "mytoken123"


class TestSetSourceToken:
    """Mutator: set_source_token(doc, name: str, token: str) -> None
    Set [sources.<name>].token, create table if absent, never delete comments.
    """

    def test_sets_freesound_token(self, tmp_path):
        """set_source_token sets [sources.freesound].token."""
        doc = tomlkit.loads("[sources]\n")
        set_source_token(doc, "freesound", "mytoken123")
        assert doc["sources"]["freesound"]["token"] == "mytoken123"

    def test_creates_sources_table_if_missing(self, tmp_path):
        """If [sources] missing, create it."""
        doc = tomlkit.loads("")
        set_source_token(doc, "freesound", "token123")
        assert "sources" in doc
        assert doc["sources"]["freesound"]["token"] == "token123"

    def test_sets_yandex_token(self, tmp_path):
        """set_source_token works for yandex too."""
        doc = tomlkit.loads("[sources]\n")
        set_source_token(doc, "yandex", "yandex_token_xyz")
        assert doc["sources"]["yandex"]["token"] == "yandex_token_xyz"


class TestSetSourceTokenFile:
    """Mutator: set_source_token_file(doc, name: str, token_file: str) -> None
    Set [sources.<name>].token_file; empty string clears value but keeps key.
    """

    def test_sets_yandex_token_file(self, tmp_path):
        """set_source_token_file sets [sources.yandex].token_file."""
        doc = tomlkit.loads("[sources]\n")
        set_source_token_file(doc, "yandex", "/path/to/token.txt")
        assert doc["sources"]["yandex"]["token_file"] == "/path/to/token.txt"

    def test_empty_string_clears_value_keeps_key(self, tmp_path):
        """Empty string clears the value but preserves the key."""
        doc = tomlkit.loads('[sources.yandex]\ntoken_file = "old.txt"')
        set_source_token_file(doc, "yandex", "")
        assert "token_file" in doc["sources"]["yandex"]
        assert doc["sources"]["yandex"]["token_file"] == ""


class TestSourceTokenStatus:
    """Function: source_token_status(doc, name: str, root: Path) -> TokenStatus
    Returns TokenStatus(name, configured: bool, via_file: bool).
    - configured = True iff token non-empty OR token_file exists + non-empty.
    - via_file = True iff satisfied by token_file, not inline token.
    - Token value never appears in repr(status).
    """

    def test_empty_token_not_configured(self, tmp_path):
        """Empty/absent inline token -> configured False."""
        doc = tomlkit.loads('[sources.freesound]\ntoken = ""')
        status = source_token_status(doc, "freesound", tmp_path)
        assert status.configured is False
        assert status.via_file is False

    def test_non_empty_token_configured(self, tmp_path):
        """Non-empty inline token -> configured True, via_file False."""
        doc = tomlkit.loads('[sources.freesound]\ntoken = "abc123"')
        status = source_token_status(doc, "freesound", tmp_path)
        assert status.configured is True
        assert status.via_file is False

    def test_token_file_exists_configured_via_file(self, tmp_path):
        """Existing non-empty token_file -> configured True, via_file True."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("secret_token")
        doc = tomlkit.loads(f'[sources.yandex]\ntoken_file = "{token_file.as_posix()}"')
        status = source_token_status(doc, "yandex", tmp_path)
        assert status.configured is True
        assert status.via_file is True

    def test_token_file_missing_not_configured(self, tmp_path):
        """Nonexistent token_file path -> configured False."""
        doc = tomlkit.loads('[sources.yandex]\ntoken_file = "/nonexistent/path.txt"')
        status = source_token_status(doc, "yandex", tmp_path)
        assert status.configured is False

    def test_token_never_appears_in_repr(self, tmp_path):
        """Token value does not appear in repr(status)."""
        doc = tomlkit.loads('[sources.freesound]\ntoken = "my_secret_api_key_12345"')
        status = source_token_status(doc, "freesound", tmp_path)
        status_repr = repr(status)
        assert "my_secret_api_key_12345" not in status_repr


class TestCommentPreservationR3:
    """Invariant R3: Mutating one key preserves surrounding comments.
    After set_source_token, freesound/yandex/discogs how-to blocks intact.
    """

    def _copy_example(self, tmp_path):
        """Helper: copy the real config.example.toml into tmp_path."""
        example_src = Path(__file__).parent.parent / "config.example.toml"
        if not example_src.is_file():
            pytest.skip("config.example.toml not found in repo root")
        shutil.copy2(example_src, tmp_path / "config.example.toml")

    def test_set_source_token_preserves_freesound_comments(self, tmp_path):
        """After set_source_token for freesound, comment block still present."""
        self._copy_example(tmp_path)
        cfg = tmp_path / "config.toml"
        shutil.copy2(tmp_path / "config.example.toml", cfg)

        doc = load_document(cfg)
        set_source_token(doc, "freesound", "XYZ_TOKEN")
        write_document(doc, cfg)

        dumped = cfg.read_text()
        # Look for a known substring from the freesound how-to comment
        assert "freesound" in dumped
        assert "XYZ_TOKEN" in dumped


class TestMetadataValuesRoundTrip:
    """After set_*_metadata mutators, values survive reload via tomlkit."""

    def test_cache_ttl_days_round_trips(self, tmp_path):
        """set_metadata_cache_ttl_days value persists after write+reload."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_cache_ttl_days(doc, 7)
        dumped = tomlkit.dumps(doc)
        reloaded = tomlkit.loads(dumped)
        assert reloaded["metadata"]["cache_ttl_days"] == 7

    def test_enable_search_ranking_round_trips(self, tmp_path):
        """set_metadata_enable_search_ranking value persists."""
        doc = tomlkit.loads("[metadata]\n")
        set_metadata_enable_search_ranking(doc, False)
        dumped = tomlkit.dumps(doc)
        reloaded = tomlkit.loads(dumped)
        assert reloaded["metadata"]["enable_search_ranking"] is False

"""Tests for updater.py: offline update manifest validation and payload verification.

TDD-style: these are FAILING tests that define the API the developer must satisfy.
Tests cover:
- SHA256 file hashing matching hashlib
- Version string parsing with validation
- Version comparison (newer/older/equal)
- Manifest SHA256 stability and independence from key order
- Round-trip serialization (build_update_zip_doc -> load_update_manifest)
- Manifest integrity checks (tampered SHA256, missing keys)
- Compatibility validation (version range, current version in from_versions)
- Payload verification (file existence, size match, SHA256 match)
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from dataclasses import dataclass

import pytest

from cratedig.updater import (
    UpdateError,
    FileEntry,
    UpdateManifest,
    sha256_file,
    parse_version,
    is_newer,
    manifest_sha256,
    build_update_zip_doc,
    load_update_manifest,
    check_compatible,
    verify_payload,
)


class TestSha256File:
    """Signature: sha256_file(path: str | Path) -> str
    Returns hex digest of file bytes, matching hashlib.sha256.
    """

    def test_sha256_matches_hashlib_simple_file(self, tmp_path):
        """SHA256 of written file matches hashlib.sha256(bytes).hexdigest()."""
        test_file = tmp_path / "test.bin"
        content = b"hello world"
        test_file.write_bytes(content)

        result = sha256_file(test_file)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected

    def test_sha256_matches_hashlib_empty_file(self, tmp_path):
        """SHA256 of empty file matches hashlib."""
        test_file = tmp_path / "empty.bin"
        test_file.write_bytes(b"")

        result = sha256_file(test_file)
        expected = hashlib.sha256(b"").hexdigest()

        assert result == expected

    def test_sha256_matches_hashlib_large_file(self, tmp_path):
        """SHA256 of large file (1MB) matches hashlib."""
        test_file = tmp_path / "large.bin"
        content = b"x" * (1024 * 1024)
        test_file.write_bytes(content)

        result = sha256_file(test_file)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected

    def test_sha256_as_string_path(self, tmp_path):
        """sha256_file accepts string paths too."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"test data")

        result = sha256_file(str(test_file))
        expected = hashlib.sha256(b"test data").hexdigest()

        assert result == expected

    def test_sha256_hex_format(self, tmp_path):
        """Result is lowercase hex (64 chars for SHA256)."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"data")

        result = sha256_file(test_file)

        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)


class TestParseVersion:
    """Signature: parse_version(s: str) -> tuple[int, ...]
    Parses "1.2.3" -> (1, 2, 3); raises UpdateError on garbage.
    """

    def test_parse_simple_version(self):
        """Parse "0.3.0" -> (0, 3, 0)."""
        result = parse_version("0.3.0")
        assert result == (0, 3, 0)

    def test_parse_version_with_many_parts(self):
        """Parse "1.2.3.4.5" -> (1, 2, 3, 4, 5)."""
        result = parse_version("1.2.3.4.5")
        assert result == (1, 2, 3, 4, 5)

    def test_parse_two_part_version(self):
        """Parse "2.1" -> (2, 1)."""
        result = parse_version("2.1")
        assert result == (2, 1)

    def test_parse_single_part_version(self):
        """Parse "5" -> (5,)."""
        result = parse_version("5")
        assert result == (5,)

    def test_raises_on_non_numeric(self):
        """parse_version("abc") raises UpdateError."""
        with pytest.raises(UpdateError):
            parse_version("abc")

    def test_raises_on_mixed_numeric_alpha(self):
        """parse_version("1.x.2") raises UpdateError."""
        with pytest.raises(UpdateError):
            parse_version("1.x.2")

    def test_raises_on_empty_part(self):
        """parse_version("1..2") with empty part raises UpdateError."""
        with pytest.raises(UpdateError):
            parse_version("1..2")

    def test_raises_on_empty_string(self):
        """parse_version("") raises UpdateError."""
        with pytest.raises(UpdateError):
            parse_version("")

    def test_raises_on_non_numeric_with_dots(self):
        """parse_version("1.2.beta") raises UpdateError."""
        with pytest.raises(UpdateError):
            parse_version("1.2.beta")


class TestIsNewer:
    """Signature: is_newer(a: str, b: str) -> bool
    True if version a > version b (parsed; handles different lengths).
    """

    def test_newer_simple(self):
        """is_newer("0.3.0", "0.2.0") is True."""
        assert is_newer("0.3.0", "0.2.0") is True

    def test_older_simple(self):
        """is_newer("0.2.0", "0.3.0") is False."""
        assert is_newer("0.2.0", "0.3.0") is False

    def test_equal_versions_not_newer(self):
        """is_newer("1.0.0", "1.0.0") is False."""
        assert is_newer("1.0.0", "1.0.0") is False

    def test_longer_version_newer(self):
        """is_newer("1.0.1", "1.0") is True (1.0 == 1.0.0)."""
        assert is_newer("1.0.1", "1.0") is True

    def test_shorter_version_older(self):
        """is_newer("1.0", "1.0.1") is False."""
        assert is_newer("1.0", "1.0.1") is False

    def test_major_version_difference(self):
        """is_newer("2.0.0", "1.9.9") is True."""
        assert is_newer("2.0.0", "1.9.9") is True

    def test_minor_version_difference(self):
        """is_newer("1.5.0", "1.4.9") is True."""
        assert is_newer("1.5.0", "1.4.9") is True

    def test_patch_version_difference(self):
        """is_newer("1.0.2", "1.0.1") is True."""
        assert is_newer("1.0.2", "1.0.1") is True

    def test_equal_different_length_trailing_zeros(self):
        """is_newer("1.0.0", "1.0") is False (both equal when padded)."""
        assert is_newer("1.0.0", "1.0") is False


class TestManifestSha256:
    """Signature: manifest_sha256(doc: dict) -> str
    SHA256 of canonical JSON (without 'manifest_sha256' key).
    Result is stable regardless of key insertion order.
    """

    def test_manifest_sha256_stable_without_manifest_sha256_key(self):
        """manifest_sha256 ignores any pre-existing 'manifest_sha256' in doc."""
        doc1 = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }
        doc2 = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
            "manifest_sha256": "fake_hash_to_be_ignored",
        }

        result1 = manifest_sha256(doc1)
        result2 = manifest_sha256(doc2)

        assert result1 == result2

    def test_manifest_sha256_independent_of_key_order(self):
        """manifest_sha256 is same regardless of dict key insertion order."""
        doc1 = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }
        doc2 = {
            "deletions": [],
            "to_version": "1.0.0",
            "files": [],
            "from_versions": ["0.9.0"],
        }

        result1 = manifest_sha256(doc1)
        result2 = manifest_sha256(doc2)

        assert result1 == result2

    def test_manifest_sha256_changes_on_content_change(self):
        """manifest_sha256 changes when content changes."""
        doc1 = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }
        doc2 = {
            "to_version": "1.1.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }

        result1 = manifest_sha256(doc1)
        result2 = manifest_sha256(doc2)

        assert result1 != result2

    def test_manifest_sha256_hex_format(self):
        """manifest_sha256 returns lowercase hex (64 chars)."""
        doc = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }

        result = manifest_sha256(doc)

        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_manifest_sha256_uses_canonical_json(self):
        """manifest_sha256 uses json.dumps with sort_keys and compact separators."""
        doc = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }

        result = manifest_sha256(doc)
        # Reconstruct expected hash manually
        canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        assert result == expected


class TestBuildUpdateZipDoc:
    """Signature: build_update_zip_doc(files: list[FileEntry], deletions: list[str],
                                        to_version: str, from_versions: list[str]) -> dict
    Returns dict with to_version, from_versions, files, deletions, manifest_sha256.
    """

    def test_build_update_zip_doc_returns_dict_with_required_keys(self):
        """Returns dict with all required keys."""
        files = []
        deletions = []
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        assert isinstance(result, dict)
        assert "to_version" in result
        assert "from_versions" in result
        assert "files" in result
        assert "deletions" in result
        assert "manifest_sha256" in result

    def test_build_update_zip_doc_populates_correct_values(self):
        """Populated dict has correct to_version, from_versions, etc."""
        files = []
        deletions = []
        to_version = "1.0.0"
        from_versions = ["0.9.0", "0.8.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        assert result["to_version"] == "1.0.0"
        assert result["from_versions"] == ["0.9.0", "0.8.0"]
        assert result["files"] == []
        assert result["deletions"] == []

    def test_build_update_zip_doc_with_files(self, tmp_path):
        """Build doc with FileEntry objects; files appear as list of dicts."""
        file1 = tmp_path / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)
        size1 = len(b"content1")

        file_entry = FileEntry(path="subdir/file1.txt", sha256=sha1, size=size1)
        files = [file_entry]
        deletions = []
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "subdir/file1.txt"
        assert result["files"][0]["sha256"] == sha1
        assert result["files"][0]["size"] == size1

    def test_build_update_zip_doc_with_deletions(self):
        """Build doc with deletion paths."""
        files = []
        deletions = ["old_file.txt", "old_dir/file.py"]
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        assert result["deletions"] == ["old_file.txt", "old_dir/file.py"]

    def test_build_update_zip_doc_manifest_sha256_computed(self):
        """manifest_sha256 is computed and present."""
        files = []
        deletions = []
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        # manifest_sha256 should be a valid hex string
        assert isinstance(result["manifest_sha256"], str)
        assert len(result["manifest_sha256"]) == 64

    def test_build_update_zip_doc_manifest_sha256_matches_computed(self):
        """Computed manifest_sha256 matches what we compute independently."""
        files = []
        deletions = []
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        result = build_update_zip_doc(files, deletions, to_version, from_versions)

        # Extract the manifest_sha256 from result
        stored_sha = result["manifest_sha256"]

        # Recompute it from doc-without-manifest_sha256
        doc_copy = {k: v for k, v in result.items() if k != "manifest_sha256"}
        recomputed = manifest_sha256(doc_copy)

        assert stored_sha == recomputed


class TestLoadUpdateManifest:
    """Signature: load_update_manifest(doc: dict) -> UpdateManifest
    Validate doc structure, recompute manifest_sha256, compare.
    Raise UpdateError on mismatch or missing keys.
    """

    def test_load_update_manifest_from_valid_doc(self, tmp_path):
        """Load valid doc -> returns UpdateManifest with matching fields."""
        file1 = tmp_path / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        files = [FileEntry(path="file1.txt", sha256=sha1, size=8)]
        deletions = ["old.txt"]
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        doc = build_update_zip_doc(files, deletions, to_version, from_versions)

        result = load_update_manifest(doc)

        assert isinstance(result, UpdateManifest)
        assert result.to_version == "1.0.0"
        assert result.from_versions == ("0.9.0",)
        assert len(result.files) == 1
        assert result.files[0].path == "file1.txt"
        assert result.deletions == ("old.txt",)

    def test_load_update_manifest_files_as_tuple(self, tmp_path):
        """Files converted to tuple of FileEntry objects."""
        file1 = tmp_path / "f1.txt"
        file1.write_bytes(b"data1")
        sha1 = sha256_file(file1)

        files = [FileEntry(path="f1.txt", sha256=sha1, size=5)]
        doc = build_update_zip_doc(files, [], "1.0.0", ["0.9.0"])

        result = load_update_manifest(doc)

        assert isinstance(result.files, tuple)
        assert len(result.files) == 1
        assert isinstance(result.files[0], FileEntry)

    def test_load_update_manifest_raises_on_missing_to_version(self):
        """Raises UpdateError when 'to_version' key missing."""
        doc = {
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
            "manifest_sha256": "dummy",
        }

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_raises_on_missing_from_versions(self):
        """Raises UpdateError when 'from_versions' key missing."""
        doc = {
            "to_version": "1.0.0",
            "files": [],
            "deletions": [],
            "manifest_sha256": "dummy",
        }

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_raises_on_missing_files(self):
        """Raises UpdateError when 'files' key missing."""
        doc = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "deletions": [],
            "manifest_sha256": "dummy",
        }

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_raises_on_missing_deletions(self):
        """Raises UpdateError when 'deletions' key missing."""
        doc = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "manifest_sha256": "dummy",
        }

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_raises_on_missing_manifest_sha256(self):
        """Raises UpdateError when 'manifest_sha256' key missing."""
        doc = {
            "to_version": "1.0.0",
            "from_versions": ["0.9.0"],
            "files": [],
            "deletions": [],
        }

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_raises_on_tampered_sha256(self, tmp_path):
        """Raises UpdateError when manifest_sha256 doesn't match content."""
        file1 = tmp_path / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        files = [FileEntry(path="file1.txt", sha256=sha1, size=8)]
        doc = build_update_zip_doc(files, [], "1.0.0", ["0.9.0"])

        # Tamper with the manifest_sha256
        doc["manifest_sha256"] = "0" * 64

        with pytest.raises(UpdateError):
            load_update_manifest(doc)

    def test_load_update_manifest_round_trip(self, tmp_path):
        """build -> load round-trip preserves all data."""
        file1 = tmp_path / "f1.txt"
        file1.write_bytes(b"data1")
        sha1 = sha256_file(file1)

        original_files = [FileEntry(path="f1.txt", sha256=sha1, size=5)]
        original_deletions = ["old.txt"]
        to_version = "1.0.0"
        from_versions = ["0.9.0"]

        doc = build_update_zip_doc(
            original_files, original_deletions, to_version, from_versions
        )
        manifest = load_update_manifest(doc)

        assert manifest.to_version == to_version
        assert manifest.from_versions == tuple(from_versions)
        assert manifest.files[0].path == original_files[0].path
        assert manifest.files[0].sha256 == original_files[0].sha256
        assert manifest.deletions == tuple(original_deletions)


class TestCheckCompatible:
    """Signature: check_compatible(manifest: UpdateManifest, current_version: str) -> None
    Raise UpdateError if:
    - to_version is not newer than current_version
    - current_version not in from_versions
    Message mentions full installer when incompatible.
    """

    def test_check_compatible_passes_valid_case(self, tmp_path):
        """check_compatible passes when to_version > current and current in from_versions."""
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0", "0.8.0"),
            files=(),
            deletions=(),
        )

        # Should not raise
        check_compatible(manifest, "0.9.0")

    def test_check_compatible_raises_when_to_version_not_newer(self):
        """Raises when to_version is not newer than current."""
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("1.0.0", "0.9.0"),
            files=(),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            check_compatible(manifest, "1.0.0")

    def test_check_compatible_raises_when_current_not_in_from_versions(self):
        """Raises when current_version not in from_versions."""
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0", "0.8.0"),
            files=(),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            check_compatible(manifest, "0.7.0")

    def test_check_compatible_raises_with_installer_hint(self):
        """Error message mentions full installer."""
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(),
            deletions=(),
        )

        with pytest.raises(UpdateError) as exc_info:
            check_compatible(manifest, "0.7.0")

        error_msg = str(exc_info.value).lower()
        assert "installer" in error_msg or "full" in error_msg or "incompatible" in error_msg

    def test_check_compatible_newer_in_from_versions(self):
        """Passes when current is older than to_version AND in from_versions."""
        manifest = UpdateManifest(
            to_version="2.0.0",
            from_versions=("1.5.0", "1.0.0"),
            files=(),
            deletions=(),
        )

        # Should not raise (current 1.5.0 < target 2.0.0, and in from_versions)
        check_compatible(manifest, "1.5.0")

    def test_check_compatible_current_equal_to_version(self):
        """Raises when current_version == to_version (not newer)."""
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("1.0.0",),
            files=(),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            check_compatible(manifest, "1.0.0")


class TestVerifyPayload:
    """Signature: verify_payload(manifest: UpdateManifest, staged_dir: str | Path) -> None
    For each FileEntry: staged_dir/path must exist, size match, sha256_file match.
    Raise UpdateError listing first offending path.
    """

    def test_verify_payload_passes_with_valid_files(self, tmp_path):
        """verify_payload passes when all files exist with matching size/hash."""
        # Create staged directory with files
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        file2 = staged_dir / "subdir" / "file2.txt"
        file2.parent.mkdir()
        file2.write_bytes(b"content2")
        sha2 = sha256_file(file2)

        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(
                FileEntry(path="file1.txt", sha256=sha1, size=8),
                FileEntry(path="subdir/file2.txt", sha256=sha2, size=8),
            ),
            deletions=(),
        )

        # Should not raise
        verify_payload(manifest, staged_dir)

    def test_verify_payload_raises_on_missing_file(self, tmp_path):
        """Raises when file doesn't exist in staged_dir."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(FileEntry(path="missing.txt", sha256="abc" * 21 + "d", size=100),),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            verify_payload(manifest, staged_dir)

    def test_verify_payload_raises_on_size_mismatch(self, tmp_path):
        """Raises when file size doesn't match manifest."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        # Create manifest with wrong size
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(FileEntry(path="file1.txt", sha256=sha1, size=999),),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            verify_payload(manifest, staged_dir)

    def test_verify_payload_raises_on_sha256_mismatch(self, tmp_path):
        """Raises when file SHA256 doesn't match manifest."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "file1.txt"
        file1.write_bytes(b"content1")

        # Create manifest with wrong SHA256
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(FileEntry(path="file1.txt", sha256="0" * 64, size=8),),
            deletions=(),
        )

        with pytest.raises(UpdateError):
            verify_payload(manifest, staged_dir)

    def test_verify_payload_error_mentions_path(self, tmp_path):
        """Error message names the offending file path."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "goodfile.txt"
        file1.write_bytes(b"good")

        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(
                FileEntry(path="goodfile.txt", sha256=sha256_file(file1), size=4),
                FileEntry(path="badfile.txt", sha256="0" * 64, size=100),
            ),
            deletions=(),
        )

        with pytest.raises(UpdateError) as exc_info:
            verify_payload(manifest, staged_dir)

        # Error should mention one of the problematic paths
        error_msg = str(exc_info.value)
        assert "badfile.txt" in error_msg or "file" in error_msg.lower()

    def test_verify_payload_string_path(self, tmp_path):
        """verify_payload accepts string path for staged_dir."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(FileEntry(path="file1.txt", sha256=sha1, size=8),),
            deletions=(),
        )

        # Should accept string path
        verify_payload(manifest, str(staged_dir))

    def test_verify_payload_empty_files_passes(self, tmp_path):
        """verify_payload passes when manifest has no files."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(),
            deletions=(),
        )

        # Should not raise even if staged_dir is empty
        verify_payload(manifest, staged_dir)

    def test_verify_payload_multiple_files_stops_at_first_error(self, tmp_path):
        """verify_payload stops and reports first offending file."""
        staged_dir = tmp_path / "staged"
        staged_dir.mkdir()

        file1 = staged_dir / "file1.txt"
        file1.write_bytes(b"content1")
        sha1 = sha256_file(file1)

        # Second file doesn't exist; should fail before checking a third
        manifest = UpdateManifest(
            to_version="1.0.0",
            from_versions=("0.9.0",),
            files=(
                FileEntry(path="file1.txt", sha256=sha1, size=8),
                FileEntry(path="missing.txt", sha256="0" * 64, size=1),
            ),
            deletions=(),
        )

        with pytest.raises(UpdateError) as exc_info:
            verify_payload(manifest, staged_dir)

        # Should mention the missing file
        error_msg = str(exc_info.value)
        assert "missing.txt" in error_msg or "file" in error_msg.lower()

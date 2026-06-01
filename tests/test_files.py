"""Tests for cratedig.files module - file manipulation operations."""

from pathlib import Path

import pytest

from cratedig.files import rename_file, move_file, trash_file


class TestRenameFile:
    """Test rename_file(old_path, new_name) -> str."""

    def test_rename_file_basic(self, tmp_path):
        """Rename a file in its current directory."""
        file = tmp_path / "original.txt"
        file.write_text("content")

        new_path = rename_file(str(file), "renamed")

        assert Path(new_path).exists()
        assert not file.exists()
        assert Path(new_path).read_text() == "content"
        assert str(new_path).endswith("renamed.txt")

    def test_rename_file_returns_absolute_path_string(self, tmp_path):
        """Result should be an absolute path string."""
        file = tmp_path / "original.txt"
        file.write_text("data")

        result = rename_file(str(file), "renamed.txt")

        assert isinstance(result, str)
        assert Path(result).is_absolute()

    def test_rename_file_preserves_directory(self, tmp_path):
        """File stays in the same directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        file = subdir / "original.txt"
        file.write_text("data")

        result = rename_file(str(file), "renamed.txt")

        assert Path(result).parent == subdir
        assert Path(result).exists()

    def test_rename_file_with_path_object(self, tmp_path):
        """Also works with Path objects as input."""
        file = tmp_path / "original.txt"
        file.write_text("data")

        new_path = rename_file(file, "renamed.txt")

        assert Path(new_path).exists()
        assert not file.exists()

    def test_rename_file_preserves_original_extension(self, tmp_path):
        """Rename changes only the filename stem."""
        file = tmp_path / "document.txt"
        file.write_text("data")

        result = rename_file(str(file), "report.txt")

        assert Path(result).name == "report.txt"
        assert Path(result).suffix == ".txt"
        assert Path(result).exists()
        assert not file.exists()

    def test_rename_file_preserves_extension_with_new_stem(self, tmp_path):
        """A new stem is combined with the source extension."""
        file = tmp_path / "document.txt"
        file.write_text("data")

        result = rename_file(str(file), "renamed")

        assert Path(result).name == "renamed.txt"
        assert Path(result).exists()
        assert not file.exists()

    def test_rename_file_allows_dots_in_new_stem(self, tmp_path):
        """Dots inside the new stem are preserved."""
        file = tmp_path / "document.txt"
        file.write_text("data")

        result = rename_file(str(file), "renamed.v2")

        assert Path(result).name == "renamed.v2.txt"
        assert Path(result).exists()
        assert not file.exists()


class TestMoveFile:
    """Test move_file(old_path, dest_dir) -> str."""

    def test_move_file_to_existing_directory(self, tmp_path):
        """Move file to an existing directory."""
        source = tmp_path / "file.txt"
        source.write_text("content")
        dest_dir = tmp_path / "subdir"
        dest_dir.mkdir()

        result = move_file(str(source), str(dest_dir))

        assert Path(result).exists()
        assert not source.exists()
        assert Path(result).parent == dest_dir
        assert Path(result).name == "file.txt"

    def test_move_file_creates_missing_directory(self, tmp_path):
        """Create dest_dir if it doesn't exist."""
        source = tmp_path / "file.txt"
        source.write_text("content")
        dest_dir = tmp_path / "new_dir"

        result = move_file(str(source), str(dest_dir))

        assert Path(result).exists()
        assert not source.exists()
        assert dest_dir.exists()

    def test_move_file_returns_absolute_path_string(self, tmp_path):
        """Result should be an absolute path string."""
        source = tmp_path / "file.txt"
        source.write_text("data")
        dest_dir = tmp_path / "subdir"

        result = move_file(str(source), str(dest_dir))

        assert isinstance(result, str)
        assert Path(result).is_absolute()

    def test_move_file_preserves_filename(self, tmp_path):
        """Filename should remain the same in destination."""
        source = tmp_path / "document.txt"
        source.write_text("data")
        dest_dir = tmp_path / "archive"

        result = move_file(str(source), str(dest_dir))

        assert Path(result).name == "document.txt"
        assert Path(result).exists()

    def test_move_file_preserves_content(self, tmp_path):
        """File content should be unchanged."""
        content = "important data"
        source = tmp_path / "file.txt"
        source.write_text(content)
        dest_dir = tmp_path / "new_location"

        result = move_file(str(source), str(dest_dir))

        assert Path(result).read_text() == content

    def test_move_file_with_path_object(self, tmp_path):
        """Also works with Path objects as input."""
        source = tmp_path / "file.txt"
        source.write_text("data")
        dest_dir = tmp_path / "subdir"

        result = move_file(source, dest_dir)

        assert Path(result).exists()
        assert not source.exists()


class TestTrashFile:
    """Test trash_file(path) -> None using monkeypatched send2trash."""

    def test_trash_file_calls_send2trash(self, tmp_path, monkeypatch):
        """Verify that send2trash is called with the correct path."""
        file = tmp_path / "to_delete.txt"
        file.write_text("data")

        # Track calls to send2trash
        calls = []
        def fake_send2trash(path):
            calls.append(path)

        # Monkeypatch the lazy import point (module-level symbol)
        monkeypatch.setattr("cratedig.files.send2trash", fake_send2trash)

        trash_file(str(file))

        # Verify send2trash was called with the file path
        assert len(calls) == 1
        assert calls[0] == str(file)

    def test_trash_file_with_path_object(self, tmp_path, monkeypatch):
        """Also accepts Path objects."""
        file = tmp_path / "to_delete.txt"
        file.write_text("data")

        calls = []
        def fake_send2trash(path):
            calls.append(path)

        monkeypatch.setattr("cratedig.files.send2trash", fake_send2trash)

        trash_file(file)

        assert len(calls) == 1

    def test_trash_file_returns_none(self, tmp_path, monkeypatch):
        """Function should return None."""
        file = tmp_path / "to_delete.txt"
        file.write_text("data")

        monkeypatch.setattr("cratedig.files.send2trash", lambda p: None)

        result = trash_file(str(file))

        assert result is None

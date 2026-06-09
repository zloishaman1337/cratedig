"""Tests for Internet Archive downloader backend."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cratedig.sources.archive import ArchiveDownloader
from cratedig.sources.base import DownloadRequest, DownloadResult


class TestArchiveDownloaderAvailable:
    """Test ArchiveDownloader.available() behavior."""

    def test_available_returns_true_when_internetarchive_present(self, monkeypatch):
        """available() returns True when internetarchive module can be imported."""
        # Inject a mock module to simulate internetarchive being available
        monkeypatch.setitem(sys.modules, "internetarchive", MagicMock())

        downloader = ArchiveDownloader({})
        result = downloader.available()
        assert result is True

    def test_available_returns_false_when_import_fails(self, monkeypatch):
        """available() returns False when internetarchive import raises ImportError."""
        # Remove internetarchive from sys.modules if present
        if "internetarchive" in sys.modules:
            monkeypatch.delitem(sys.modules, "internetarchive")

        # Patch the import mechanism to raise ImportError for internetarchive
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "internetarchive":
                raise ImportError("Mock: internetarchive not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        downloader = ArchiveDownloader({})
        result = downloader.available()
        assert result is False


class TestArchiveDownloaderFetch:
    """Test ArchiveDownloader.fetch() behavior."""

    def _mock_ia_module(self, monkeypatch, search_items_return=None, get_item_func=None):
        """Helper: inject mocked internetarchive module into cratedig.sources.archive."""
        mock_ia = MagicMock()

        if search_items_return is not None:
            mock_ia.search_items.return_value = search_items_return

        if get_item_func is not None:
            mock_ia.get_item = get_item_func

        monkeypatch.setitem(sys.modules, "internetarchive", mock_ia)
        return mock_ia

    def test_fetch_no_search_results_returns_ok_false(self, tmp_path, monkeypatch):
        """fetch() with search query yielding no results returns DownloadResult(ok=False, error contains 'no results')."""
        self._mock_ia_module(monkeypatch, search_items_return=[])

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="nonexistent query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is False
        assert result.source == "archive"
        assert "no results" in result.error.lower()

    def test_fetch_happy_path_with_mp3_file(self, tmp_path, monkeypatch):
        """fetch() happy path: mock ia.search_items and ia.get_item, returns ok=True with path and source_url."""
        # Setup search results
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "test_identifier"}],
        )

        # Setup get_item to return a mock item with files
        mock_item = MagicMock()
        mock_item.files = [
            {"name": "track.mp3"},
        ]
        mock_item.download.return_value = None

        mock_ia.get_item.return_value = mock_item

        # Create the audio file so is_file() returns True
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3 data")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="test query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is True
        assert result.source == "archive"
        assert result.path == audio_file
        assert "test_identifier" in result.source_url
        assert result.title == "test_identifier"
        mock_item.download.assert_called_once()

    def test_fetch_happy_path_with_flac_file(self, tmp_path, monkeypatch):
        """fetch() happy path: works with .flac files."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "flac_identifier"}],
        )

        mock_item = MagicMock()
        mock_item.files = [
            {"name": "audio.flac"},
        ]
        mock_item.download.return_value = None
        mock_ia.get_item.return_value = mock_item

        audio_file = tmp_path / "audio.flac"
        audio_file.write_bytes(b"fake flac data")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="test query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is True
        assert result.path == audio_file

    def test_fetch_url_mode_extracts_identifier_from_url(self, tmp_path, monkeypatch):
        """fetch() in URL mode extracts identifier from URL path."""
        mock_ia = self._mock_ia_module(monkeypatch)

        mock_item = MagicMock()
        mock_item.files = [{"name": "audio.mp3"}]
        mock_item.download.return_value = None
        mock_ia.get_item.return_value = mock_item

        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake mp3")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(
            query="https://archive.org/details/my_identifier/",
            dest_dir=tmp_path,
            is_url=True,
        )
        result = downloader.fetch(req)

        assert result.ok is True
        mock_ia.get_item.assert_called_once_with("my_identifier")

    def test_fetch_item_has_no_audio_files(self, tmp_path, monkeypatch):
        """fetch() where item has files but none are audio → ok=False, error 'item has no audio file'."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "no_audio_item"}],
        )

        mock_item = MagicMock()
        mock_item.files = [
            {"name": "readme.txt"},
            {"name": "image.jpg"},
            {"name": "document.pdf"},
        ]
        mock_ia.get_item.return_value = mock_item

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="no audio", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is False
        assert result.source == "archive"
        assert "no audio file" in result.error.lower()

    def test_fetch_get_item_raises_exception(self, tmp_path, monkeypatch):
        """fetch() where ia.get_item() raises exception → ok=False, error non-empty (NOT propagated)."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "bad_item"}],
        )

        # Make get_item raise an exception
        mock_ia.get_item.side_effect = RuntimeError("Item not found on server")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="bad query", dest_dir=tmp_path)

        # This should NOT raise; it should catch and return ok=False
        result = downloader.fetch(req)

        assert result.ok is False
        assert result.source == "archive"
        assert result.error is not None
        assert len(result.error) > 0

    def test_fetch_search_items_raises_exception(self, tmp_path, monkeypatch):
        """fetch() where ia.search_items() raises exception → ok=False, error caught (NOT propagated)."""
        mock_ia = MagicMock()
        mock_ia.search_items.side_effect = RuntimeError("Network error during search")
        monkeypatch.setitem(sys.modules, "internetarchive", mock_ia)

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="query", dest_dir=tmp_path)

        # This should NOT raise; it should catch and return ok=False
        result = downloader.fetch(req)

        assert result.ok is False
        assert result.source == "archive"
        assert result.error is not None

    def test_fetch_files_as_generator_not_list(self, tmp_path, monkeypatch):
        """fetch() where item.files is a generator (not a list) → still works without exhaustion bug."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "gen_item"}],
        )

        mock_item = MagicMock()

        # Create a generator instead of a list
        def file_generator():
            yield {"name": "audio.mp3"}

        mock_item.files = file_generator()
        mock_item.download.return_value = None
        mock_ia.get_item.return_value = mock_item

        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake mp3")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="gen query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is True
        assert result.path == audio_file

    def test_fetch_item_download_raises_exception(self, tmp_path, monkeypatch):
        """fetch() where item.download() raises exception → ok=False, error caught (NOT propagated)."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "download_fail"}],
        )

        mock_item = MagicMock()
        mock_item.files = [{"name": "audio.mp3"}]
        mock_item.download.side_effect = IOError("Download failed: permission denied")
        mock_ia.get_item.return_value = mock_item

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="query", dest_dir=tmp_path)

        # This should NOT raise; it should catch and return ok=False
        result = downloader.fetch(req)

        assert result.ok is False
        assert result.source == "archive"
        assert result.error is not None

    def test_fetch_first_audio_file_picked_when_multiple_exist(self, tmp_path, monkeypatch):
        """fetch() with multiple audio files picks the first one."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "multi_audio"}],
        )

        mock_item = MagicMock()
        mock_item.files = [
            {"name": "intro.mp3"},
            {"name": "main_track.flac"},
            {"name": "outro.wav"},
        ]
        mock_item.download.return_value = None
        mock_ia.get_item.return_value = mock_item

        audio_file = tmp_path / "intro.mp3"
        audio_file.write_bytes(b"fake mp3")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="multi query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is True
        assert result.path == audio_file
        # Verify download was called with the first audio file
        mock_item.download.assert_called_once()
        call_kwargs = mock_item.download.call_args[1]
        assert call_kwargs["files"] == ["intro.mp3"]

    def test_fetch_audio_extensions_case_insensitive(self, tmp_path, monkeypatch):
        """fetch() recognizes audio extensions regardless of case."""
        mock_ia = self._mock_ia_module(
            monkeypatch,
            search_items_return=[{"identifier": "case_test"}],
        )

        mock_item = MagicMock()
        mock_item.files = [
            {"name": "SONG.MP3"},  # uppercase
            {"name": "other.PDF"},
        ]
        mock_item.download.return_value = None
        mock_ia.get_item.return_value = mock_item

        audio_file = tmp_path / "SONG.MP3"
        audio_file.write_bytes(b"fake mp3")

        downloader = ArchiveDownloader({})
        req = DownloadRequest(query="query", dest_dir=tmp_path)
        result = downloader.fetch(req)

        assert result.ok is True
        assert result.path == audio_file

"""Tests for cratedig.gui.platform_files module - cross-platform file reveal."""

import os
import sys
import pytest

from cratedig.gui.platform_files import reveal_in_file_manager


class TestRevealInFileManagerWindows:
    """Test reveal_in_file_manager on Windows (sys.platform == "win32")."""

    def test_windows_uses_explorer_with_select_flag(self, monkeypatch):
        """On Windows, should call subprocess.run with explorer /select, command string."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        reveal_in_file_manager("C:\\Users\\test\\file.txt")

        assert len(calls) == 1
        cmd = calls[0]
        assert isinstance(cmd, str)
        assert "explorer" in cmd.lower()
        assert "/select," in cmd
        assert "C:\\Users\\test\\file.txt" in cmd

    def test_windows_normalizes_path(self, monkeypatch):
        """On Windows, path should be normalized via os.path.normpath(os.path.abspath())."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        # Use a relative path to test normalization
        reveal_in_file_manager("./subdir/./file.txt")

        assert len(calls) == 1
        cmd = calls[0]
        # The normalized absolute path should be in the command
        assert "/select," in cmd
        # Should not contain "./" after normalization
        assert "./" not in cmd

    def test_windows_quotes_path_with_spaces(self, monkeypatch):
        """On Windows, path with spaces should be quoted in the command string."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        reveal_in_file_manager("C:\\My Documents\\my file.wav")

        assert len(calls) == 1
        cmd = calls[0]
        assert '"' in cmd
        assert "My Documents" in cmd or "my file.wav" in cmd

    def test_windows_exception_swallowed(self, monkeypatch):
        """On Windows, if subprocess.run raises, exception should be swallowed."""
        def fake_run(cmd, **kwargs):
            raise OSError("Subprocess failed")

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        # Should not raise
        reveal_in_file_manager("C:\\test.txt")


class TestRevealInFileManagerMacOS:
    """Test reveal_in_file_manager on macOS (sys.platform == "darwin")."""

    def test_macos_uses_open_with_reveal_flag(self, monkeypatch):
        """On macOS, should call subprocess.Popen with ["open", "-R", path]."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        reveal_in_file_manager("/Users/test/file.wav")

        assert len(calls) == 1
        argv = calls[0]
        assert isinstance(argv, list)
        assert argv[0] == "open"
        assert argv[1] == "-R"
        # macOS reveals the FILE itself (host-OS-agnostic: normpath/abspath
        # mangles POSIX separators when the test runs on Windows)
        assert argv[2].replace("\\", "/").endswith("file.wav")

    def test_macos_normalizes_path(self, monkeypatch):
        """On macOS, path should be normalized via os.path.normpath(os.path.abspath())."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        # Use a relative path with ./ to test normalization
        reveal_in_file_manager("./test/./file.wav")

        assert len(calls) == 1
        argv = calls[0]
        # Should not contain "./" after normalization
        assert "./" not in argv[2]
        assert os.path.isabs(argv[2])

    def test_macos_exception_swallowed(self, monkeypatch):
        """On macOS, if subprocess.Popen raises, exception should be swallowed."""
        def fake_popen(argv, **kwargs):
            raise OSError("Popen failed")

        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        # Should not raise
        reveal_in_file_manager("/Users/test/file.wav")


class TestRevealInFileManagerLinux:
    """Test reveal_in_file_manager on Linux and other platforms."""

    def test_linux_uses_xdg_open_with_directory(self, monkeypatch):
        """On Linux, should call subprocess.Popen with ["xdg-open", dirname(path)]."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        reveal_in_file_manager("/home/user/samples/kick.wav")

        assert len(calls) == 1
        argv = calls[0]
        assert isinstance(argv, list)
        assert argv[0] == "xdg-open"
        # Should pass the directory, not the file (host-OS-agnostic compare)
        norm = argv[1].replace("\\", "/")
        assert norm.endswith("/samples")
        assert not norm.endswith("kick.wav")

    def test_linux_extracts_dirname_from_normalized_path(self, monkeypatch):
        """On Linux, dirname should be extracted from the normalized path."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        # Use a relative path with redundant directories
        reveal_in_file_manager("./music/./drums/kick.wav")

        assert len(calls) == 1
        argv = calls[0]
        # The dirname should be normalized and absolute
        dirname = argv[1]
        assert os.path.isabs(dirname)
        assert "./" not in dirname

    def test_linux_exception_swallowed(self, monkeypatch):
        """On Linux, if subprocess.Popen raises, exception should be swallowed."""
        def fake_popen(argv, **kwargs):
            raise OSError("Popen failed")

        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        # Should not raise
        reveal_in_file_manager("/home/user/file.wav")

    def test_freebsd_uses_xdg_open(self, monkeypatch):
        """On other platforms (e.g., FreeBSD), should use xdg-open as fallback."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "freebsd11")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        reveal_in_file_manager("/home/user/file.txt")

        assert len(calls) == 1
        argv = calls[0]
        assert argv[0] == "xdg-open"


class TestRevealInFileManagerEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_path_string(self, monkeypatch):
        """An empty path string should still be processed (normalized to current dir)."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        # Empty string should normalize to current working directory
        reveal_in_file_manager("")

        # Should call subprocess, not raise
        assert len(calls) == 1

    def test_path_with_unicode_characters(self, monkeypatch):
        """Paths with unicode characters should be handled correctly."""
        calls = []

        class FakeProc:
            pass

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return FakeProc()

        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.Popen", fake_popen)

        reveal_in_file_manager("/Users/test/Ñoño_Café.wav")

        assert len(calls) == 1
        argv = calls[0]
        assert "Ñoño_Café.wav" in argv[2]

    def test_nonexistent_path_still_processed(self, monkeypatch):
        """A path to a non-existent file should still be revealed (OS handles it)."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        reveal_in_file_manager("C:\\nonexistent\\fake\\path\\file.wav")

        # Should still attempt to reveal, even if path doesn't exist
        assert len(calls) == 1

    def test_multiple_calls_independent(self, monkeypatch):
        """Multiple calls to reveal_in_file_manager should be independent."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("cratedig.gui.platform_files.subprocess.run", fake_run)

        reveal_in_file_manager("C:\\file1.wav")
        reveal_in_file_manager("C:\\file2.wav")

        assert len(calls) == 2
        assert "file1.wav" in calls[0]
        assert "file2.wav" in calls[1]

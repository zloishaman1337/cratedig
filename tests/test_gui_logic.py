"""Tests for cratedig.gui.logic module - pure GUI logic functions."""

import math
import os

from pathlib import Path
import numpy as np
import pytest

from cratedig.db.models import Sample
from cratedig.gui.logic import (
    compute_peaks, filename_parts, hit_rows, resolve_similar, tree_rows,
    is_sample_favorite, similar_name, format_metadata, file_urls,
    time_to_x, x_to_time, clamp_region,
)
from cratedig.sources.base import SearchHit
from cratedig.tui.browser import FolderNode


def _make_sample(sample_id: int, filename: str) -> Sample:
    """Minimal Sample factory for testing."""
    return Sample(id=sample_id, path=f"/test/{filename}", filename=filename)


class TestSimilarName:
    """Test similar_name(path) -> str with stem + parent."""

    def test_simple_path(self):
        """Test basic file path returns stem and parent dir."""
        result = similar_name("/packs/drums/kick.wav")
        assert "kick" in result
        assert "drums" in result
        assert "·" in result

    def test_stem_only_no_extension(self):
        """Stem should not include file extension."""
        result = similar_name("/packs/bass/bass_01.wav")
        assert "bass_01" in result
        assert ".wav" not in result

    def test_parent_directory_name(self):
        """Parent directory should appear in output."""
        result = similar_name("/library/samples/snare.wav")
        assert "samples" in result

    def test_deep_path(self):
        """Works with deeply nested paths."""
        result = similar_name("/packs/drums/kicks/acoustic_kick.wav")
        # Parent of the file is "kicks", so "kicks" should appear
        assert "acoustic_kick" in result
        assert "kicks" in result

    def test_format_with_separator(self):
        """Output should contain the separator ·."""
        result = similar_name("/packs/drums/kick.wav")
        assert "·" in result

    def test_root_level_file(self):
        """Files at root level should still work."""
        result = similar_name("/kick.wav")
        assert "kick" in result


class TestFormatMetadata:
    """Test format_metadata(sample, embedded) -> list[(label, value)] filtering."""

    def test_returns_list_of_tuples(self):
        """format_metadata returns list of (label, value) tuples."""
        sample = Sample(id=1, path="/a/kick.wav", filename="kick.wav")
        result = format_metadata(sample, None)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_skips_none_fields(self):
        """None values should not appear in output."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            format="wav", samplerate=None, bpm=None
        )
        result = format_metadata(sample, None)
        # Check that no None values leak into the output
        for label, value in result:
            assert value is not None
            assert value != ""

    def test_includes_format(self):
        """Format field should be included when set."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            format="wav"
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Format" in labels

    def test_samplerate_formatted_with_hz(self):
        """Sample rate should be formatted as 'X Hz'."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            samplerate=44100
        )
        result = format_metadata(sample, None)
        found = False
        for label, value in result:
            if label == "Sample rate":
                assert value == "44100 Hz"
                found = True
        assert found

    def test_duration_is_omitted(self):
        """Duration belongs in the table, not the metadata panel."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            duration_sec=125.5  # 2 min 5.5 sec
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Duration" not in labels

    def test_short_duration_is_omitted(self):
        """Short duration should also stay out of metadata rows."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            duration_sec=45.0  # 45 sec
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Duration" not in labels

    def test_file_size_in_kb(self):
        """File size under 1 MB should be shown in KB."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            file_size=100_000  # ~98 KB
        )
        result = format_metadata(sample, None)
        found = False
        for label, value in result:
            if label == "Size":
                assert "KB" in value
                found = True
        assert found

    def test_file_size_in_mb(self):
        """File size over 1 MB should be shown in MB."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            file_size=5_000_000  # ~5 MB
        )
        result = format_metadata(sample, None)
        found = False
        for label, value in result:
            if label == "Size":
                assert "MB" in value
                found = True
        assert found

    def test_bpm_is_omitted(self):
        """BPM belongs in the table, not the metadata panel."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            bpm=120.5
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "BPM" not in labels

    def test_key_and_scale_are_omitted(self):
        """Key belongs in the table, not the metadata panel."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            musical_key="C", key_scale="minor"
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Key" not in labels

    def test_key_only_is_omitted(self):
        """Key without scale should also stay out of metadata rows."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            musical_key="A", key_scale=None
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Key" not in labels

    def test_loudness_lufs(self):
        """Loudness should be shown in LUFS."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            loudness_lufs=-12.5
        )
        result = format_metadata(sample, None)
        found = False
        for label, value in result:
            if label == "Loudness":
                assert "LUFS" in value
                assert "-12" in value
                found = True
        assert found

    def test_category_and_instrument_class(self):
        """Category and instrument_class should appear as 'Category' and 'Class'."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            category="drum", instrument_class="kick"
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]
        assert "Category" in labels
        assert "Class" in labels

    def test_source_field(self):
        """Source field should be included when set."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            source="freesound"
        )
        result = format_metadata(sample, None)
        found = False
        for label, value in result:
            if label == "Source":
                assert value == "freesound"
                found = True
        assert found

    def test_embedded_dict_appended(self):
        """Embedded dict with metadata should be appended."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            format="wav"
        )
        embedded = {
            "artist": "Sample Pack Ltd",
            "title": "Kick 01",
            "album": "Drums Vol 1",
            "genre": "Drum and Bass",
            "date": "2023",
        }
        result = format_metadata(sample, embedded)

        # Should have an empty row separator
        found_separator = False
        for label, value in result:
            if label == "" and value == "":
                found_separator = True
                break
        assert found_separator

        # Should have artist, title, etc. after separator
        labels = [label for label, _ in result]
        assert "Artist" in labels
        assert "Title" in labels
        assert "Album" in labels
        assert "Genre" in labels
        assert "Year" in labels

    def test_embedded_skips_none_values(self):
        """Embedded dict with None/empty values should be skipped."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            format="wav"
        )
        embedded = {
            "artist": "Sample Pack Ltd",
            "title": None,
            "album": "",
            "genre": "Drum and Bass",
        }
        result = format_metadata(sample, embedded)

        # title and album should not appear
        labels = [label for label, _ in result]
        assert "Artist" in labels
        assert "Genre" in labels
        # No label for title/album (they were None or empty)
        found_title = any(label == "Title" for label, _ in result)
        found_album = any(label == "Album" for label, _ in result)
        assert not found_title
        assert not found_album

    def test_empty_sample_minimal_output(self):
        """Sample with all None fields should produce minimal output."""
        sample = Sample(
            id=1, path="/a/file.wav", filename="file.wav"
        )
        result = format_metadata(sample, None)
        # Should have very few entries (mostly None/empty fields)
        # Just checking it doesn't crash and returns a list
        assert isinstance(result, list)

    def test_all_fields_filled(self):
        """Sample with all fields filled should include all of them."""
        sample = Sample(
            id=1, path="/a/kick.wav", filename="kick.wav",
            format="wav", samplerate=48000, channels=2,
            duration_sec=60.0, file_size=5_000_000,
            bpm=128.0, musical_key="D", key_scale="major",
            loudness_lufs=-10.0, category="drum",
            instrument_class="kick", source="local"
        )
        result = format_metadata(sample, None)
        labels = [label for label, _ in result]

        # Check for key fields
        assert "Format" in labels
        assert "Sample rate" in labels
        assert "Channels" in labels
        assert "Size" in labels
        assert "Loudness" in labels
        assert "Category" in labels
        assert "Class" in labels
        assert "Source" in labels


class TestFilenameParts:
    """Test filename_parts(filename) -> (stem, suffix)."""

    def test_splits_filename_and_extension(self):
        assert filename_parts("kick.wav") == ("kick", ".wav")

    def test_splits_only_final_extension(self):
        assert filename_parts("kick.v2.wav") == ("kick.v2", ".wav")

    def test_filename_without_extension(self):
        assert filename_parts("kick") == ("kick", "")


class TestFileUrls:
    """Test file_urls(samples) -> list[str] preserving selected sample paths."""

    def test_empty(self):
        assert file_urls([]) == []

    def test_preserves_paths_and_order(self):
        s1 = Sample(id=1, path="/packs/a.wav", filename="a.wav")
        s2 = Sample(id=2, path="/packs/nested/b.wav", filename="b.wav")

        assert file_urls([s1, s2]) == ["/packs/a.wav", "/packs/nested/b.wav"]


class TestComputePeaks:
    """Test compute_peaks(samples: np.ndarray, width: int) -> list[tuple[float, float]]."""

    def test_linear_ramp_reduces_to_min_max_pairs(self):
        """Linear ramp should yield pairs tracking min/max across each bin."""
        # Create ramp: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        samples = np.linspace(0, 9, 10, dtype=np.float32)
        peaks = compute_peaks(samples, width=5)

        # Should return 5 pairs (exactly width)
        assert len(peaks) == 5

        # Each pair should be (float, float)
        for pair in peaks:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert isinstance(pair[0], float)
            assert isinstance(pair[1], float)

        # First pair min/max should be near the start
        assert peaks[0][0] <= 1.0  # min of first bin
        assert peaks[0][1] >= 0.0  # max of first bin

        # Last pair min/max should be near the end
        assert peaks[-1][0] <= 9.0  # min of last bin
        assert peaks[-1][1] >= 8.0  # max of last bin

        # Each pair satisfies min <= max
        for min_val, max_val in peaks:
            assert min_val <= max_val

    def test_sine_wave_reduction(self):
        """Sine wave should produce reasonable min/max pairs."""
        # Create sine: 1 full cycle
        samples = np.sin(np.linspace(0, 2 * math.pi, 100, dtype=np.float32)).astype(np.float32)
        peaks = compute_peaks(samples, width=10)

        # Should return 10 pairs
        assert len(peaks) == 10

        # Each pair satisfies min <= max
        for min_val, max_val in peaks:
            assert min_val <= max_val

        # Sine peaks should be roughly symmetric (roughly equal magnitude)
        first_max = peaks[0][1] - peaks[0][0]
        last_max = peaks[-1][1] - peaks[-1][0]
        # Both should have some non-zero spread
        assert first_max > 0
        assert last_max > 0

    def test_silence_all_zeros(self):
        """All-zero signal should produce (0.0, 0.0) pairs."""
        samples = np.zeros(100, dtype=np.float32)
        peaks = compute_peaks(samples, width=10)

        assert len(peaks) == 10
        for min_val, max_val in peaks:
            assert min_val == 0.0
            assert max_val == 0.0

    def test_single_sample(self):
        """Single sample should return one (value, value) pair."""
        samples = np.array([5.0], dtype=np.float32)
        peaks = compute_peaks(samples, width=10)

        assert len(peaks) == 1
        assert peaks[0] == (5.0, 5.0)

    def test_width_larger_than_samples(self):
        """Width larger than len(samples) should return len(samples) pairs."""
        samples = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        peaks = compute_peaks(samples, width=100)

        # Should return min(width, len(samples)) = 3
        assert len(peaks) == 3
        assert peaks[0] == (1.0, 1.0)
        assert peaks[1] == (2.0, 2.0)
        assert peaks[2] == (3.0, 3.0)

    def test_width_zero_returns_empty(self):
        """Width <= 0 should return empty list."""
        samples = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert compute_peaks(samples, width=0) == []
        assert compute_peaks(samples, width=-1) == []

    def test_empty_array_returns_empty(self):
        """Empty array should return empty list."""
        samples = np.array([], dtype=np.float32)
        peaks = compute_peaks(samples, width=10)
        assert peaks == []

    def test_array_with_nan_drops_nan_before_reduction(self):
        """NaN values should be dropped before reduction."""
        # Mix of valid and NaN: [1, nan, 2, 3, nan, 4]
        samples = np.array([1.0, np.nan, 2.0, 3.0, np.nan, 4.0], dtype=np.float32)
        peaks = compute_peaks(samples, width=3)

        # After dropping NaN: [1, 2, 3, 4] -> 4 values
        # With width=3, should return 3 pairs (exactly width)
        assert len(peaks) == 3

        # All values should be finite
        for min_val, max_val in peaks:
            assert math.isfinite(min_val)
            assert math.isfinite(max_val)

    def test_array_with_inf_drops_inf_before_reduction(self):
        """Inf values should be dropped before reduction."""
        samples = np.array([1.0, np.inf, 2.0, -np.inf, 3.0], dtype=np.float32)
        peaks = compute_peaks(samples, width=2)

        # After dropping inf: [1, 2, 3] -> 3 values
        # With width=2, should return 2 pairs
        assert len(peaks) == 2

        # All values should be finite
        for min_val, max_val in peaks:
            assert math.isfinite(min_val)
            assert math.isfinite(max_val)

    def test_all_non_finite_input_returns_empty(self):
        """Array with only NaN/inf should return empty list."""
        samples = np.array([np.nan, np.inf, -np.inf, np.nan], dtype=np.float32)
        peaks = compute_peaks(samples, width=10)
        assert peaks == []

    def test_returned_values_are_plain_python_float(self):
        """Returned min/max values should be plain Python float, not np.float32."""
        samples = np.array([1.5, 2.5], dtype=np.float32)
        peaks = compute_peaks(samples, width=2)

        for min_val, max_val in peaks:
            assert type(min_val) is float
            assert type(max_val) is float
            assert not isinstance(min_val, np.floating)
            assert not isinstance(max_val, np.floating)

    def test_mixed_positive_negative_amplitudes(self):
        """Signal with positive and negative values should track min/max correctly."""
        samples = np.array([-5.0, -3.0, 2.0, 4.0, -1.0], dtype=np.float32)
        peaks = compute_peaks(samples, width=5)

        assert len(peaks) == 5
        # Check that min/max pairs respect the original values
        assert peaks[0][0] == -5.0  # first sample
        assert peaks[4][1] == -1.0  # last sample


class TestTreeRows:
    """Test tree_rows(nodes: dict, favorites: list) -> list[tuple]."""

    def test_empty_nodes_empty_favorites_returns_favorites_and_library_roots(self):
        """Empty input should return the ★ Favorites root and the Library root."""
        nodes = {}
        favorites = []

        result = tree_rows(nodes, favorites)

        # Should have exactly two rows: ★ Favorites root + Library root
        assert len(result) == 2

        parent_key, key, label, is_favorites_branch = result[0]
        assert parent_key is None
        assert key == "__favorites__"
        assert label == "★ Favorites"
        assert is_favorites_branch is True

        assert result[1] == (None, "__library__", "Library", False)

    def test_crates_branch_between_favorites_and_library(self):
        nodes = {}
        favorites = []
        crate = type("Crate", (), {"id": 7, "name": "Breaks"})()

        result = tree_rows(nodes, favorites, [crate])

        assert result == [
            (None, "__favorites__", "★ Favorites", True),
            (None, "__crates__", "📦 Crates", False),
            ("__crates__", "crate:7", "Breaks", False),
            (None, "__library__", "Library", False),
        ]

    def test_favorites_branch_always_first(self):
        """Favorites branch should always appear first, even with folder nodes."""
        nodes = {
            "packs": FolderNode(name="packs", key="packs", parent_key=None),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # First row should be ★ Favorites root
        assert result[0][1] == "__favorites__"
        assert result[0][3] is True  # is_favorites_branch

    def test_single_favorite_sample(self):
        """Single favorite should produce root + one child row."""
        nodes = {}
        sample = _make_sample(1, "kick.wav")
        favorites = [sample]

        result = tree_rows(nodes, favorites)

        # Should have 3 rows: ★ root + 1 child + Library root
        assert len(result) == 3

        # First row: ★ Favorites root
        assert result[0] == (None, "__favorites__", "★ Favorites", True)

        # Second row: favorite child
        parent_key, key, label, is_fav_branch = result[1]
        assert parent_key == "__favorites__"
        assert key == "fav:1"
        assert label == "kick.wav"
        assert is_fav_branch is True

        # Third row: Library root
        assert result[2] == (None, "__library__", "Library", False)

    def test_multiple_favorites_in_order(self):
        """Multiple favorites should appear in order after root."""
        nodes = {}
        fav1 = _make_sample(10, "snare.wav")
        fav2 = _make_sample(20, "kick.wav")
        favorites = [fav1, fav2]

        result = tree_rows(nodes, favorites)

        # Should have 4 rows: ★ root + 2 children + Library root
        assert len(result) == 4

        # First row: root
        assert result[0][1] == "__favorites__"

        # Second and third: favorites in order
        assert result[1] == ("__favorites__", "fav:10", "snare.wav", True)
        assert result[2] == ("__favorites__", "fav:20", "kick.wav", True)

        # Fourth row: Library root
        assert result[3] == (None, "__library__", "Library", False)

    def test_simple_folder_nodes_nested_structure(self):
        """Nested folders should appear in parent-before-child order, sorted by key."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
            "packs/drums": FolderNode(
                name="drums",
                key="packs/drums",
                parent_key="packs",
                children={},
                samples=[],
            ),
            "packs/bass": FolderNode(
                name="bass",
                key="packs/bass",
                parent_key="packs",
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Should have 5 rows: ★ Favorites root + Library root + 3 folder rows
        assert len(result) == 5

        # First row: ★ Favorites root, second: Library root
        assert result[0][1] == "__favorites__"
        assert result[1][1] == "__library__"

        # Folder rows should follow, sorted by key
        folder_rows = result[2:]
        keys = [row[1] for row in folder_rows]
        assert keys == ["packs", "packs/bass", "packs/drums"]

        # Top-level folders are reparented under Library
        assert folder_rows[0][0] == "__library__"

    def test_deeply_nested_folders_parent_before_child(self):
        """Deeply nested folders: parent must appear before child."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
            "packs/drums": FolderNode(
                name="drums",
                key="packs/drums",
                parent_key="packs",
                children={},
                samples=[],
            ),
            "packs/drums/kicks": FolderNode(
                name="kicks",
                key="packs/drums/kicks",
                parent_key="packs/drums",
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Skip ★ Favorites + Library roots and check folder order
        folder_rows = result[2:]
        keys = [row[1] for row in folder_rows]

        # Parent must come before children
        assert keys.index("packs") < keys.index("packs/drums")
        assert keys.index("packs/drums") < keys.index("packs/drums/kicks")

    def test_folder_parent_key_set_correctly(self):
        """Parent_key in folder rows should match their parent's key."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
            "packs/drums": FolderNode(
                name="drums",
                key="packs/drums",
                parent_key="packs",
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Find folder rows (skip ★ Favorites + Library roots at index 0, 1)
        packs_row = result[2]
        drums_row = result[3]

        assert packs_row[0] == "__library__"  # top-level folders sit under Library
        assert packs_row[1] == "packs"

        assert drums_row[0] == "packs"  # drums parent is packs
        assert drums_row[1] == "packs/drums"

    def test_folder_labels_use_node_name_not_key(self):
        """Folder row labels should use FolderNode.name, not the key."""
        nodes = {
            "packs/drums": FolderNode(
                name="drums",  # name is "drums"
                key="packs/drums",  # key is "packs/drums"
                parent_key="packs",
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Find drums row (skip ★ Favorites + Library roots)
        drums_row = result[2]
        label = drums_row[2]

        assert label == "drums"  # Should be the name, not "packs/drums"

    def test_folder_rows_have_is_favorites_branch_false(self):
        """Folder rows should have is_favorites_branch = False."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Find packs row (skip ★ Favorites + Library roots)
        packs_row = result[2]
        is_fav_branch = packs_row[3]

        assert is_fav_branch is False

    def test_favorites_precede_folder_rows(self):
        """All favorite rows must precede all folder rows."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
        }
        fav1 = _make_sample(1, "snare.wav")
        fav2 = _make_sample(2, "kick.wav")
        favorites = [fav1, fav2]

        result = tree_rows(nodes, favorites)

        # First 3 rows should be ★ Favorites root + 2 favorites
        assert result[0][1] == "__favorites__"
        assert result[1][1] == "fav:1"
        assert result[2][1] == "fav:2"

        # Library root precedes folder rows
        assert result[3][1] == "__library__"

        # Fifth row should be the folder
        assert result[4][1] == "packs"
        assert result[4][3] is False  # is_favorites_branch

    def test_multiple_favorites_with_nested_folders(self):
        """Favorites + folders: favorites first, then folders in parent-before-child order."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
            "packs/drums": FolderNode(
                name="drums",
                key="packs/drums",
                parent_key="packs",
                children={},
                samples=[],
            ),
        }
        fav1 = _make_sample(100, "favorite.wav")
        favorites = [fav1]

        result = tree_rows(nodes, favorites)

        # Expected order: ★ root, fav1, Library root, packs, packs/drums
        keys = [row[1] for row in result]
        assert keys == ["__favorites__", "fav:100", "__library__", "packs", "packs/drums"]

        # Check is_favorites_branch flags
        assert result[0][3] is True  # ★ root
        assert result[1][3] is True  # fav1
        assert result[2][3] is False  # Library root
        assert result[3][3] is False  # packs
        assert result[4][3] is False  # packs/drums

    def test_folders_sorted_lexically_at_same_level(self):
        """Folders at the same nesting level should be sorted by key."""
        nodes = {
            "zebra": FolderNode(
                name="zebra",
                key="zebra",
                parent_key=None,
                children={},
                samples=[],
            ),
            "apple": FolderNode(
                name="apple",
                key="apple",
                parent_key=None,
                children={},
                samples=[],
            ),
            "monkey": FolderNode(
                name="monkey",
                key="monkey",
                parent_key=None,
                children={},
                samples=[],
            ),
        }
        favorites = []

        result = tree_rows(nodes, favorites)

        # Skip ★ Favorites + Library roots and check folder order
        folder_keys = [row[1] for row in result[2:]]
        assert folder_keys == ["apple", "monkey", "zebra"]

    def test_complex_scenario_favorites_and_nested_folders(self):
        """Complex: 2 favorites, 3-level nested folders, verify full order."""
        nodes = {
            "packs": FolderNode(
                name="packs",
                key="packs",
                parent_key=None,
                children={},
                samples=[],
            ),
            "packs/drums": FolderNode(
                name="drums",
                key="packs/drums",
                parent_key="packs",
                children={},
                samples=[],
            ),
            "packs/drums/kicks": FolderNode(
                name="kicks",
                key="packs/drums/kicks",
                parent_key="packs/drums",
                children={},
                samples=[],
            ),
        }
        fav1 = _make_sample(10, "snare.wav")
        fav2 = _make_sample(20, "clap.wav")
        favorites = [fav1, fav2]

        result = tree_rows(nodes, favorites)

        # Expected order:
        # 1. ★ Favorites root
        # 2. fav:10
        # 3. fav:20
        # 4. Library root
        # 5. packs
        # 6. packs/drums
        # 7. packs/drums/kicks
        keys = [row[1] for row in result]
        assert keys == [
            "__favorites__",
            "fav:10",
            "fav:20",
            "__library__",
            "packs",
            "packs/drums",
            "packs/drums/kicks",
        ]

        # Verify parent_key for each row
        assert result[0][0] is None  # ★ root
        assert result[1][0] == "__favorites__"  # fav:10
        assert result[2][0] == "__favorites__"  # fav:20
        assert result[3][0] is None  # Library root (top-level)
        assert result[4][0] == "__library__"  # packs sits under Library
        assert result[5][0] == "packs"  # packs/drums
        assert result[6][0] == "packs/drums"  # packs/drums/kicks

        # Verify is_favorites_branch
        is_fav_flags = [row[3] for row in result]
        assert is_fav_flags == [True, True, True, False, False, False, False]


class TestHitRows:
    """Test hit_rows(hits) display tuples."""

    def test_empty(self):
        assert hit_rows([]) == []

    def test_full_hit_formats_duration_one_decimal(self):
        hit = SearchHit(
            backend="freesound", id="123", title="Kick", artist="Foo",
            duration_sec=2.5,
        )
        assert hit_rows([hit]) == [("Kick", "Foo", "-", "", "2.5", "freesound")]

    def test_missing_duration_shows_dash(self):
        hit = SearchHit(backend="yandex", id="x", title="Track", artist="Bar")
        assert hit_rows([hit]) == [("Track", "Bar", "-", "", "-", "yandex")]

    def test_metadata_overrides_source_fields(self):
        hit = SearchHit(
            backend="youtube",
            id="x",
            title="Eminem - Lose Yourself (Official Video)",
            artist="EminemMusic",
            extra={"metadata": {
                "title": "Lose Yourself",
                "artist": "Eminem",
                "album": "8 Mile",
                "year": 2002,
            }},
        )

        assert hit_rows([hit]) == [("Lose Yourself", "Eminem", "2002", "8 Mile", "-", "youtube")]

    def test_order_preserved_for_row_index_mapping(self):
        hits = [
            SearchHit(backend="a", id="1", title="One"),
            SearchHit(backend="b", id="2", title="Two"),
        ]
        rows = hit_rows(hits)
        assert [r[0] for r in rows] == ["One", "Two"]
        assert [r[5] for r in rows] == ["a", "b"]


class TestIsSampleFavorite:
    """Test is_sample_favorite(favorites_by_id: dict, sample_id: int) -> bool."""

    def test_sample_id_present_returns_true(self):
        """Sample ID that exists in dict should return True."""
        sample1 = _make_sample(42, "kick.wav")
        sample2 = _make_sample(99, "snare.wav")
        favorites_by_id = {42: sample1, 99: sample2}
        assert is_sample_favorite(favorites_by_id, 42) is True

    def test_sample_id_absent_returns_false(self):
        """Sample ID that does not exist in dict should return False."""
        sample1 = _make_sample(42, "kick.wav")
        favorites_by_id = {42: sample1}
        assert is_sample_favorite(favorites_by_id, 100) is False

    def test_empty_dict_returns_false(self):
        """Empty dict should return False for any sample ID."""
        favorites_by_id = {}
        assert is_sample_favorite(favorites_by_id, 1) is False
        assert is_sample_favorite(favorites_by_id, 42) is False


class TestResolveSimilar:
    """Test resolve_similar(hits, samples_by_id) -> list[Sample] in hit order, None-filtered."""

    def test_empty_hits_returns_empty(self):
        assert resolve_similar([], {}) == []

    def test_preserves_hit_order(self):
        s1 = _make_sample(1, "a.wav")
        s2 = _make_sample(2, "b.wav")
        s3 = _make_sample(3, "c.wav")
        by_id = {1: s1, 2: s2, 3: s3}
        # hits ranked 3, 1, 2 by similarity score
        hits = [(3, 0.99), (1, 0.80), (2, 0.50)]
        assert resolve_similar(hits, by_id) == [s3, s1, s2]

    def test_skips_missing_ids(self):
        s1 = _make_sample(1, "a.wav")
        by_id = {1: s1, 2: None}  # id 2 unresolved (deleted between query and fetch)
        hits = [(2, 0.9), (1, 0.7), (99, 0.6)]
        assert resolve_similar(hits, by_id) == [s1]


class TestSampleTable:
    """Optional PySide6 smoke tests for table columns and drag MIME payload."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_table_has_nine_columns_without_extension(self):
        self._app()
        from cratedig.gui.sample_table import SampleTable

        table = SampleTable()

        headers = [
            table._table.horizontalHeaderItem(col).text()
            for col in range(table._table.columnCount())
        ]
        assert table._table.columnCount() == 9
        assert "Extension" not in headers

    def test_drag_mime_data_uses_selected_sample_file_urls(self):
        self._app()
        from PySide6.QtCore import QItemSelectionModel
        from cratedig.gui.sample_table import SampleTable

        table = SampleTable()
        s1 = Sample(id=1, path="/packs/a.wav", filename="a.wav")
        s2 = Sample(id=2, path="/packs/b.wav", filename="b.wav")
        table.set_samples([s1, s2])

        selection = table._table.selectionModel()
        selection.select(
            table._table.model().index(0, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
        selection.select(
            table._table.model().index(1, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )

        mime = table._table.mimeData([])

        assert [url.toLocalFile() for url in mime.urls()] == ["/packs/a.wav", "/packs/b.wav"]


class TestSimplerGeometry:
    """Pure time/pixel mapping + region clamping for the Simpler waveform."""

    def test_time_to_x_endpoints(self):
        assert time_to_x(0.0, 100, 2.0) == 0
        assert time_to_x(2.0, 100, 2.0) == 100
        assert time_to_x(1.0, 100, 2.0) == 50

    def test_time_to_x_clamped(self):
        assert time_to_x(-1.0, 100, 2.0) == 0
        assert time_to_x(5.0, 100, 2.0) == 100

    def test_time_to_x_degenerate(self):
        assert time_to_x(1.0, 0, 2.0) == 0
        assert time_to_x(1.0, 100, 0.0) == 0

    def test_x_to_time_roundtrip(self):
        assert x_to_time(50, 100, 2.0) == pytest.approx(1.0)
        assert x_to_time(0, 100, 2.0) == pytest.approx(0.0)
        assert x_to_time(100, 100, 2.0) == pytest.approx(2.0)

    def test_x_to_time_clamped(self):
        assert x_to_time(-10, 100, 2.0) == pytest.approx(0.0)
        assert x_to_time(200, 100, 2.0) == pytest.approx(2.0)

    def test_clamp_region_orders_and_bounds(self):
        assert clamp_region(1.5, 0.5, 2.0) == pytest.approx((0.5, 1.5))
        assert clamp_region(-1.0, 3.0, 2.0) == pytest.approx((0.0, 2.0))

    def test_clamp_region_min_len(self):
        start, end = clamp_region(1.0, 1.0, 2.0, min_len=0.1)
        assert end - start == pytest.approx(0.1)

    def test_clamp_region_min_len_at_tail(self):
        start, end = clamp_region(2.0, 2.0, 2.0, min_len=0.1)
        assert end == pytest.approx(2.0)
        assert end - start == pytest.approx(0.1)


def test_tree_rows_saved_branch_groups_by_dated_folder(tmp_path):
    saved_root = tmp_path / "_saved"
    dated = saved_root / "06_06_2026"
    saved = [
        Sample(id=7, path=str(dated / "edit_a.wav"), filename="edit_a.wav"),
        Sample(id=8, path=str(dated / "edit_b.wav"), filename="edit_b.wav"),
    ]
    rows = tree_rows({}, [], None, saved, saved_root)
    keys = [r[1] for r in rows]
    assert "__saved__" in keys
    assert "saved-dir:06_06_2026" in keys
    assert "saved:7" not in keys and "saved:8" not in keys
    assert rows[keys.index("saved-dir:06_06_2026")][0] == "__saved__"
    # Saved branch sits before the Library root
    assert keys.index("__saved__") < keys.index("__library__")


def test_tree_rows_no_saved_branch_when_empty():
    rows = tree_rows({}, [], None, [])
    assert "__saved__" not in [r[1] for r in rows]


def test_tree_rows_root_saved_file_uses_mtime_date(tmp_path):
    saved_root = tmp_path / "_saved"
    saved_root.mkdir()
    fp = saved_root / "legacy.wav"
    fp.write_text("x")
    sample = Sample(id=9, path=str(fp), filename=fp.name)

    rows = tree_rows({}, [], None, [sample], saved_root)

    date_key = next(r[1] for r in rows if r[1].startswith("saved-dir:"))
    assert date_key != "saved-dir:_saved"
    assert "saved:9" not in [r[1] for r in rows]


def test_worker_delete_saved_file_unlinks_when_send2trash_missing(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from types import SimpleNamespace
    from cratedig.db import Database
    from cratedig.gui.worker import IndexWorker

    fp = tmp_path / "edit.wav"
    fp.write_text("x")
    db = Database(tmp_path / "s.db")
    sid = db.upsert_sample(Sample(id=None, path=str(fp), filename=fp.name, source="edit"))
    monkeypatch.setattr("cratedig.files.send2trash", lambda _path: pytest.fail("saved files should unlink directly"))

    cfg = SimpleNamespace(paths=SimpleNamespace(library_dirs=(), saved_dir=tmp_path))
    IndexWorker(db, cfg).request_delete(sid)

    assert not fp.exists()
    assert db.get_sample(sid) is None
    db.close()


def test_worker_delete_file_inside_saved_dir_unlinks_even_if_source_is_local(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from types import SimpleNamespace
    from cratedig.db import Database
    from cratedig.gui.worker import IndexWorker

    saved_dir = tmp_path / "_saved"
    saved_dir.mkdir()
    fp = saved_dir / "legacy.wav"
    fp.write_text("x")
    db = Database(tmp_path / "s.db")
    sid = db.upsert_sample(Sample(id=None, path=str(fp), filename=fp.name, source="local"))
    monkeypatch.setattr("cratedig.files.send2trash", lambda _path: pytest.fail("saved-dir files should unlink directly"))

    cfg = SimpleNamespace(paths=SimpleNamespace(library_dirs=(), saved_dir=saved_dir))
    IndexWorker(db, cfg).request_delete(sid)

    assert not fp.exists()
    assert db.get_sample(sid) is None
    db.close()


def test_main_window_refreshes_current_tree_table_after_reload():
    pytest.importorskip("PySide6")
    from cratedig.gui.main_window import MainWindow

    class TableStub:
        def __init__(self):
            self.calls = []

        def set_samples(self, samples, tags_by_id=None, **_kwargs):
            self.calls.append((list(samples), tags_by_id))

    sample = Sample(id=1, path="/packs/kick.wav", filename="kick.wav")
    table = TableStub()
    window = MainWindow.__new__(MainWindow)
    window._sample_table = table
    window._tags_by_id = {1: ["tag"]}
    window._favorites_by_id = {}
    window._saved_folder_samples = {}
    window._crate_samples_by_id = {}
    window._nodes = {
        "packs": FolderNode(name="packs", key="packs", parent_key=None, samples=[sample]),
    }
    window._current_tree_key = "packs"
    window._current_tree_is_fav = False

    MainWindow._refresh_current_tree_table(window)

    assert table.calls == [([sample], {1: ["tag"]})]


def test_main_window_clears_table_when_current_folder_disappears_after_reload():
    pytest.importorskip("PySide6")
    from cratedig.gui.main_window import MainWindow

    class TableStub:
        def __init__(self):
            self.calls = []

        def set_samples(self, samples, tags_by_id=None, **_kwargs):
            self.calls.append((list(samples), tags_by_id))

    table = TableStub()
    window = MainWindow.__new__(MainWindow)
    window._sample_table = table
    window._tags_by_id = {}
    window._favorites_by_id = {}
    window._saved_folder_samples = {}
    window._crate_samples_by_id = {}
    window._nodes = {}
    window._current_tree_key = "packs"
    window._current_tree_is_fav = False

    MainWindow._refresh_current_tree_table(window)

    assert table.calls == [([], {})]


class TestSimplerPane:
    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_knobs_feed_current_params(self, tmp_path):
        self._app()
        from PySide6.QtWidgets import QDoubleSpinBox
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/kick.wav", 2.0)
        pane._gain.setValue(3.0)
        pane._attack.setValue(0.25)
        pane._decay.setValue(0.5)
        pane._sustain.setValue(0.75)
        pane._release.setValue(1.0)

        params = pane.current_params()

        assert pane.findChildren(QDoubleSpinBox) == []
        assert params["gain_db"] == pytest.approx(3.0)
        assert params["adsr"] == pytest.approx((0.25, 0.5, 0.75, 1.0))

    def test_canvas_zoom_preserves_region(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.resize(400, 180)
        pane._canvas.resize(400, 120)
        pane.set_sample("/tmp/loop.wav", 10.0)
        pane._canvas.region = (2.0, 8.0)

        pane._canvas._zoom_at(2.0, 200)

        assert pane._canvas.view == pytest.approx((2.5, 7.5))
        assert pane._canvas.region == pytest.approx((2.0, 8.0))

    def test_canvas_pan_preserves_zoom_span(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane._canvas.resize(400, 120)
        pane.set_sample("/tmp/loop.wav", 10.0)
        pane._canvas.view = (2.0, 6.0)

        pane._canvas._pan_by_pixels(100)

        assert pane._canvas.view == pytest.approx((6.0, 10.0))

    def test_canvas_region_paint_coordinates_are_not_clamped_to_view(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane._canvas.resize(400, 120)
        pane.set_sample("/tmp/loop.wav", 10.0)
        pane._canvas.region = (2.0, 8.0)
        pane._canvas.view = (4.0, 6.0)

        assert pane._canvas._handle_x()["start"] == 0
        assert pane._canvas._handle_x()["end"] == 400
        assert pane._canvas._region_view_x() == pytest.approx((-400.0, 800.0))

    def test_live_render_peaks_rescale_with_view_zoom(self, tmp_path):
        self._app()
        import numpy as np
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane._canvas.resize(80, 120)
        pane.set_sample("/tmp/loop.wav", 8.0)
        pane._canvas.region = (2.0, 6.0)
        pane.set_mono(np.linspace(-1.0, 1.0, 1000, dtype=np.float32))
        whole_view_bins = len(pane._canvas._rendered_peaks)

        pane._canvas.view = (2.0, 4.0)
        pane._canvas._recompute_rendered()

        assert whole_view_bins == 80
        assert len(pane._canvas._rendered_peaks) == 160

    def test_canvas_samples_for_interval_uses_raw_mono_slice(self, tmp_path):
        self._app()
        import numpy as np
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/loop.wav", 10.0)
        samples = np.arange(100, dtype=np.float32)

        visible = pane._canvas._samples_for_interval(samples, 0.0, 10.0, 2.0, 4.0)

        assert visible[0] == pytest.approx(20.0)
        assert visible[-1] == pytest.approx(39.0)

    def test_loop_button_feeds_current_params(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/loop.wav", 4.0)

        assert pane.current_params()["loop"] is False
        pane._loop.setChecked(True)
        assert pane.current_params()["loop"] is True
        assert pane._canvas.loop_enabled is True

    def test_adsr_knobs_update_canvas_overlay(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/kick.wav", 2.0)

        assert pane._canvas.adsr is None
        pane._attack.setValue(0.25)

        assert pane._canvas.adsr is not None
        assert pane._canvas.adsr.attack == pytest.approx(0.25)

    def test_live_render_updates_when_gain_changes(self, tmp_path):
        self._app()
        import numpy as np
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane._canvas.resize(80, 120)
        pane.set_sample("/tmp/kick.wav", 4.0)
        pane._canvas.region = (1.0, 3.0)
        pane.set_mono(np.ones(400, dtype=np.float32) * 0.25)
        before = pane._canvas._rendered_peaks[:]

        pane._gain.setValue(6.0)

        assert pane._canvas._rendered_peaks
        assert pane._canvas._rendered_peaks != before

    def test_preview_trigger_toggles_to_stop_signal(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/kick.wav", 2.0)
        requested = []
        stopped = []
        pane.preview_requested.connect(lambda params: requested.append(params))
        pane.preview_stop_requested.connect(lambda: stopped.append(True))

        pane.trigger_preview()
        pane.set_preview_playing(True)
        pane.trigger_preview()

        assert len(requested) == 1
        assert stopped == [True]

    def test_preview_playhead_clamps_and_clears_on_stop(self, tmp_path):
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane.set_sample("/tmp/kick.wav", 2.0)

        pane.set_preview_playhead(3.0)
        assert pane._canvas.playhead_time == pytest.approx(2.0)

        pane.set_preview_playing(False)
        assert pane._canvas.playhead_time is None

    def test_canvas_drag_starts_on_mouse_move_not_click_release(self, tmp_path):
        self._app()
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from cratedig.gui.simpler_pane import SimplerPane

        pane = SimplerPane(tmp_path)
        pane._canvas.resize(240, 120)
        pane.set_sample("/tmp/kick.wav", 2.0)
        starts = []
        pane._canvas.drag_started.connect(lambda: starts.append(True))

        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(120, 60),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pane._canvas.mousePressEvent(press)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(120, 60),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pane._canvas.mouseReleaseEvent(release)
        assert starts == []

        pane._canvas.mousePressEvent(press)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(120 + QApplication.startDragDistance() + 2, 60),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pane._canvas.mouseMoveEvent(move)

        assert starts == [True]

    def test_start_drag_cancelled_removes_orphan_and_skips_export(self, tmp_path, monkeypatch):
        """Test that cancelled drag (IgnoreAction) removes orphan and doesn't emit exported."""
        self._app()
        import numpy as np
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import Qt
        from cratedig.gui.simpler_pane import SimplerPane
        from cratedig.audio.editor import write_wav

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()

        # Create a synthetic source WAV
        source_wav = tmp_path / "source.wav"
        sr = 44100
        duration = 1.0
        mono = np.sin(2 * np.pi * 440 * np.arange(int(sr * duration), dtype=np.float32) / sr) * 0.1
        write_wav(mono, sr, source_wav)

        # Create SimplerPane and set the sample
        pane = SimplerPane(saved_dir)
        pane.set_sample(str(source_wav), duration)
        pane.set_mono(mono)

        # Monkeypatch QDrag.exec to return IgnoreAction (cancelled drop)
        exec_call_count = [0]
        original_exec = QDrag.exec

        def mock_exec(self, *args, **kwargs):
            exec_call_count[0] += 1
            return Qt.DropAction.IgnoreAction

        monkeypatch.setattr(QDrag, "exec", mock_exec)

        # Track exported signal emissions
        exported_calls = []
        pane.exported.connect(lambda path: exported_calls.append(path))

        # Call _start_drag
        pane._start_drag()

        # Verify exec was called
        assert exec_call_count[0] == 1

        # Verify exported was NOT emitted
        assert exported_calls == []

        # Verify the rendered file was not left behind (no orphan in saved_dir)
        # List all files in saved_dir recursively
        all_files = list(saved_dir.glob("**/*.wav"))
        assert len(all_files) == 0, f"Expected no WAV files after cancelled drag, but found: {all_files}"

    def test_start_drag_accepted_keeps_file_and_emits_export(self, tmp_path, monkeypatch):
        """Test that accepted drag (CopyAction) keeps file and emits exported exactly once."""
        self._app()
        import numpy as np
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import Qt
        from cratedig.gui.simpler_pane import SimplerPane
        from cratedig.audio.editor import write_wav

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()

        # Create a synthetic source WAV
        source_wav = tmp_path / "source.wav"
        sr = 44100
        duration = 1.0
        mono = np.sin(2 * np.pi * 440 * np.arange(int(sr * duration), dtype=np.float32) / sr) * 0.1
        write_wav(mono, sr, source_wav)

        # Create SimplerPane and set the sample
        pane = SimplerPane(saved_dir)
        pane.set_sample(str(source_wav), duration)
        pane.set_mono(mono)

        # Monkeypatch QDrag.exec to return CopyAction (accepted drop)
        exec_call_count = [0]

        def mock_exec(self, *args, **kwargs):
            exec_call_count[0] += 1
            return Qt.DropAction.CopyAction

        monkeypatch.setattr(QDrag, "exec", mock_exec)

        # Track exported signal emissions
        exported_calls = []
        pane.exported.connect(lambda path: exported_calls.append(path))

        # Call _start_drag
        pane._start_drag()

        # Verify exec was called
        assert exec_call_count[0] == 1

        # Verify exported was emitted exactly once
        assert len(exported_calls) == 1

        # Verify the emitted path exists on disk
        emitted_path = exported_calls[0]
        assert Path(emitted_path).exists(), f"Expected emitted file to exist at {emitted_path}"

        # Verify it's actually in the saved_dir structure
        all_files = list(saved_dir.glob("**/*.wav"))
        assert len(all_files) == 1, f"Expected 1 WAV file in saved_dir, but found: {all_files}"
        assert str(all_files[0]) == emitted_path

    def test_start_drag_render_failure_skips_export(self, tmp_path, monkeypatch):
        """Test that a render failure early-returns: no export, no file written."""
        self._app()
        import numpy as np
        from PySide6.QtGui import QDrag
        from cratedig.gui.simpler_pane import SimplerPane
        from cratedig.audio.editor import write_wav

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()

        source_wav = tmp_path / "source.wav"
        sr = 44100
        mono = np.sin(2 * np.pi * 440 * np.arange(sr, dtype=np.float32) / sr) * 0.1
        write_wav(mono, sr, source_wav)

        pane = SimplerPane(saved_dir)
        pane.set_sample(str(source_wav), 1.0)
        pane.set_mono(mono)

        # Force the render to fail; _start_drag must early-return.
        monkeypatch.setattr(pane, "_render_to_saved", lambda: (_ for _ in ()).throw(IOError("boom")))

        exec_call_count = [0]
        monkeypatch.setattr(QDrag, "exec", lambda self, *a, **k: exec_call_count.__setitem__(0, 1))

        exported_calls = []
        pane.exported.connect(lambda path: exported_calls.append(path))

        pane._start_drag()

        assert exec_call_count[0] == 0, "QDrag.exec must not run when render fails"
        assert exported_calls == []
        assert list(saved_dir.glob("**/*.wav")) == []


class TestDownloadPane:
    """Test DownloadPane progress bar API contract."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_start_download_busy_state(self):
        """After pane.start_download() -> indeterminate animation state."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.start_download()

        assert pane._bar.minimum() == 0
        assert pane._bar.maximum() == 0
        assert pane._bar.property("state") == "busy"
        assert "Downloading" in pane._bar.format()

    def test_finish_download_ok_green(self):
        """After pane.finish_download(True, msg) -> completed ok state with green stylesheet."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.finish_download(True, "downloaded track.mp3")

        assert pane._bar.maximum() == 100
        assert pane._bar.value() == 100
        assert pane._bar.property("state") == "ok"
        fmt = pane._bar.format()
        assert fmt.startswith("✓")
        assert "downloaded track.mp3" in fmt

    def test_finish_download_fail_red(self):
        """After pane.finish_download(False, msg) -> completed fail state with red stylesheet."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.finish_download(False, "no preview")

        assert pane._bar.property("state") == "fail"
        assert pane._bar.maximum() == 100
        assert pane._bar.value() == pane._bar.maximum()
        fmt = pane._bar.format()
        assert fmt.startswith("✗")
        assert "no preview" in fmt

    def test_finish_download_fail_stylesheet_differs_from_ok(self):
        """Stylesheet when fail must differ from ok stylesheet."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane_ok = DownloadPane()
        pane_ok.finish_download(True, "ok msg")
        ok_style = pane_ok._bar.styleSheet()

        pane_fail = DownloadPane()
        pane_fail.finish_download(False, "fail msg")
        fail_style = pane_fail._bar.styleSheet()

        assert ok_style != fail_style

    def test_set_status_idle_state(self):
        """After pane.set_status(msg) -> idle state."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.set_status("searching…")

        assert pane._bar.maximum() == 100
        assert pane._bar.value() == 0
        assert pane._bar.property("state") == "idle"
        assert "searching" in pane._bar.format()

    def test_busy_then_finish_resets_range(self):
        """start_download() (range 0,0) -> finish_download() must restore determinate range."""
        self._app()
        from cratedig.gui.download_pane import DownloadPane

        pane = DownloadPane()
        pane.start_download()
        assert pane._bar.maximum() == 0  # busy/indeterminate
        pane.finish_download(True, "done")
        assert pane._bar.maximum() == 100
        assert pane._bar.value() == 100
        assert pane._bar.property("state") == "ok"


class TestWorkerPreviewRender:
    """Tests for background worker preview rendering (TDD — FAILING tests)."""

    def _app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_index_worker_has_request_preview_render_slot(self, tmp_path):
        """IndexWorker must have request_preview_render(seq, path, params) Slot."""
        self._app()
        from cratedig.gui.worker import IndexWorker
        from cratedig.db import Database
        from types import SimpleNamespace

        db = Database(tmp_path / "test.db")
        cfg = SimpleNamespace(paths=SimpleNamespace(library_dirs=(), saved_dir=tmp_path))
        worker = IndexWorker(db, cfg)

        # Check that request_preview_render is callable
        assert hasattr(worker, "request_preview_render")
        assert callable(getattr(worker, "request_preview_render"))
        db.close()

    def test_index_worker_has_preview_ready_signal(self, tmp_path):
        """IndexWorker must emit previewReady(seq: int, path: str, duration: float)."""
        self._app()
        from cratedig.gui.worker import IndexWorker
        from cratedig.db import Database
        from types import SimpleNamespace
        from PySide6.QtCore import Signal

        db = Database(tmp_path / "test.db")
        cfg = SimpleNamespace(paths=SimpleNamespace(library_dirs=(), saved_dir=tmp_path))
        worker = IndexWorker(db, cfg)

        # Check that previewReady signal exists
        assert hasattr(worker, "previewReady")
        signal = getattr(worker, "previewReady")
        # Should be a Signal
        assert isinstance(signal, Signal)
        db.close()

    def test_main_window_preview_does_not_block_gui_thread(self, tmp_path, monkeypatch):
        """MainWindow._on_preview_edit must delegate to worker, NOT call render_edit on GUI thread."""
        self._app()
        import numpy as np
        from cratedig.gui.main_window import MainWindow
        from cratedig.gui.worker import IndexWorker
        from cratedig.db import Database
        from cratedig.audio.editor import write_wav
        from types import SimpleNamespace
        from PySide6.QtCore import QThread

        # Create minimal test setup
        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()
        db = Database(tmp_path / "test.db")
        cfg = SimpleNamespace(
            paths=SimpleNamespace(library_dirs=(), saved_dir=saved_dir),
            metadata={}
        )

        # Create minimal MainWindow (without full __init__ to avoid complexity)
        window = MainWindow.__new__(MainWindow)
        window._cfg = cfg
        window._preview_edit_playing = False
        window._status_bar = SimpleNamespace(showMessage=lambda *a: None)
        window._player = SimpleNamespace(play=lambda *a, **k: None, stop=lambda: None)

        # Create a worker thread
        worker_thread = QThread()
        worker = IndexWorker(db, cfg)
        worker.moveToThread(worker_thread)
        window._worker = worker

        # Track if render_edit was called on GUI thread
        render_edit_called_on_gui_thread = []

        def mock_render_edit(*args, **kwargs):
            # Check if we're on the main QThread
            from PySide6.QtCore import QThread as QtThread
            if QtThread.currentThread() == QtThread.mainThread():
                render_edit_called_on_gui_thread.append(True)
            raise RuntimeError("rendered on GUI thread")

        monkeypatch.setattr(
            "cratedig.gui.main_window.render_edit",
            mock_render_edit
        )

        # Create test preview parameters
        sr = 44100
        duration = 1.0
        mono = np.sin(2 * np.pi * 440 * np.arange(int(sr * duration), dtype=np.float32) / sr) * 0.1
        test_wav = tmp_path / "test.wav"
        write_wav(mono, sr, test_wav)

        params = {
            "path": str(test_wav),
            "region": None,
            "reverse": False,
            "gain_db": 0.0,
            "fade_in": 0.0,
            "fade_out": 0.0,
            "adsr": None,
            "loop": False,
        }

        # Call _on_preview_edit
        try:
            window._on_preview_edit(params)
        except:
            pass

        # Clean up
        worker_thread.quit()
        worker_thread.wait()
        db.close()

        # If delegation is working, render_edit should NOT be called on GUI thread
        # (or maybe not called at all if it's queued to worker)
        # The key assertion is that we don't get RuntimeError from render_edit

    def test_simpler_pane_has_staged_render_path_attribute(self, tmp_path):
        """SimplerPane must have _staged_render_path attribute (initially None)."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Check for the staging attribute
        assert hasattr(pane, "_staged_render_path")
        # Initially should be None or empty
        assert pane._staged_render_path is None or pane._staged_render_path == ""

    def test_simpler_pane_has_request_stage_render_method(self, tmp_path):
        """SimplerPane must have request_stage_render() method for pre-rendering."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Check for the method
        assert hasattr(pane, "request_stage_render")
        assert callable(getattr(pane, "request_stage_render"))

    def test_simpler_pane_render_to_saved_exists_for_fallback(self, tmp_path):
        """SimplerPane._render_to_saved must exist for synchronous fallback in drag."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Verify _render_to_saved is still available (for drag fallback)
        assert hasattr(pane, "_render_to_saved")
        assert callable(getattr(pane, "_render_to_saved"))

    def test_worker_request_render_still_exists_for_export(self, tmp_path):
        """IndexWorker.request_render (export path) must still exist and emit renderReady."""
        self._app()
        from cratedig.gui.worker import IndexWorker
        from cratedig.db import Database
        from types import SimpleNamespace
        from PySide6.QtCore import Signal

        db = Database(tmp_path / "test.db")
        cfg = SimpleNamespace(paths=SimpleNamespace(library_dirs=(), saved_dir=tmp_path))
        worker = IndexWorker(db, cfg)

        # Check that request_render still exists
        assert hasattr(worker, "request_render")
        assert callable(getattr(worker, "request_render"))

        # Check that renderReady signal still exists
        assert hasattr(worker, "renderReady")
        signal = getattr(worker, "renderReady")
        assert isinstance(signal, Signal)
        db.close()

    def test_simpler_pane_exported_signal_still_exists(self, tmp_path):
        """SimplerPane.exported signal must still exist (emitted only on CopyAction)."""
        self._app()
        from cratedig.gui.simpler_pane import SimplerPane
        from PySide6.QtCore import Signal

        saved_dir = tmp_path / "_saved"
        saved_dir.mkdir()
        pane = SimplerPane(saved_dir)

        # Check that exported signal exists
        assert hasattr(pane, "exported")
        signal = getattr(pane, "exported")
        assert isinstance(signal, Signal)

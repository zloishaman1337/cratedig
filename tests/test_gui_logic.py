"""Tests for cratedig.gui.logic module - pure GUI logic functions."""

import math

import numpy as np
import pytest

from cratedig.db.models import Sample
from cratedig.gui.logic import compute_peaks, hit_rows, tree_rows, is_sample_favorite
from cratedig.sources.base import SearchHit
from cratedig.tui.browser import FolderNode


def _make_sample(sample_id: int, filename: str) -> Sample:
    """Minimal Sample factory for testing."""
    return Sample(id=sample_id, path=f"/test/{filename}", filename=filename)


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

    def test_empty_nodes_empty_favorites_returns_favorites_root_only(self):
        """Empty input should return exactly one row: the ★ Favorites root with no children."""
        nodes = {}
        favorites = []

        result = tree_rows(nodes, favorites)

        # Should have exactly one row: the ★ Favorites root
        assert len(result) == 1

        parent_key, key, label, is_favorites_branch = result[0]
        assert parent_key is None
        assert key == "__favorites__"
        assert label == "★ Favorites"
        assert is_favorites_branch is True

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

        # Should have 2 rows: root + 1 child
        assert len(result) == 2

        # First row: ★ Favorites root
        assert result[0] == (None, "__favorites__", "★ Favorites", True)

        # Second row: favorite child
        parent_key, key, label, is_fav_branch = result[1]
        assert parent_key == "__favorites__"
        assert key == "fav:1"
        assert label == "kick.wav"
        assert is_fav_branch is True

    def test_multiple_favorites_in_order(self):
        """Multiple favorites should appear in order after root."""
        nodes = {}
        fav1 = _make_sample(10, "snare.wav")
        fav2 = _make_sample(20, "kick.wav")
        favorites = [fav1, fav2]

        result = tree_rows(nodes, favorites)

        # Should have 3 rows: root + 2 children
        assert len(result) == 3

        # First row: root
        assert result[0][1] == "__favorites__"

        # Second and third: favorites in order
        assert result[1] == ("__favorites__", "fav:10", "snare.wav", True)
        assert result[2] == ("__favorites__", "fav:20", "kick.wav", True)

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

        # Should have 4 rows: ★ Favorites root + 3 folder rows
        assert len(result) == 4

        # First row: ★ Favorites root
        assert result[0][1] == "__favorites__"

        # Folder rows should follow, sorted by key
        folder_rows = result[1:]
        keys = [row[1] for row in folder_rows]
        assert keys == ["packs", "packs/bass", "packs/drums"]

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

        # Skip ★ Favorites root and check folder order
        folder_rows = result[1:]
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

        # Find folder rows (skip ★ Favorites root at index 0)
        packs_row = result[1]
        drums_row = result[2]

        assert packs_row[0] is None  # packs is top-level
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

        # Find drums row (skip ★ Favorites root)
        drums_row = result[1]
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

        # Find packs row (skip ★ Favorites root)
        packs_row = result[1]
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

        # Fourth row should be folder
        assert result[3][1] == "packs"
        assert result[3][3] is False  # is_favorites_branch

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

        # Expected order: ★ root, fav1, packs, packs/drums
        keys = [row[1] for row in result]
        assert keys == ["__favorites__", "fav:100", "packs", "packs/drums"]

        # Check is_favorites_branch flags
        assert result[0][3] is True  # ★ root
        assert result[1][3] is True  # fav1
        assert result[2][3] is False  # packs
        assert result[3][3] is False  # packs/drums

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

        # Skip ★ Favorites root and check folder order
        folder_keys = [row[1] for row in result[1:]]
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
        # 4. packs
        # 5. packs/drums
        # 6. packs/drums/kicks
        keys = [row[1] for row in result]
        assert keys == [
            "__favorites__",
            "fav:10",
            "fav:20",
            "packs",
            "packs/drums",
            "packs/drums/kicks",
        ]

        # Verify parent_key for each row
        assert result[0][0] is None  # ★ root
        assert result[1][0] == "__favorites__"  # fav:10
        assert result[2][0] == "__favorites__"  # fav:20
        assert result[3][0] is None  # packs (top-level)
        assert result[4][0] == "packs"  # packs/drums
        assert result[5][0] == "packs/drums"  # packs/drums/kicks

        # Verify is_favorites_branch
        is_fav_flags = [row[3] for row in result]
        assert is_fav_flags == [True, True, True, False, False, False]


class TestHitRows:
    """Test hit_rows(hits) -> list of (title, artist, duration, backend) tuples."""

    def test_empty(self):
        assert hit_rows([]) == []

    def test_full_hit_formats_duration_one_decimal(self):
        hit = SearchHit(
            backend="freesound", id="123", title="Kick", artist="Foo",
            duration_sec=2.5,
        )
        assert hit_rows([hit]) == [("Kick", "Foo", "2.5", "freesound")]

    def test_missing_duration_shows_dash(self):
        hit = SearchHit(backend="yandex", id="x", title="Track", artist="Bar")
        assert hit_rows([hit]) == [("Track", "Bar", "-", "yandex")]

    def test_order_preserved_for_row_index_mapping(self):
        hits = [
            SearchHit(backend="a", id="1", title="One"),
            SearchHit(backend="b", id="2", title="Two"),
        ]
        rows = hit_rows(hits)
        assert [r[0] for r in rows] == ["One", "Two"]
        assert [r[3] for r in rows] == ["a", "b"]


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

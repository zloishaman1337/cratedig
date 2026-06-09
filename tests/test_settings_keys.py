"""Tests for cratedig.gui.settings_tabs._keys (QSettings schema constants + defaults).

These are FAILING tests; they define the contract that _keys.py must satisfy.
"""

from __future__ import annotations


class TestSettingsKeysConstants:
    """Test that _keys.py exports all required QSettings key constants."""

    def test_auto_preview_on_select_constant_has_correct_key(self):
        """AUTO_PREVIEW_ON_SELECT constant equals "playback/auto_preview_on_select"."""
        from cratedig.gui.settings_tabs._keys import AUTO_PREVIEW_ON_SELECT

        assert AUTO_PREVIEW_ON_SELECT == "playback/auto_preview_on_select"

    def test_stop_before_preview_constant_has_correct_key(self):
        """STOP_BEFORE_PREVIEW constant equals "playback/stop_before_preview"."""
        from cratedig.gui.settings_tabs._keys import STOP_BEFORE_PREVIEW

        assert STOP_BEFORE_PREVIEW == "playback/stop_before_preview"

    def test_loop_edited_by_default_constant_has_correct_key(self):
        """LOOP_EDITED_BY_DEFAULT constant equals "playback/loop_edited_by_default"."""
        from cratedig.gui.settings_tabs._keys import LOOP_EDITED_BY_DEFAULT

        assert LOOP_EDITED_BY_DEFAULT == "playback/loop_edited_by_default"

    def test_ab_loudness_leveling_constant_has_correct_key(self):
        """AB_LOUDNESS_LEVELING constant equals "playback/ab_loudness_leveling"."""
        from cratedig.gui.settings_tabs._keys import AB_LOUDNESS_LEVELING

        assert AB_LOUDNESS_LEVELING == "playback/ab_loudness_leveling"

    def test_preview_download_on_row_select_constant_has_correct_key(self):
        """PREVIEW_DOWNLOAD_ON_ROW_SELECT constant equals "playback/preview_download_on_row_select"."""
        from cratedig.gui.settings_tabs._keys import PREVIEW_DOWNLOAD_ON_ROW_SELECT

        assert PREVIEW_DOWNLOAD_ON_ROW_SELECT == "playback/preview_download_on_row_select"

    def test_show_tags_column_constant_has_correct_key(self):
        """SHOW_TAGS_COLUMN constant equals "browser/show_tags_column"."""
        from cratedig.gui.settings_tabs._keys import SHOW_TAGS_COLUMN

        assert SHOW_TAGS_COLUMN == "browser/show_tags_column"

    def test_remember_column_widths_constant_has_correct_key(self):
        """REMEMBER_COLUMN_WIDTHS constant equals "browser/remember_column_widths"."""
        from cratedig.gui.settings_tabs._keys import REMEMBER_COLUMN_WIDTHS

        assert REMEMBER_COLUMN_WIDTHS == "browser/remember_column_widths"

    def test_remember_column_visibility_constant_has_correct_key(self):
        """REMEMBER_COLUMN_VISIBILITY constant equals "browser/remember_column_visibility"."""
        from cratedig.gui.settings_tabs._keys import REMEMBER_COLUMN_VISIBILITY

        assert REMEMBER_COLUMN_VISIBILITY == "browser/remember_column_visibility"

    def test_remember_window_geometry_constant_has_correct_key(self):
        """REMEMBER_WINDOW_GEOMETRY constant equals "browser/remember_window_geometry"."""
        from cratedig.gui.settings_tabs._keys import REMEMBER_WINDOW_GEOMETRY

        assert REMEMBER_WINDOW_GEOMETRY == "browser/remember_window_geometry"

    def test_remember_splitter_sizes_constant_has_correct_key(self):
        """REMEMBER_SPLITTER_SIZES constant equals "browser/remember_splitter_sizes"."""
        from cratedig.gui.settings_tabs._keys import REMEMBER_SPLITTER_SIZES

        assert REMEMBER_SPLITTER_SIZES == "browser/remember_splitter_sizes"

    def test_expand_tree_on_load_constant_has_correct_key(self):
        """EXPAND_TREE_ON_LOAD constant equals "browser/expand_tree_on_load"."""
        from cratedig.gui.settings_tabs._keys import EXPAND_TREE_ON_LOAD

        assert EXPAND_TREE_ON_LOAD == "browser/expand_tree_on_load"

    def test_restore_last_folder_constant_has_correct_key(self):
        """RESTORE_LAST_FOLDER constant equals "browser/restore_last_folder"."""
        from cratedig.gui.settings_tabs._keys import RESTORE_LAST_FOLDER

        assert RESTORE_LAST_FOLDER == "browser/restore_last_folder"

    def test_recent_folders_constant_has_correct_key(self):
        """RECENT_FOLDERS constant equals "browser/recent_folders"."""
        from cratedig.gui.settings_tabs._keys import RECENT_FOLDERS

        assert RECENT_FOLDERS == "browser/recent_folders"

    def test_recent_folders_max_constant_has_correct_key(self):
        """RECENT_FOLDERS_MAX constant equals "browser/recent_folders_max"."""
        from cratedig.gui.settings_tabs._keys import RECENT_FOLDERS_MAX

        assert RECENT_FOLDERS_MAX == "browser/recent_folders_max"

    def test_default_similar_aspects_constant_has_correct_key(self):
        """DEFAULT_SIMILAR_ASPECTS constant equals "search/default_similar_aspects"."""
        from cratedig.gui.settings_tabs._keys import DEFAULT_SIMILAR_ASPECTS

        assert DEFAULT_SIMILAR_ASPECTS == "search/default_similar_aspects"

    def test_similar_results_count_constant_has_correct_key(self):
        """SIMILAR_RESULTS_COUNT constant equals "search/similar_results_count"."""
        from cratedig.gui.settings_tabs._keys import SIMILAR_RESULTS_COUNT

        assert SIMILAR_RESULTS_COUNT == "search/similar_results_count"

    def test_download_search_limit_constant_has_correct_key(self):
        """DOWNLOAD_SEARCH_LIMIT constant equals "search/download_search_limit"."""
        from cratedig.gui.settings_tabs._keys import DOWNLOAD_SEARCH_LIMIT

        assert DOWNLOAD_SEARCH_LIMIT == "search/download_search_limit"

    def test_default_download_mode_constant_has_correct_key(self):
        """DEFAULT_DOWNLOAD_MODE constant equals "search/default_download_mode"."""
        from cratedig.gui.settings_tabs._keys import DEFAULT_DOWNLOAD_MODE

        assert DEFAULT_DOWNLOAD_MODE == "search/default_download_mode"

    def test_confirm_delete_constant_has_correct_key(self):
        """CONFIRM_DELETE constant equals "safety/confirm_delete"."""
        from cratedig.gui.settings_tabs._keys import CONFIRM_DELETE

        assert CONFIRM_DELETE == "safety/confirm_delete"

    def test_recycle_bin_for_saved_constant_has_correct_key(self):
        """RECYCLE_BIN_FOR_SAVED constant equals "safety/recycle_bin_for_saved"."""
        from cratedig.gui.settings_tabs._keys import RECYCLE_BIN_FOR_SAVED

        assert RECYCLE_BIN_FOR_SAVED == "safety/recycle_bin_for_saved"

    def test_confirm_dup_resolver_deletes_constant_has_correct_key(self):
        """CONFIRM_DUP_RESOLVER_DELETES constant equals "safety/confirm_dup_resolver_deletes"."""
        from cratedig.gui.settings_tabs._keys import CONFIRM_DUP_RESOLVER_DELETES

        assert CONFIRM_DUP_RESOLVER_DELETES == "safety/confirm_dup_resolver_deletes"

    def test_auto_refresh_health_on_open_constant_has_correct_key(self):
        """AUTO_REFRESH_HEALTH_ON_OPEN constant equals "safety/auto_refresh_health_on_open"."""
        from cratedig.gui.settings_tabs._keys import AUTO_REFRESH_HEALTH_ON_OPEN

        assert AUTO_REFRESH_HEALTH_ON_OPEN == "safety/auto_refresh_health_on_open"


class TestSettingsKeysDefaults:
    """Test that _keys.py exports DEFAULTS dict with correct values per design §3.6 overrides."""

    def test_defaults_dict_exists_and_is_dict(self):
        """DEFAULTS is a dict."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert isinstance(DEFAULTS, dict)

    def test_defaults_contains_all_required_keys(self):
        """DEFAULTS contains entries for all 18+ keys from §3.6."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        expected_keys = {
            "playback/auto_preview_on_select",
            "playback/stop_before_preview",
            "playback/loop_edited_by_default",
            "playback/ab_loudness_leveling",
            "playback/preview_download_on_row_select",
            "browser/show_tags_column",
            "browser/remember_column_widths",
            "browser/remember_column_visibility",
            "browser/remember_window_geometry",
            "browser/remember_splitter_sizes",
            "browser/expand_tree_on_load",
            "browser/restore_last_folder",
            "browser/recent_folders",
            "browser/recent_folders_max",
            "search/default_similar_aspects",
            "search/similar_results_count",
            "search/download_search_limit",
            "search/default_download_mode",
            "safety/confirm_delete",
            "safety/recycle_bin_for_saved",
            "safety/confirm_dup_resolver_deletes",
            "safety/auto_refresh_health_on_open",
        }
        assert expected_keys.issubset(DEFAULTS.keys())

    def test_defaults_auto_preview_on_select_is_true(self):
        """playback/auto_preview_on_select defaults to True (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["playback/auto_preview_on_select"] is True

    def test_defaults_stop_before_preview_is_true(self):
        """playback/stop_before_preview defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["playback/stop_before_preview"] is True

    def test_defaults_loop_edited_by_default_is_false(self):
        """playback/loop_edited_by_default defaults to False (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["playback/loop_edited_by_default"] is False

    def test_defaults_ab_loudness_leveling_is_false(self):
        """playback/ab_loudness_leveling defaults to False (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["playback/ab_loudness_leveling"] is False

    def test_defaults_preview_download_on_row_select_is_false(self):
        """playback/preview_download_on_row_select defaults to False (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["playback/preview_download_on_row_select"] is False

    def test_defaults_show_tags_column_is_true(self):
        """browser/show_tags_column defaults to True (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/show_tags_column"] is True

    def test_defaults_remember_column_widths_is_true(self):
        """browser/remember_column_widths defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/remember_column_widths"] is True

    def test_defaults_remember_column_visibility_is_true(self):
        """browser/remember_column_visibility defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/remember_column_visibility"] is True

    def test_defaults_remember_window_geometry_is_true(self):
        """browser/remember_window_geometry defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/remember_window_geometry"] is True

    def test_defaults_remember_splitter_sizes_is_true(self):
        """browser/remember_splitter_sizes defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/remember_splitter_sizes"] is True

    def test_defaults_expand_tree_on_load_is_false(self):
        """browser/expand_tree_on_load defaults to False (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/expand_tree_on_load"] is False

    def test_defaults_restore_last_folder_is_true(self):
        """browser/restore_last_folder defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/restore_last_folder"] is True

    def test_defaults_recent_folders_is_empty_list(self):
        """browser/recent_folders defaults to [] (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/recent_folders"] == []

    def test_defaults_recent_folders_max_is_10(self):
        """browser/recent_folders_max defaults to 10 (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["browser/recent_folders_max"] == 10

    def test_defaults_default_similar_aspects_is_overall_only(self):
        """search/default_similar_aspects defaults to ["Overall"] (per design override).

        This overrides the design default of ["timbre","rhythm"] to match current behavior
        (main_window.py:139 only checks Overall).
        """
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["search/default_similar_aspects"] == ["Overall"]

    def test_defaults_similar_results_count_is_30(self):
        """search/similar_results_count defaults to 30 (per design override).

        This overrides the design default of 50 to match main_window.py:694.
        """
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["search/similar_results_count"] == 30

    def test_defaults_download_search_limit_is_20(self):
        """search/download_search_limit defaults to 20 (per design override).

        This overrides the design default of 25 to match main_window.py:671.
        """
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["search/download_search_limit"] == 20

    def test_defaults_default_download_mode_is_samples(self):
        """search/default_download_mode defaults to "samples" (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["search/default_download_mode"] == "samples"

    def test_defaults_confirm_delete_is_true(self):
        """safety/confirm_delete defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["safety/confirm_delete"] is True

    def test_defaults_recycle_bin_for_saved_is_true(self):
        """safety/recycle_bin_for_saved defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["safety/recycle_bin_for_saved"] is True

    def test_defaults_confirm_dup_resolver_deletes_is_true(self):
        """safety/confirm_dup_resolver_deletes defaults to True (per design §3.6)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["safety/confirm_dup_resolver_deletes"] is True

    def test_defaults_auto_refresh_health_on_open_is_false(self):
        """safety/auto_refresh_health_on_open defaults to False (per design override)."""
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        assert DEFAULTS["safety/auto_refresh_health_on_open"] is False

    def test_all_constants_are_keys_in_defaults(self):
        """Every exported constant (playback/, browser/, search/, safety/) is in DEFAULTS."""
        from cratedig.gui.settings_tabs import _keys
        from cratedig.gui.settings_tabs._keys import DEFAULTS

        # Gather all module-level string constants that look like keys (contain /)
        key_constants = {
            getattr(_keys, name)
            for name in dir(_keys)
            if not name.startswith("_")
            and isinstance(getattr(_keys, name), str)
            and "/" in getattr(_keys, name)
        }

        # Remove special constants like module docstrings
        key_constants = {k for k in key_constants if k.startswith(("playback/", "browser/", "search/", "safety/"))}

        # All key constants must be in DEFAULTS
        for key in key_constants:
            assert key in DEFAULTS, f"Constant key {key!r} is not in DEFAULTS"


class TestSettingsKeysTypes:
    """Test that _keys.py optionally exports TYPES mapping (if implemented)."""

    def test_types_dict_exists_if_present(self):
        """TYPES dict is optional but if present should map keys → type objects."""
        try:
            from cratedig.gui.settings_tabs._keys import TYPES

            assert isinstance(TYPES, dict)
            # All keys in TYPES should be full QSettings keys
            for key in TYPES.keys():
                assert "/" in key, f"TYPES key {key!r} does not look like a QSettings key"
        except ImportError:
            # TYPES is optional
            pass

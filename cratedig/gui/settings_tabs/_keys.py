"""QSettings key constants and defaults for cratedig preferences."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# playback/
# ---------------------------------------------------------------------------

AUTO_PREVIEW_ON_SELECT = "playback/auto_preview_on_select"
STOP_BEFORE_PREVIEW = "playback/stop_before_preview"
LOOP_EDITED_BY_DEFAULT = "playback/loop_edited_by_default"
AB_LOUDNESS_LEVELING = "playback/ab_loudness_leveling"
PREVIEW_DOWNLOAD_ON_ROW_SELECT = "playback/preview_download_on_row_select"

# ---------------------------------------------------------------------------
# browser/
# ---------------------------------------------------------------------------

SHOW_TAGS_COLUMN = "browser/show_tags_column"
REMEMBER_COLUMN_WIDTHS = "browser/remember_column_widths"
REMEMBER_COLUMN_VISIBILITY = "browser/remember_column_visibility"
REMEMBER_WINDOW_GEOMETRY = "browser/remember_window_geometry"
REMEMBER_SPLITTER_SIZES = "browser/remember_splitter_sizes"
EXPAND_TREE_ON_LOAD = "browser/expand_tree_on_load"
RESTORE_LAST_FOLDER = "browser/restore_last_folder"
RECENT_FOLDERS = "browser/recent_folders"
RECENT_FOLDERS_MAX = "browser/recent_folders_max"
LIBRARY_LOAD_LIMIT = "browser/library_load_limit"  # max samples loaded into the tree; 0 = all

# ---------------------------------------------------------------------------
# search/
# ---------------------------------------------------------------------------

DEFAULT_SIMILAR_ASPECTS = "search/default_similar_aspects"
SIMILAR_RESULTS_COUNT = "search/similar_results_count"
DOWNLOAD_SEARCH_LIMIT = "search/download_search_limit"
DEFAULT_DOWNLOAD_MODE = "search/default_download_mode"

# ---------------------------------------------------------------------------
# safety/
# ---------------------------------------------------------------------------

CONFIRM_DELETE = "safety/confirm_delete"
RECYCLE_BIN_FOR_SAVED = "safety/recycle_bin_for_saved"
CONFIRM_DUP_RESOLVER_DELETES = "safety/confirm_dup_resolver_deletes"
AUTO_REFRESH_HEALTH_ON_OPEN = "safety/auto_refresh_health_on_open"

# ---------------------------------------------------------------------------
# DEFAULTS — single source of truth (overrides per design §3.6 critical defaults)
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, object] = {
    AUTO_PREVIEW_ON_SELECT: True,
    STOP_BEFORE_PREVIEW: True,
    LOOP_EDITED_BY_DEFAULT: False,
    AB_LOUDNESS_LEVELING: False,
    PREVIEW_DOWNLOAD_ON_ROW_SELECT: False,
    SHOW_TAGS_COLUMN: True,
    REMEMBER_COLUMN_WIDTHS: True,
    REMEMBER_COLUMN_VISIBILITY: True,
    REMEMBER_WINDOW_GEOMETRY: True,
    REMEMBER_SPLITTER_SIZES: True,
    EXPAND_TREE_ON_LOAD: False,
    RESTORE_LAST_FOLDER: True,
    RECENT_FOLDERS: [],
    RECENT_FOLDERS_MAX: 10,
    LIBRARY_LOAD_LIMIT: 0,
    DEFAULT_SIMILAR_ASPECTS: ["Overall"],
    SIMILAR_RESULTS_COUNT: 30,
    DOWNLOAD_SEARCH_LIMIT: 20,
    DEFAULT_DOWNLOAD_MODE: "samples",
    CONFIRM_DELETE: True,
    RECYCLE_BIN_FOR_SAVED: True,
    CONFIRM_DUP_RESOLVER_DELETES: True,
    AUTO_REFRESH_HEALTH_ON_OPEN: False,
}

# ---------------------------------------------------------------------------
# TYPES — QSettings.value type hints
# ---------------------------------------------------------------------------

TYPES: dict[str, type] = {
    AUTO_PREVIEW_ON_SELECT: bool,
    STOP_BEFORE_PREVIEW: bool,
    LOOP_EDITED_BY_DEFAULT: bool,
    AB_LOUDNESS_LEVELING: bool,
    PREVIEW_DOWNLOAD_ON_ROW_SELECT: bool,
    SHOW_TAGS_COLUMN: bool,
    REMEMBER_COLUMN_WIDTHS: bool,
    REMEMBER_COLUMN_VISIBILITY: bool,
    REMEMBER_WINDOW_GEOMETRY: bool,
    REMEMBER_SPLITTER_SIZES: bool,
    EXPAND_TREE_ON_LOAD: bool,
    RESTORE_LAST_FOLDER: bool,
    RECENT_FOLDERS: list,
    RECENT_FOLDERS_MAX: int,
    LIBRARY_LOAD_LIMIT: int,
    DEFAULT_SIMILAR_ASPECTS: list,
    SIMILAR_RESULTS_COUNT: int,
    DOWNLOAD_SEARCH_LIMIT: int,
    DEFAULT_DOWNLOAD_MODE: str,
    CONFIRM_DELETE: bool,
    RECYCLE_BIN_FOR_SAVED: bool,
    CONFIRM_DUP_RESOLVER_DELETES: bool,
    AUTO_REFRESH_HEALTH_ON_OPEN: bool,
}

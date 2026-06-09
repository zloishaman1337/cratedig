"""Settings tabs package — re-exports the three tab classes."""

from .preferences_tab import PreferencesTab
from .project_config_tab import ProjectConfigTab
from .paths_tab import PathsTab

__all__ = ["PreferencesTab", "ProjectConfigTab", "PathsTab"]

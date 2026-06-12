"""User-selectable conversion options (the modal's checkboxes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvertOptions:
    tempo: bool = True
    tracks: bool = True
    copy_samples: bool = True
    plugin_names: bool = True
    effect_names: bool = True

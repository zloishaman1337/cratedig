"""Extension → parser dispatch for the unified Project Checker.

Single source of truth mapping a project file's extension to the right parser +
normalizer. The Ableton ``.als`` parser already returns the rich checker schema, so
it carries ``normalizer=None``; the binary/best-effort formats return a flat dict
that ``common.to_checker_data`` adapts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..als.parser import parse_als
from .bitwig import parse_bwproject
from .common import to_checker_data
from .flstudio import parse_flp
from .logic import parse_logicx
from .nuendo import parse_npr
from .protools import parse_ptx
from .reaper import parse_rpp
from .studioone import parse_song


@dataclass(frozen=True)
class FormatSpec:
    name: str  # human DAW name shown in the panel
    parser: Callable[[str], dict]
    normalizer: Callable[[dict, str], dict] | None  # None => parser yields checker schema
    bare_is_native: bool  # how a bare plugin name badges (DAW-native vs 3rd-party)


# Extension (lowercase, incl. dot) → spec. Cubase ``.cpr`` reuses the Nuendo RIFF
# parser (same NUNDROOT tree). Order matters only for the suffix scan in
# ``parser_for``: longer/more-specific suffixes are safe because ``.rpp-bak`` does
# not end with ``.rpp``.
REGISTRY: dict[str, FormatSpec] = {
    ".als": FormatSpec("Ableton Live", parse_als, None, True),
    ".bwproject": FormatSpec("Bitwig", parse_bwproject, to_checker_data, True),
    ".npr": FormatSpec("Nuendo", parse_npr, to_checker_data, False),
    ".cpr": FormatSpec("Cubase", parse_npr, to_checker_data, False),
    ".rpp": FormatSpec("Reaper", parse_rpp, to_checker_data, False),
    ".rpp-bak": FormatSpec("Reaper", parse_rpp, to_checker_data, False),
    ".flp": FormatSpec("FL Studio", parse_flp, to_checker_data, True),
    ".song": FormatSpec("Studio One", parse_song, to_checker_data, False),
    ".logicx": FormatSpec("Logic Pro", parse_logicx, to_checker_data, False),
    ".ptx": FormatSpec("Pro Tools", parse_ptx, to_checker_data, False),
    ".ptf": FormatSpec("Pro Tools", parse_ptx, to_checker_data, False),
}

ALL_EXTS: tuple[str, ...] = tuple(REGISTRY.keys())


def file_filter() -> str:
    """A Qt file-dialog filter string covering every supported project extension."""
    globs = " ".join(f"*{ext}" for ext in ALL_EXTS)
    return f"DAW project ({globs})"


def parser_for(path: str | Path) -> FormatSpec | None:
    """Return the :class:`FormatSpec` for ``path`` by extension, or None if unsupported.

    ``.logicx`` projects are directories (bundles); matching on the trailing suffix
    handles both files and bundle dirs. ``.rpp-bak`` is matched before ``.rpp`` would
    apply because a ``-bak`` name does not end with ``.rpp``.
    """
    name = Path(path).name.lower()
    for ext, spec in REGISTRY.items():
        if name.endswith(ext):
            return spec
    return None

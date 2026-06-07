"""Pure duplicate-resolution logic for cratedig.

No DB calls, no filesystem mutation.  All functions are deterministic and
side-effect-free; the GUI/worker performs actual deletion via request_delete.

Keep heuristic (first rule that breaks the tie wins):
  1. Non-edit over edit: a sample whose source != 'edit' AND whose path is not
     under saved_dir beats one that is a generated edit.  Generated chunks are
     the disposable copy — the original library file is always preferred.
  2. Analyzed over unanalyzed: analyzed_at is not None.
  3. Richer metadata: category or instrument_class is not None.
  4. Shortest path, then lexicographically smallest path as a stable tiebreak.

Protected-edit safety rule:
  Any sample in the *remove* set that is a generated edit (source == 'edit' or
  path under saved_dir) is also listed in ResolutionPlan.protected so the GUI
  can warn before performing an irreversible direct-unlink.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from .db.models import Sample


# ---------------------------------------------------------------------------
# Predicate
# ---------------------------------------------------------------------------

def is_generated_edit(sample: Sample, saved_dir: str | Path | None = None) -> bool:
    """Return True if sample is a generated edit or lives under saved_dir."""
    if sample.source == "edit":
        return True
    if saved_dir is not None:
        try:
            Path(sample.path).resolve().relative_to(Path(saved_dir).resolve())
            return True
        except (OSError, ValueError):
            pass
    return False


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_duplicates(samples: list[Sample]) -> list[list[Sample]]:
    """Group flat list by file_hash; return only groups of size >= 2.

    Rows with a falsy file_hash are skipped.  Output is deterministic:
    groups are ordered by file_hash, members within each group by path.
    """
    filtered = [s for s in samples if s.file_hash]
    sorted_by_hash = sorted(filtered, key=lambda s: (s.file_hash, s.path))
    groups: list[list[Sample]] = []
    for _hash, members in groupby(sorted_by_hash, key=lambda s: s.file_hash):
        group = list(members)
        if len(group) >= 2:
            groups.append(group)
    return groups


# ---------------------------------------------------------------------------
# Best-pick heuristic
# ---------------------------------------------------------------------------

def _sort_key(sample: Sample, saved_dir: str | Path | None) -> tuple:
    """Lower tuple = better candidate (sort ascending, take first)."""
    edit_score = 1 if is_generated_edit(sample, saved_dir) else 0
    analyzed_score = 0 if sample.analyzed_at is not None else 1
    metadata_score = 0 if (sample.category is not None or sample.instrument_class is not None) else 1
    path_len = len(sample.path)
    return (edit_score, analyzed_score, metadata_score, path_len, sample.path)


def pick_best(group: list[Sample], saved_dir: str | Path | None = None) -> Sample:
    """Return the keeper from a duplicate group using the documented heuristic.

    Never returns a generated-edit sample when a non-edit duplicate exists.
    """
    return min(group, key=lambda s: _sort_key(s, saved_dir))


# ---------------------------------------------------------------------------
# Resolution plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolutionPlan:
    """Describes what to keep and what to remove for one duplicate group.

    keep      -- the single Sample to retain.
    remove    -- all other members of the group (should be deleted).
    protected -- subset of remove whose members are generated edits; these
                 require extra confirmation before deletion because they will
                 be directly unlinked (not sent to the recycle bin).
    """

    keep: Sample
    remove: list[Sample]
    protected: list[Sample]


def plan_resolution(
    group: list[Sample],
    *,
    saved_dir: str | Path | None = None,
    keep: Sample | None = None,
) -> ResolutionPlan:
    """Build a ResolutionPlan for one duplicate group.

    If keep is not provided, pick_best() is used.  All other members become
    candidates for removal.  Those that are generated edits are also added to
    protected so the caller can surface a targeted warning.
    """
    keeper = keep if keep is not None else pick_best(group, saved_dir)
    remove = [s for s in group if s is not keeper]
    protected = [s for s in remove if is_generated_edit(s, saved_dir)]
    return ResolutionPlan(keep=keeper, remove=remove, protected=protected)


# ---------------------------------------------------------------------------
# Batch entry point
# ---------------------------------------------------------------------------

def plan_all(
    samples: list[Sample],
    *,
    saved_dir: str | Path | None = None,
) -> list[ResolutionPlan]:
    """Group samples by file_hash and produce a ResolutionPlan per group."""
    return [
        plan_resolution(group, saved_dir=saved_dir)
        for group in group_duplicates(samples)
    ]

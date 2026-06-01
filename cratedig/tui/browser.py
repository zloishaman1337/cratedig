"""Pure helpers for the TUI browse view folder tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..db.models import Sample


@dataclass
class FolderNode:
    name: str
    key: str
    parent_key: str | None
    children: dict[str, "FolderNode"] = field(default_factory=dict)
    samples: list[Sample] = field(default_factory=list)


def build_folder_tree(
    samples: list[Sample],
    roots: tuple[Path, ...],
) -> dict[str, FolderNode]:
    """Return a flat mapping of folder_key -> FolderNode from a list of Samples.

    folder_key uses slash-joined root-relative paths, root label first, e.g.
    "packs", "packs/drums".  The returned dict includes ALL ancestor nodes so
    callers can populate a Tree widget by iterating sorted keys.
    """
    nodes: dict[str, FolderNode] = {}
    resolved_roots = [r.resolve() for r in roots if str(r)]

    for sample in sorted(samples, key=lambda s: s.path.lower()):
        path = Path(sample.path)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path

        root_label = "Library"
        rel_parts: tuple[str, ...] = (path.name,)
        for root in resolved_roots:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            root_label = root.name or str(root)
            rel_parts = rel.parts
            break
        else:
            parent = path.parent
            root_label = parent.name or str(parent) or "Library"
            rel_parts = (path.name,)

        # Ensure root node exists
        if root_label not in nodes:
            nodes[root_label] = FolderNode(
                name=root_label,
                key=root_label,
                parent_key=None,
            )

        # Ensure all intermediate folder nodes exist
        current_key = root_label
        for depth, part in enumerate(rel_parts[:-1]):
            child_key = f"{current_key}/{part}"
            if child_key not in nodes:
                nodes[child_key] = FolderNode(
                    name=part,
                    key=child_key,
                    parent_key=current_key,
                )
                nodes[current_key].children[part] = nodes[child_key]
            current_key = child_key

        # Add the sample to its direct parent folder
        nodes[current_key].samples.append(sample)

    return nodes

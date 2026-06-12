"""Collect referenced sample files next to a converted project."""

from __future__ import annotations

import shutil
from pathlib import Path

from .ir import ProjectIR


def _scan_basenames(project_path: str | Path, max_files: int = 20_000) -> dict[str, Path]:
    """Map lowercased basename -> absolute path for files near the project.

    Mirrors ``projects_fmt.common.resolve_samples_on_disk``: bundle formats (Logic
    ``.logicx``) hand us the package directory; file formats hand us a file, so we
    scan its parent. Bounded by ``max_files`` against a hostile/huge tree.
    """
    p = Path(project_path).resolve()
    base = p if p.is_dir() else p.parent
    found: dict[str, Path] = {}
    if base.is_dir():
        seen = 0
        for f in base.rglob("*"):
            seen += 1
            if seen > max_files:
                break
            if f.is_file():
                found.setdefault(f.name.lower(), f)
    return found


def gather_samples(ir: ProjectIR, media_dir: str | Path) -> dict:
    """Copy ``ir.samples_found`` into ``media_dir``; return media map + missing list.

    ``media`` maps each copied basename to its path relative to ``media_dir.parent``
    (e.g. ``"media/kick.wav"``) so writers can reference the copied file. A basename
    that cannot be located on disk is reported in ``missing`` rather than copied.
    """
    media_dir = Path(media_dir)
    on_disk = _scan_basenames(ir.project_path)
    media: dict[str, str] = {}
    missing: list[str] = list(ir.samples_missing)

    for basename in ir.samples_found:
        src = on_disk.get(basename.lower())
        if src is None:
            missing.append(basename)
            continue
        media_dir.mkdir(parents=True, exist_ok=True)
        dest = media_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
        media[src.name] = f"{media_dir.name}/{src.name}"

    return {"media": media, "missing": sorted(set(missing))}

"""DAW→DAW project conversion.

Reads any supported project (via the existing parsers + the checker schema) into a
neutral :class:`~cratedig.convert.ir.ProjectIR`, then writes it out to a target DAW
format. The source parsers recover metadata only — tempo, track names/types,
referenced sample files, and plugin/effect NAMES — so conversion transfers exactly
that (plus optionally copies the referenced audio files). Plugin presets, automation,
MIDI notes and audio mixdowns are not present in the source and are not transferred.

Targets:
  * ``reaper``  — native ``.RPP`` (plain text; highest fidelity).
  * ``ableton`` — native ``.als`` (gzipped XML; best-effort, opens in Live 11+).
  * ``aaf``     — AAF interchange (importable by Cubase / Pro Tools / Logic / Reaper).
"""

from __future__ import annotations

from pathlib import Path

from .ir import ProjectIR, TrackIR, ir_from_checker_data
from .options import ConvertOptions
from .samples import gather_samples

TARGETS = ("reaper", "ableton", "aaf")
_EXT = {"reaper": ".rpp", "ableton": ".als", "aaf": ".aaf"}


def target_extension(target: str) -> str:
    return _EXT[target]


def convert_project(
    ir: ProjectIR, target: str, out_path: str | Path, options: ConvertOptions
) -> dict:
    """Write ``ir`` to ``out_path`` in ``target`` format. Returns a result summary.

    Copies referenced sample files into ``<out_dir>/media/`` when
    ``options.copy_samples`` is set, rewriting the writer's file references to the
    copied media. Returns ``{"out_path", "copied", "missing"}``.
    """
    if target not in TARGETS:
        raise ValueError(f"unknown convert target: {target!r}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    media: dict[str, str] = {}
    missing: list[str] = list(ir.samples_missing)
    if options.copy_samples:
        result = gather_samples(ir, out_path.parent / "media")
        media = result["media"]  # basename -> relative path under out dir
        missing = result["missing"]

    if target == "reaper":
        from .writers import reaper as writer
    elif target == "ableton":
        from .writers import ableton as writer
    else:
        from .writers import aaf as writer

    writer.write(ir, out_path, options, media)
    return {"out_path": str(out_path), "copied": sorted(media), "missing": missing}


__all__ = [
    "ProjectIR",
    "TrackIR",
    "ConvertOptions",
    "ir_from_checker_data",
    "convert_project",
    "target_extension",
    "gather_samples",
    "TARGETS",
]

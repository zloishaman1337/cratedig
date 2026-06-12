"""Neutral intermediate representation shared by every convert writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TrackIR:
    name: str
    kind: str  # "audio" | "midi" | "instrument" | "" (best-effort from source)
    instruments: tuple[str, ...] = ()
    plugins: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectIR:
    source_format: str            # human DAW name of the source (e.g. "Ableton Live")
    project_path: str             # the file/bundle the IR was read from
    version: str = ""
    bpm: float | None = None
    length: str = ""
    key: str = ""
    tracks: tuple[TrackIR, ...] = ()
    samples_found: tuple[str, ...] = ()    # basenames present next to the project
    samples_missing: tuple[str, ...] = ()  # referenced basenames not found on disk
    extra: dict = field(default_factory=dict)


def _coerce_track(t: dict) -> TrackIR:
    return TrackIR(
        name=str(t.get("name", "") or ""),
        kind=str(t.get("type", "") or ""),
        instruments=tuple(str(i) for i in (t.get("instruments") or [])),
        plugins=tuple(str(p) for p in (t.get("plugins") or [])),
    )


def ir_from_checker_data(
    data: dict, project_path: str | Path, source_format: str
) -> ProjectIR:
    """Build a :class:`ProjectIR` from the rich checker schema.

    ``data`` is what ``als.parser.parse_als`` returns directly, or what
    ``projects_fmt.common.to_checker_data`` produces for the binary formats:
    ``{version, bpm, length, key, tracks:[{name,type,instruments,plugins}],
    samples:{found,missing}}``.
    """
    raw_tracks = data.get("tracks") or []
    tracks = tuple(_coerce_track(t) for t in raw_tracks if isinstance(t, dict))
    samples = data.get("samples") or {}
    bpm = data.get("bpm")
    return ProjectIR(
        source_format=source_format,
        project_path=str(project_path),
        version=str(data.get("version", "") or ""),
        bpm=float(bpm) if isinstance(bpm, (int, float)) else None,
        length=str(data.get("length", "") or ""),
        key=str(data.get("key", "") or ""),
        tracks=tracks,
        samples_found=tuple(str(s) for s in samples.get("found", [])),
        samples_missing=tuple(str(s) for s in samples.get("missing", [])),
    )

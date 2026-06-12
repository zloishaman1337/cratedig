"""Write a :class:`ProjectIR` to an AAF interchange file (via pyaaf2).

AAF is importable by Cubase, Pro Tools, Logic, Reaper and Premiere, so it is the
realistic path to reach DAWs we cannot author natively. This emits a structural
CompositionMob: one named timeline slot per source track, with tempo, sample-file
names and plugin/effect names recorded as user comments. Audio essence is not
embedded — the importing DAW relinks media from the copied ``media/`` folder.

``aaf2`` is an optional dependency (``cratedig[convert]``); :func:`write` raises a
clear error when it is absent so the UI can surface "install the convert extra".
"""

from __future__ import annotations

from pathlib import Path

from ..ir import ProjectIR
from ..options import ConvertOptions

_EDIT_RATE = 25  # frames/sec timeline edit rate (arbitrary; AAF requires one)


def available() -> bool:
    try:
        import aaf2  # noqa: F401
    except ImportError:
        return False
    return True


def write(ir: ProjectIR, out_path: str | Path, options: ConvertOptions, media: dict) -> None:
    try:
        import aaf2
    except ImportError as exc:  # pragma: no cover - exercised via available() guard
        raise RuntimeError(
            "AAF export needs pyaaf2 — install it with: pip install \"cratedig[convert]\""
        ) from exc

    comments = _comments(ir, media, options)

    with aaf2.open(str(out_path), "w") as f:
        comp = f.create.CompositionMob(_safe_name(Path(ir.project_path).stem) or "cratedig")
        comp.usage = "Usage_TopLevel"
        f.content.mobs.append(comp)

        if options.tracks and ir.tracks:
            for track in ir.tracks:
                slot = comp.create_timeline_slot(edit_rate=_EDIT_RATE)
                slot.name = _safe_name(_track_label(track, options))
                slot.segment = f.create.Sequence(media_kind="Sound")
        else:
            slot = comp.create_timeline_slot(edit_rate=_EDIT_RATE)
            slot.name = "cratedig"
            slot.segment = f.create.Sequence(media_kind="Sound")

        # Record metadata that AAF can't structurally carry as searchable comments.
        for key, value in comments.items():
            comp.comments[key] = value


def _track_label(track, options: ConvertOptions) -> str:
    name = track.name or "Track"
    extras: list[str] = []
    if options.plugin_names:
        extras += list(track.instruments)
    if options.effect_names:
        extras += list(track.plugins)
    return f"{name} — FX: {', '.join(extras)}" if extras else name


def _comments(ir: ProjectIR, media: dict, options: ConvertOptions) -> dict:
    out: dict[str, str] = {"cratedig_source": ir.source_format}
    if options.tempo and ir.bpm:
        out["cratedig_bpm"] = f"{ir.bpm:g}"
    if ir.key:
        out["cratedig_key"] = ir.key
    refs = list(ir.samples_found)
    if refs:
        out["cratedig_samples"] = ", ".join(refs[:64])
    return out


def _safe_name(s: str) -> str:
    return "".join(c for c in s if c.isprintable()).strip()

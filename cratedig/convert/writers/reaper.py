"""Write a :class:`ProjectIR` to a Reaper ``.RPP`` project (plain-text S-expr).

Highest-fidelity target: tempo, one named track per source track, and one media
item per referenced sample on a dedicated "Imported Samples" track. Plugin/effect
names — which the source only exposes as labels, not instantiable state — are
appended to each track's name so they survive visibly.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..ir import ProjectIR
from ..options import ConvertOptions


def _esc(s: str) -> str:
    """Reaper quotes are plain double quotes; drop any embedded quote to stay valid."""
    return s.replace('"', "'")


def _track_label(track, options: ConvertOptions) -> str:
    name = track.name or "Track"
    extras: list[str] = []
    if options.plugin_names:
        extras += list(track.instruments)
    if options.effect_names:
        extras += list(track.plugins)
    if extras:
        name = f"{name} — FX: {', '.join(extras)}"
    return _esc(name)


def write(ir: ProjectIR, out_path: str | Path, options: ConvertOptions, media: dict) -> None:
    lines: list[str] = []
    a = lines.append
    a(f'<REAPER_PROJECT 0.1 "7.0/cratedig" {int(time.time())}')
    if options.tempo and ir.bpm:
        a(f"  TEMPO {ir.bpm:g} 4 4")

    if options.tracks:
        for track in ir.tracks:
            a("  <TRACK")
            a(f'    NAME "{_track_label(track, options)}"')
            a("  >")

    # Referenced samples become media items on a dedicated track so both the track
    # names above and the file references survive a round-trip.
    refs = _sample_refs(ir, media, options)
    if refs:
        a("  <TRACK")
        a('    NAME "Imported Samples"')
        pos = 0.0
        for ref in refs:
            a("    <ITEM")
            a(f"      POSITION {pos:g}")
            a("      LENGTH 4")
            a("      <SOURCE WAVE")
            a(f'        FILE "{_esc(ref)}"')
            a("      >")
            a("    >")
            pos += 4.0
        a("  >")

    a(">")
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sample_refs(ir: ProjectIR, media: dict, options: ConvertOptions) -> list[str]:
    """Resolve each found sample to a copied media path or its bare basename."""
    refs: list[str] = []
    for basename in ir.samples_found:
        if options.copy_samples and basename in media:
            refs.append(media[basename])
        else:
            refs.append(basename)
    return refs

"""Write a :class:`ProjectIR` to an Ableton Live ``.als`` (gzipped XML).

Best-effort: emits a structurally valid LiveSet with the tempo, one named track per
source track, and the referenced samples as audio clips. The schema mirrors exactly
what ``cratedig.als.parser`` reads, so a converted project round-trips through it;
it is intended to open in Live 11+. Plugin/effect names are appended to the track
name (the source exposes names only, not instantiable device state).
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

from ..ir import ProjectIR
from ..options import ConvertOptions

# A real Live 11 header. MajorVersion 5 + this MinorVersion is what Live 11 writes.
_CREATOR = "Ableton Live 11.3.21"
_MAJOR = "5"
_MINOR = "11.0_11300"
_SCHEMA = "3"


def _val(parent: ET.Element, tag: str, value) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.set("Value", str(value))
    return el


def _track_name(track, options: ConvertOptions) -> str:
    name = track.name or "Track"
    extras: list[str] = []
    if options.plugin_names:
        extras += list(track.instruments)
    if options.effect_names:
        extras += list(track.plugins)
    return f"{name} — FX: {', '.join(extras)}" if extras else name


def _named_track(parent: ET.Element, tag: str, name: str) -> ET.Element:
    track = ET.SubElement(parent, tag)
    name_el = ET.SubElement(track, "Name")
    _val(name_el, "EffectiveName", name)
    _val(name_el, "UserName", name)
    return track


def write(ir: ProjectIR, out_path: str | Path, options: ConvertOptions, media: dict) -> None:
    root = ET.Element("Ableton")
    root.set("Creator", f"cratedig (from {ir.source_format})")
    root.set("MajorVersion", _MAJOR)
    root.set("MinorVersion", _MINOR)
    root.set("SchemaChangeCount", _SCHEMA)
    root.set("Revision", "0")

    live_set = ET.SubElement(root, "LiveSet")

    # Tempo at the path _get_tempo reads first.
    bpm = ir.bpm if (options.tempo and ir.bpm) else 120.0
    master = ET.SubElement(live_set, "MasterTrack")
    mixer = ET.SubElement(ET.SubElement(master, "MasterChain"), "Mixer")
    tempo = ET.SubElement(mixer, "Tempo")
    _val(tempo, "Manual", f"{bpm:g}")

    tracks_el = ET.SubElement(live_set, "Tracks")
    if options.tracks:
        for track in ir.tracks:
            tag = "MidiTrack" if track.kind in ("midi", "instrument") else "AudioTrack"
            _named_track(tracks_el, tag, _track_name(track, options))

    refs = _sample_refs(ir, media, options)
    if refs:
        holder = _named_track(tracks_el, "AudioTrack", "Imported Samples")
        events = _arranger_events(holder)
        for i, (basename, rel) in enumerate(refs):
            clip = ET.SubElement(events, "AudioClip")
            clip.set("Time", str(i * 4))
            _val(clip, "CurrentStart", i * 4)
            _val(clip, "CurrentEnd", i * 4 + 4)
            file_ref = ET.SubElement(ET.SubElement(clip, "SampleRef"), "FileRef")
            _val(file_ref, "Name", basename)
            _val(file_ref, "RelativePath", rel)

    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with gzip.open(out_path, "wb") as fh:
        fh.write(data)


def _arranger_events(track: ET.Element) -> ET.Element:
    chain = ET.SubElement(track, "DeviceChain")
    seq = ET.SubElement(chain, "MainSequencer")
    timeable = ET.SubElement(seq, "ClipTimeable")
    arranger = ET.SubElement(timeable, "ArrangerAutomation")
    return ET.SubElement(arranger, "Events")


def _sample_refs(ir: ProjectIR, media: dict, options: ConvertOptions) -> list[tuple[str, str]]:
    """(basename, relative_path) for each found sample; bare basename if not copied."""
    refs: list[tuple[str, str]] = []
    for basename in ir.samples_found:
        rel = media[basename] if (options.copy_samples and basename in media) else basename
        refs.append((basename, rel))
    return refs

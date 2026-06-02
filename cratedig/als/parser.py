import gzip
import math
import os
import struct
import sys
import xml.etree.ElementTree as ET

# ── Live built-in device tag → display name ──────────────────────────────────

LIVE_INSTRUMENTS = {
    "Operator": "Operator",
    "Analog": "Analog",
    "UltraAnalog": "Analog",              # Live 12+
    "Collision": "Collision",
    "Electric": "Electric",
    "LoungeLizard": "Electric",           # Live 12+
    "Tension": "Tension",
    "StringStudio": "Tension",            # Live 12+
    "Wavetable": "Wavetable",
    "InstrumentVector": "Wavetable",      # Live 12+
    "Drift": "Drift",
    "Meld": "Meld",
    "InstrumentMeld": "Meld",             # Live 12+
    "Impulse": "Impulse",
    "InstrumentImpulse": "Impulse",       # Live 12+
    "Sampler": "Sampler",
    "MultiSampler": "Sampler",
    "SimplerInstrument": "Simpler",
    "Simpler": "Simpler",
    "OriginalSimpler": "Simpler",
    "DrumSampler": "Drum Sampler",
    "DrumCell": "Drum Sampler",           # Live 12+
    "Granulator3": "Granulator III",
    "ExternalInstrument": "External Instrument",
    "ProxyInstrumentDevice": "External Instrument",  # Live 12+
    "MidiArpeggiator": "Arpeggiator",
    "MidiChord": "Chord",
    "MidiNoteLength": "Note Length",
    "MidiPitcher": "Pitch",
    "MidiRandom": "Random",
    "MidiScale": "Scale",
    "MidiVelocity": "Velocity",
    "MidiMonitor": "MIDI Monitor",
    "MidiCcControl": "CC Control",
}

LIVE_EFFECTS = {
    "Eq8": "EQ Eight",
    "Eq3": "EQ Three",
    "FilterEQ3": "EQ Three",
    "ChannelEq": "Channel EQ",
    "AutoFilter": "Auto Filter",
    "AutoFilter2": "Auto Filter",         # Live 12+
    "Compressor2": "Compressor",
    "MultibandDynamics": "Multiband Dynamics",
    "Limiter": "Limiter",
    "GlueCompressor": "Glue Compressor",
    "Gate": "Gate",
    "DrumBuss": "Drum Buss",
    "Saturator": "Saturator",
    "Tube": "Tube",
    "Overdrive": "Overdrive",
    "Pedal": "Pedal",
    "Redux": "Redux",
    "Redux2": "Redux",
    "Erosion": "Erosion",
    "Erosion2": "Erosion",                # Live 12+
    "Amp": "Amp",
    "Cabinet": "Cabinet",
    "Roar": "Roar",
    "AutoPan": "Auto Pan",
    "AutoPan2": "Auto Pan",               # Live 12+
    "Chorus": "Chorus-Ensemble",
    "Chorus2": "Chorus-Ensemble",
    "Flanger": "Flanger",
    "Phaser": "Phaser-Flanger",
    "Phaser2": "Phaser-Flanger",
    "PhaserNew": "Phaser-Flanger",        # Live 12+
    "FrequencyShifter": "Frequency Shifter",
    "Shifter": "Frequency Shifter",
    "AutoShift": "Auto Shift",
    "PitchHack": "Pitch Hack",
    "Delay": "Delay",
    "PingPongDelay": "Ping Pong Delay",
    "FilterDelay": "Filter Delay",
    "GrainDelay": "Grain Delay",
    "Echo": "Echo",
    "Align": "Align Delay",
    "BeatRepeat": "Beat Repeat",
    "Reverb": "Reverb",
    "HybridReverb": "Hybrid Reverb",
    "Hybrid": "Hybrid Reverb",
    "ConvolutionReverb": "Convolution Reverb",
    "Convolution": "Convolution Reverb",
    "SpectralResonator": "Spectral Resonator",
    "SpectralTime": "Spectral Time",
    "SpectralBlur": "Spectral Blur",
    "Spectral": "Spectral",               # Live 12+ unified tag
    "Resonators": "Resonators",
    "Resonator": "Resonators",            # Live 12+
    "Corpus": "Corpus",
    "Vocoder": "Vocoder",
    "StereoGain": "Utility",
    "Utility": "Utility",
    "Spectrum": "Spectrum",
    "SpectrumAnalyzer": "Spectrum",       # Live 12+
    "Tuner": "Tuner",
    "LooperDevice": "Looper",
    "Looper": "Looper",                   # Live 12+
    "Vinyl": "Vinyl Distortion",
    "ProxyAudioEffectDevice": "External Audio Effect",  # Live 12+
    "Mangle": "Mangle",
    "Transmute": "Transmute",
}

# Rack tags — require recursion into inner chains
RACK_TAGS = {
    "InstrumentGroupDevice":  ("live_instruments", "Instrument Rack"),
    "InstrumentChain":        ("live_instruments", "Instrument Rack"),
    "AudioEffectGroupDevice": ("live_effects",     "Audio Effect Rack"),
    "DrumGroupDevice":        ("live_instruments", "Drum Rack"),
    "MidiEffectGroupDevice":  ("live_effects",     "MIDI Effect Rack"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _linear_to_db(value: float) -> float:
    if value <= 0:
        return -math.inf
    return round(20.0 * math.log10(value), 1)


def _get_fader_db(track_el: ET.Element) -> float | None:
    for path in ("./DeviceChain/Mixer/Volume", "./MasterChain/Mixer/Volume"):
        vol = track_el.find(path)
        if vol is not None:
            manual = vol.find("Manual")
            if manual is not None:
                try:
                    return _linear_to_db(float(manual.get("Value", 1.0)))
                except (TypeError, ValueError):
                    pass
    return None


def _get_track_name(track_el: ET.Element) -> str:
    for path in ("./Name/EffectiveName", "./Name/UserName"):
        el = track_el.find(path)
        if el is not None and el.get("Value"):
            return el.get("Value")
    return "Unnamed"


def _has_midi_content(track_el: ET.Element) -> bool:
    for clip in track_el.iter("MidiClip"):
        for _ in clip.iter("MidiNoteEvent"):
            return True
    return False


def _has_audio_content(track_el: ET.Element) -> bool:
    for clip in track_el.iter("AudioClip"):
        for ref in clip.iter("SampleRef"):
            for attr_path in (".//RelativePath", ".//Path", ".//Name"):
                el = ref.find(attr_path)
                if el is not None and el.get("Value"):
                    return True
    return False


def _get_m4l_name(device_el: ET.Element) -> str:
    # UserName — user-renamed in Ableton
    user_name = device_el.find("UserName")
    if user_name is not None:
        name = user_name.get("Value", "").strip()
        if name:
            return name

    # Live <12: LastPresetRef/FileRef/Name
    name_el = device_el.find(".//LastPresetRef//Name")
    if name_el is not None:
        name = name_el.get("Value", "").strip().removesuffix(".amxd")
        if name:
            return name

    # Live 12+: name lives in SourceContext or PatchSlot paths
    for path in (
        ".//SourceContext//OriginalFileRef//RelativePath",
        ".//SourceContext//OriginalFileRef//Path",
        ".//PatchSlot//FileRef/RelativePath",
        ".//PatchSlot//FileRef/Path",
    ):
        el = device_el.find(path)
        if el is not None:
            val = el.get("Value", "").strip()
            if val:
                basename = val.replace("\\", "/").rsplit("/", 1)[-1]
                name = basename.removesuffix(".amxd")
                if name:
                    return name

    return "Unknown M4L"


# ── Rack chain iterator ───────────────────────────────────────────────────────

def _get_chain_name(branch_el: ET.Element) -> str:
    """Read chain name handling both flat <Name Value="..."/> and nested formats."""
    name_el = branch_el.find("Name")
    if name_el is None:
        return ""
    # Flat attribute (older Live versions)
    name = name_el.get("Value", "").strip()
    if name:
        return name
    # Nested elements (Live 11+): <EffectiveName> or <UserName>
    for sub in ("EffectiveName", "UserName"):
        sub_el = name_el.find(sub)
        if sub_el is not None:
            name = sub_el.get("Value", "").strip()
            if name:
                return name
    return ""


def _find_devices_in_branch(branch_el: ET.Element):
    """Return the <Devices> element inside a rack branch, trying multiple paths."""
    return (branch_el.find("./DeviceChain/Devices")
            or branch_el.find(".//Devices"))


def _get_rack_chain_devices(rack_el: ET.Element) -> list[dict]:
    """
    Return list of {chain_name, devices_el} for each chain inside a rack.
    Works for Instrument, Audio Effect, MIDI Effect, and Drum racks.
    """
    result = []

    # Standard racks: Live 12 uses <Branches>, older versions use <Chains>
    for container_tag in ("Branches", "Chains"):
        container = rack_el.find(container_tag)
        if container is not None:
            for branch in container:
                devices_el = _find_devices_in_branch(branch)
                if devices_el is not None:
                    result.append({
                        "chain_name": _get_chain_name(branch),
                        "devices_el": devices_el,
                    })
            break  # use whichever container was found first

    # Drum Rack: <DrumBranches> → <DrumBranch> → <DeviceChain><Devices>
    drum_branches = rack_el.find("DrumBranches")
    if drum_branches is not None:
        for branch in drum_branches:
            devices_el = _find_devices_in_branch(branch)
            if devices_el is None:
                continue
            chain_name = _get_chain_name(branch)
            if not chain_name:
                note_el = branch.find(".//ReceivingNote") or branch.find(".//NoteRangeMin")
                if note_el is not None:
                    chain_name = f"Pad {note_el.get('Value', '?')}"
            result.append({"chain_name": chain_name, "devices_el": devices_el})

    return result


# ── Device collector ──────────────────────────────────────────────────────────

def _au_is_instrument(component_type_val: str, num_inputs_val: str) -> bool:
    """Classify AU device: True if instrument (aumu), False if effect."""
    try:
        fourcc = struct.pack(">I", int(component_type_val)).decode("ascii", "replace")
        return fourcc == "aumu"
    except (ValueError, TypeError, struct.error):
        pass
    # Fallback: 0 audio inputs → instrument
    try:
        return int(num_inputs_val) == 0
    except (ValueError, TypeError):
        return False


def _vst3_is_instrument(device_type_val: str, num_inputs_val: str) -> bool:
    """Classify VST3 device: DeviceType 1 = instrument, 2 = effect."""
    try:
        return int(device_type_val) == 1
    except (ValueError, TypeError):
        pass
    try:
        return int(num_inputs_val) == 0
    except (ValueError, TypeError):
        return False


def _vst2_is_instrument(num_inputs_val: str | None) -> bool:
    """Classify VST2 device via NumAudioInputs fallback; default → effect."""
    if num_inputs_val is None:
        return False
    try:
        return int(num_inputs_val) == 0
    except (ValueError, TypeError):
        return False


def _empty_devs() -> dict:
    return {
        "live_instruments": [],
        "live_effects": [],
        "vst2": [],
        "vst3": [],
        "au_instruments": [],
        "au_effects": [],
        "vst2_instruments": [],
        "vst2_effects": [],
        "vst3_instruments": [],
        "vst3_effects": [],
        "m4l_instruments": [],
        "m4l_effects": [],
        "m4l_midi": [],
        "rack_details": [],   # list of rack dicts for expandable GUI
    }


def _collect_devices(devices_el: ET.Element, depth: int = 0) -> dict:
    """
    Collect all devices from a single <Devices> XML element.
    Recurses into racks (up to depth 2) and stores rack hierarchy in rack_details.
    """
    result = _empty_devs()
    seen: dict[str, set] = {}   # key → set of names already added

    def _add(key: str, name: str):
        if key not in seen:
            seen[key] = set()
        if name not in seen[key]:
            seen[key].add(name)
            result[key].append(name)

    for child in devices_el:
        tag = child.tag

        # ── AU ───────────────────────────────────────────────────────────────
        if tag == "AuPluginDevice":
            au_info = child.find(".//AuPluginInfo")
            if au_info is not None:
                name_el = au_info.find("Name")
                name = (name_el.get("Value", "") if name_el is not None else "") or "Unknown AU"
                ct_el = au_info.find("ComponentType")
                ni_el = au_info.find("NumAudioInputs")
                ct_val = ct_el.get("Value", "") if ct_el is not None else ""
                ni_val = ni_el.get("Value", "") if ni_el is not None else ""
                if _au_is_instrument(ct_val, ni_val):
                    _add("au_instruments", name)
                else:
                    _add("au_effects", name)
            else:
                _add("au_effects", "Unknown AU")
            continue

        # ── VST ──────────────────────────────────────────────────────────────
        if tag == "PluginDevice":
            vst_info = child.find(".//VstPluginInfo")
            if vst_info is not None:
                plug = vst_info.find("PlugName")
                name = (plug.get("Value", "") if plug is not None else "") or "Unknown VST2"
                _add("vst2", name)
                ni_el = vst_info.find("NumAudioInputs")
                ni_val = ni_el.get("Value", None) if ni_el is not None else None
                if _vst2_is_instrument(ni_val):
                    _add("vst2_instruments", name)
                else:
                    _add("vst2_effects", name)
                continue
            vst3_info = child.find(".//Vst3PluginInfo")
            if vst3_info is not None:
                name_el = vst3_info.find("Name")
                name = (name_el.get("Value", "") if name_el is not None else "") or "Unknown VST3"
                _add("vst3", name)
                dt_el = vst3_info.find("DeviceType")
                ni_el = vst3_info.find("NumAudioInputs")
                dt_val = dt_el.get("Value", "") if dt_el is not None else ""
                ni_val = ni_el.get("Value", "") if ni_el is not None else ""
                if _vst3_is_instrument(dt_val, ni_val):
                    _add("vst3_instruments", name)
                else:
                    _add("vst3_effects", name)
                continue

        # ── Max for Live ─────────────────────────────────────────────────────
        if tag == "MxDeviceInstrument":
            _add("m4l_instruments", _get_m4l_name(child))
            continue
        if tag == "MxDeviceAudioEffect":
            _add("m4l_effects", _get_m4l_name(child))
            continue
        if tag in ("MxDeviceMidi", "MxDeviceMidiEffect"):
            _add("m4l_midi", _get_m4l_name(child))
            continue

        # ── Racks (recurse) ───────────────────────────────────────────────────
        if tag in RACK_TAGS and depth < 2:
            target_list, rack_display = RACK_TAGS[tag]
            inner_chains_raw = _get_rack_chain_devices(child)
            chain_details = []
            inner_names: list[str] = []

            for c in inner_chains_raw:
                inner = _collect_devices(c["devices_el"], depth + 1)
                chain_details.append({
                    "chain_name": c["chain_name"],
                    **{k: inner[k] for k in inner if k != "rack_details"},
                    "rack_details": inner["rack_details"],
                })
                # Collect flat names for bracket summary
                for n in inner["live_instruments"] + inner["live_effects"]:
                    inner_names.append(n)
                for n in inner["vst2"]:
                    inner_names.append(f"VST2:{n}")
                for n in inner["vst3"]:
                    inner_names.append(f"VST3:{n}")
                for n in inner["au_instruments"] + inner["au_effects"]:
                    inner_names.append(f"{n} [AU]")
                for n in inner["m4l_instruments"] + inner["m4l_effects"]:
                    inner_names.append(f"{n} [M4L]")

            # Compact display: "Instrument Rack [Operator, EQ Eight]"
            if inner_names:
                preview = inner_names[:4]
                suffix = "…" if len(inner_names) > 4 else ""
                display = f"{rack_display} [{', '.join(preview)}{suffix}]"
            else:
                display = rack_display

            _add(target_list, display)
            result["rack_details"].append({
                "rack_type": rack_display,
                "rack_tag": tag,
                "chains": chain_details,
            })
            continue

        # ── Native Live instruments ───────────────────────────────────────────
        if tag in LIVE_INSTRUMENTS:
            _add("live_instruments", LIVE_INSTRUMENTS[tag])
            continue

        # ── Native Live effects ───────────────────────────────────────────────
        if tag in LIVE_EFFECTS:
            _add("live_effects", LIVE_EFFECTS[tag])
            continue

    return result


def _merge_devs(base: dict, addition: dict) -> None:
    """Merge addition into base in-place, deduplicating string lists."""
    for key in ("live_instruments", "live_effects", "vst2", "vst3",
                "au_instruments", "au_effects",
                "vst2_instruments", "vst2_effects", "vst3_instruments", "vst3_effects",
                "m4l_instruments", "m4l_effects", "m4l_midi"):
        existing = set(base[key])
        for item in addition.get(key, []):
            if item not in existing:
                base[key].append(item)
                existing.add(item)
    base["rack_details"].extend(addition.get("rack_details", []))


# ── Track chain iterator ──────────────────────────────────────────────────────

def _iter_track_chains(track_el: ET.Element):
    """
    Yield every top-level <Devices> element found inside a track's device chains.
    Covers both the standard nested path and shallower layouts used by some track types.
    """
    for outer_tag in ("DeviceChain", "MasterChain"):
        outer = track_el.find(outer_tag)
        if outer is None:
            continue
        # Shallow: DeviceChain/Devices
        direct = outer.find("Devices")
        if direct is not None:
            yield direct
        # Deep: DeviceChain/DeviceChain/Devices (covers most MIDI + Audio tracks)
        for inner in outer.findall("DeviceChain"):
            devices = inner.find("Devices")
            if devices is not None:
                yield devices


def _collect_all_track_devices(track_el: ET.Element) -> dict:
    """Collect and merge devices from ALL chains of a track."""
    merged = _empty_devs()
    for devices_el in _iter_track_chains(track_el):
        _merge_devs(merged, _collect_devices(devices_el))
    return merged


# ── Aggregated instruments / plugins lists ────────────────────────────────────

_MIDI_FX_NAMES = {
    "Arpeggiator", "Chord", "Note Length", "Pitch",
    "Random", "Scale", "Velocity", "MIDI Monitor", "CC Control",
}

# Rack tags whose compact-display string goes into instruments vs plugins
_RACK_INSTRUMENT_TAGS = {"InstrumentGroupDevice", "InstrumentChain", "DrumGroupDevice"}
_RACK_PLUGIN_TAGS     = {"AudioEffectGroupDevice", "MidiEffectGroupDevice"}


def _build_aggregated(devs: dict) -> tuple[list[str], list[str]]:
    """
    Build (instruments, plugins) display-name lists from a collected devs dict.
    Dedupes within each list preserving first-seen order.
    """
    instruments: list[str] = []
    plugins: list[str] = []
    seen_i: set[str] = set()
    seen_p: set[str] = set()

    def _add_i(name: str) -> None:
        if name not in seen_i:
            seen_i.add(name)
            instruments.append(name)

    def _add_p(name: str) -> None:
        if name not in seen_p:
            seen_p.add(name)
            plugins.append(name)

    # Native Live instruments (split MIDI FX out to plugins)
    for n in devs.get("live_instruments", []):
        if n in _MIDI_FX_NAMES:
            _add_p(n)
        else:
            _add_i(n)

    # Native Live effects → plugins
    for n in devs.get("live_effects", []):
        _add_p(n)

    # VST2
    for n in devs.get("vst2_instruments", []):
        _add_i(f"{n} [VST2]")
    for n in devs.get("vst2_effects", []):
        _add_p(f"{n} [VST2]")

    # VST3
    for n in devs.get("vst3_instruments", []):
        _add_i(f"{n} [VST3]")
    for n in devs.get("vst3_effects", []):
        _add_p(f"{n} [VST3]")

    # AU
    for n in devs.get("au_instruments", []):
        _add_i(f"{n} [AU]")
    for n in devs.get("au_effects", []):
        _add_p(f"{n} [AU]")

    # M4L
    for n in devs.get("m4l_instruments", []):
        _add_i(f"{n} [M4L]")
    for n in devs.get("m4l_effects", []):
        _add_p(f"{n} [M4L]")
    for n in devs.get("m4l_midi", []):
        _add_p(f"{n} [M4L]")

    # Racks: instrument/drum racks → instruments; audio-effect/midi-effect racks → plugins
    for rack in devs.get("rack_details", []):
        rack_tag = rack.get("rack_tag", "")
        rack_type = rack.get("rack_type", "")
        # Build compact display string for the rack
        chains = rack.get("chains", [])
        inner_names: list[str] = []
        for c in chains:
            for n in c.get("live_instruments", []):
                inner_names.append(n)
            for n in c.get("live_effects", []):
                inner_names.append(n)
            for n in c.get("vst2", []):
                inner_names.append(f"VST2:{n}")
            for n in c.get("vst3", []):
                inner_names.append(f"VST3:{n}")
            for n in c.get("au_instruments", []) + c.get("au_effects", []):
                inner_names.append(f"{n} [AU]")
            for n in c.get("m4l_instruments", []) + c.get("m4l_effects", []):
                inner_names.append(f"{n} [M4L]")
        if inner_names:
            preview = inner_names[:4]
            suffix = "…" if len(inner_names) > 4 else ""
            display = f"{rack_type} [{', '.join(preview)}{suffix}]"
        else:
            display = rack_type

        if rack_tag in _RACK_INSTRUMENT_TAGS:
            _add_i(display)
        else:
            _add_p(display)

    return instruments, plugins


# ── Arrangement length & tempo ────────────────────────────────────────────────

def _get_tempo(live_set: ET.Element) -> float:
    """Read BPM from master track mixer tempo; default 120."""
    for path in (
        "./MasterTrack/MasterChain/Mixer/Tempo/Manual",
        "./MasterTrack/DeviceChain/Mixer/Tempo/Manual",
        "./MainTrack/DeviceChain/Mixer/Tempo/Manual",   # Live 12+
        "./Tempo/Manual",
    ):
        el = live_set.find(path)
        if el is not None:
            try:
                return float(el.get("Value", 120))
            except (ValueError, TypeError):
                pass
    return 120.0


def _clip_end_beats(clip_el: ET.Element) -> float:
    """Return end position of a clip in beats (Time_attr + visible_length)."""
    try:
        start = float(clip_el.get("Time", 0))
    except (ValueError, TypeError):
        return 0.0

    length = 0.0
    # Primary: CurrentEnd - CurrentStart (visible region in arrangement)
    ce = clip_el.find("CurrentEnd")
    cs = clip_el.find("CurrentStart")
    if ce is not None and cs is not None:
        try:
            length = float(ce.get("Value", 0)) - float(cs.get("Value", 0))
        except (ValueError, TypeError):
            pass
    # Fallback: Loop outer bounds
    if length <= 0:
        oe = clip_el.find("./Loop/OuterLoopEnd")
        os_ = clip_el.find("./Loop/OuterLoopStart")
        if oe is not None:
            try:
                length = float(oe.get("Value", 0)) - (
                    float(os_.get("Value", 0)) if os_ is not None else 0.0
                )
            except (ValueError, TypeError):
                pass

    return start + max(length, 0.0)


def _get_arrangement_length(live_set: ET.Element, bpm: float) -> dict | None:
    """
    Find the furthest clip end position across all tracks.
    Returns {beats, bars, time_str, bpm} or None if no clips found.
    Assumes 4/4 time for bar calculation.
    """
    max_beats = 0.0
    found = False

    for clip in live_set.iter():
        if clip.tag not in ("MidiClip", "AudioClip"):
            continue
        end = _clip_end_beats(clip)
        if end > max_beats:
            max_beats = end
            found = True

    if not found or max_beats <= 0:
        return None

    bars = max_beats / 4.0
    total_sec = max_beats / bpm * 60.0
    mins = int(total_sec // 60)
    secs = total_sec % 60
    return {
        "beats": round(max_beats, 2),
        "bars": round(bars, 2),
        "time_str": f"{mins}:{secs:05.2f}",
        "bpm": round(bpm, 2),
    }


# ── Sample file check ─────────────────────────────────────────────────────────

def _check_samples(live_set: ET.Element, als_path: str) -> dict:
    """
    Check whether audio sample files referenced in the project exist on disk.
    Looks for SampleRef > FileRef elements (audio clips + instrument samplers).
    Returns {found: [names], missing: [names]}.
    """
    project_dir = os.path.dirname(os.path.abspath(als_path))
    found: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    for sample_ref in live_set.iter("SampleRef"):
        file_ref = sample_ref.find("FileRef")
        if file_ref is None:
            continue

        # Try <Name> first; fall back to basename of <Path> or <RelativePath>
        name_el = file_ref.find("Name")
        sample_name = (name_el.get("Value", "") if name_el is not None else "").strip()
        if not sample_name:
            for tag in ("Path", "RelativePath"):
                el = file_ref.find(tag)
                if el is not None:
                    val = el.get("Value", "").strip()
                    if val:
                        sample_name = os.path.basename(val.replace("\\", "/"))
                        break
        if not sample_name or sample_name in seen:
            continue
        seen.add(sample_name)

        # Only check within the project folder (relative path).
        # Absolute path is intentionally ignored — the goal is to verify
        # that "Collect All and Save" was run before submitting.
        file_found = False
        rel_el = file_ref.find("RelativePath")
        if rel_el is not None and rel_el.get("Value"):
            rel = rel_el.get("Value").replace("/", os.sep).replace("\\", os.sep)
            if os.path.isfile(os.path.normpath(os.path.join(project_dir, rel))):
                file_found = True

        (found if file_found else missing).append(sample_name)

    return {"found": found, "missing": missing}


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_als(path: str) -> dict:
    try:
        with gzip.open(path, "rb") as f:
            tree = ET.parse(f)
    except Exception as e:
        raise ValueError(f"Не удалось открыть файл: {e}") from e

    root = tree.getroot()
    version = root.get("Creator", "") or f"Ableton Live {root.get('MajorVersion', '?')}"

    live_set = root.find("LiveSet")
    if live_set is None:
        raise ValueError("Не найден раздел LiveSet в файле.")

    # ── Tempo & arrangement length ────────────────────────────────────────────
    bpm = _get_tempo(live_set)
    arrangement = _get_arrangement_length(live_set, bpm)

    # ── Sample check ──────────────────────────────────────────────────────────
    samples = _check_samples(live_set, path)

    tracks_el = live_set.find("Tracks")
    tracks = []

    if tracks_el is not None:
        for track_el in tracks_el:
            tag = track_el.tag
            if tag not in ("MidiTrack", "AudioTrack", "GroupTrack"):
                continue

            track_type = {"MidiTrack": "midi", "AudioTrack": "audio", "GroupTrack": "group"}[tag]
            name = _get_track_name(track_el)

            if track_type == "midi":
                has_content = _has_midi_content(track_el)
            elif track_type == "audio":
                has_content = _has_audio_content(track_el)
            else:
                has_content = True

            devs = _collect_all_track_devices(track_el) if has_content else _empty_devs()
            agg_instruments, agg_plugins = _build_aggregated(devs)

            tracks.append({
                "name": name,
                "type": track_type,
                "has_content": has_content,
                "live_instruments": devs["live_instruments"],
                "live_effects": devs["live_effects"],
                "vst2_plugins": devs["vst2"],
                "vst3_plugins": devs["vst3"],
                "m4l_instruments": devs["m4l_instruments"],
                "m4l_effects": devs["m4l_effects"],
                "m4l_midi": devs["m4l_midi"],
                "rack_details": devs["rack_details"],
                "instruments": agg_instruments,
                "plugins": agg_plugins,
            })

    # ── Main channel ──────────────────────────────────────────────────────────
    master_el = live_set.find("MasterTrack") or live_set.find("MainTrack")
    main_info: dict = {
        "fader_db": None,
        "fader_above_0db": False,
        "live_effects": [],
        "vst2_plugins": [],
        "vst3_plugins": [],
        "m4l_effects": [],
        "rack_details": [],
        "instruments": [],
        "plugins": [],
    }

    if master_el is not None:
        fader_db = _get_fader_db(master_el)
        main_info["fader_db"] = fader_db
        main_info["fader_above_0db"] = fader_db is not None and fader_db > 0.0
        devs = _collect_all_track_devices(master_el)
        main_info["live_effects"] = devs["live_effects"]
        main_info["vst2_plugins"] = devs["vst2"]
        main_info["vst3_plugins"] = devs["vst3"]
        main_info["m4l_effects"] = devs["m4l_effects"]
        main_info["rack_details"] = devs["rack_details"]
        agg_instruments, agg_plugins = _build_aggregated(devs)
        main_info["instruments"] = agg_instruments
        main_info["plugins"] = agg_plugins

    return {
        "ableton_version": version,
        "tracks": tracks,
        "main": main_info,
        "arrangement": arrangement,   # {beats, bars, time_str, bpm} or None
        "samples": samples,           # {found: [...], missing: [...]}
    }


# ── VST scanner ───────────────────────────────────────────────────────────────

def _vst_dirs() -> dict:
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return {
            "vst2": [
                "/Library/Audio/Plug-Ins/VST",
                os.path.join(home, "Library/Audio/Plug-Ins/VST"),
            ],
            "vst3": [
                "/Library/Audio/Plug-Ins/VST3",
                os.path.join(home, "Library/Audio/Plug-Ins/VST3"),
            ],
        }
    else:  # Windows
        pf   = os.environ.get("ProgramFiles",      r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        cf   = os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files")
        return {
            "vst2": [
                os.path.join(pf,   "Steinberg", "VSTPlugins"),
                os.path.join(pf86, "Steinberg", "VSTPlugins"),
                os.path.join(pf,   "VSTPlugins"),
                os.path.join(pf86, "VSTPlugins"),
                os.path.join(cf,   "VST2"),
            ],
            "vst3": [
                os.path.join(cf, "VST3"),
            ],
        }


def _collect_stems(dirs: list, bundle_exts: tuple) -> set:
    stems = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, subdirs, files in os.walk(d):
            for entry in list(subdirs) + files:
                low = entry.lower()
                for ext in bundle_exts:
                    if low.endswith(ext):
                        stems.add(low[: -len(ext)].strip())
                        break
            subdirs[:] = [
                s for s in subdirs
                if not any(s.lower().endswith(e) for e in bundle_exts)
            ]
    return stems


def _match_plugin(name: str, stems: set) -> bool:
    n = name.lower().strip()
    if n in stems:
        return True
    for s in stems:
        if n in s or s in n:
            return True
    return False


def scan_vst_plugins(vst2_names: list, vst3_names: list) -> dict:
    """Возвращает {("vst2"|"vst3", name): bool}."""
    dirs = _vst_dirs()
    vst2_stems = _collect_stems(dirs["vst2"], (".dll", ".vst"))
    vst3_stems = _collect_stems(dirs["vst3"], (".vst3",))
    result = {}
    for n in vst2_names:
        result[("vst2", n)] = _match_plugin(n, vst2_stems)
    for n in vst3_names:
        result[("vst3", n)] = _match_plugin(n, vst3_stems)
    return result

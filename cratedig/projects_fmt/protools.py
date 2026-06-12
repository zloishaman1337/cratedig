"""Best-effort parser for Avid Pro Tools ``.ptx`` / ``.ptf`` session files.

Modern ``.ptx`` sessions are byte-obfuscated (XOR-encoded), so the internal plugin
and clip names are not recoverable without the full ptformat cipher, which is out
of scope (see docs/PLAN_0.5.2.md §6). This parser therefore recognises the format
and recovers what is safely readable: any plaintext audio file references and the
app marker. It deliberately returns nothing rather than emitting cipher garbage.
"""

from __future__ import annotations

from pathlib import Path

from .common import extract_sample_basenames, read_project_bytes

# Obfuscated PTX sessions begin with 0x03 then an ASCII "0/1" run; legacy PTF
# sessions begin with the "PTOC"/"PTf"-style marker. We accept either and the
# embedded "Pro Tools" string as confirmation.
_PT_MARKER = b"Pro Tools"


def parse_ptx(path: str | Path) -> dict:
    """Parse a .ptx/.ptf into {format, version, bpm, plugins, samples, tracks}."""
    raw = read_project_bytes(path)
    if _PT_MARKER not in raw and not raw[:1] == b"\x03":
        raise ValueError("not a Pro Tools .ptx/.ptf session (no Pro Tools marker)")

    return {
        "format": "protools",
        "version": "Pro Tools",
        "bpm": None,  # tempo lives in the obfuscated body — not recoverable
        "plugins": [],  # AAX names are XOR-encoded; emitting them would be noise
        "samples": extract_sample_basenames(raw),  # plaintext clip refs only
        "tracks": [],
    }

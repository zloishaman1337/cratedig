"""Filename/path based sample category and instrument classification."""

from __future__ import annotations

import re
from pathlib import Path

CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("drum",    ("drum", "drums", "beat", "break", "breakbeat")),
    ("bass",    ("bass", "sub", "808")),
    ("synth",   ("synth", "lead", "arp", "pluck", "stab")),
    ("pad",     ("pad", "pads", "atmos", "ambient", "drone")),
    ("vocal",   ("vocal", "vox", "voice", "chant", "phrase", "acapella")),
    ("fx",      ("fx", "sfx", "riser", "impact", "transition", "sweep", "crash")),
    ("loop",    ("loop", "groove")),
    ("oneshot", ("oneshot", "one-shot", "shot", "hit", "single")),
)

INSTRUMENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kick",   ("kick", "bd", "bassdrum", "kik")),
    ("snare",  ("snare", "snr", "sd")),
    ("clap",   ("clap", "clp")),
    ("hat",    ("hat", "hihat", "hi-hat", "hh", "openhat", "openhihat", "closedhat")),
    ("tom",    ("tom", "toms")),
    ("cymbal", ("cymbal", "crash", "ride")),
    ("perc",   ("perc", "percussion", "rim", "clave", "shaker", "tamb", "conga", "bongo")),
)


def _tokenize(path: str | Path) -> tuple[set[str], str]:
    text = str(path).lower()
    tokens = {t for t in re.split(r"[^a-z0-9#]+", text) if t}
    compact = "".join(tokens)
    return tokens, compact


def classify_category(path: str | Path) -> str | None:
    tokens, compact = _tokenize(path)
    for category, words in CATEGORY_KEYWORDS:
        for word in words:
            if word in tokens or word in compact:
                return category
    return None


def classify_instrument(path: str | Path) -> str | None:
    tokens, compact = _tokenize(path)
    for instrument, words in INSTRUMENT_KEYWORDS:
        for word in words:
            if word in tokens or word in compact:
                return instrument
    return None


def classify_from_audio(
    duration_sec: float | None,
    centroid_norm: float | None,
    zcr: float | None,
) -> tuple[str | None, str | None]:
    """Cheap fallback (category, instrument_class) from descriptors when filename gives nothing.
    centroid_norm is spectral centroid / nyquist in [0,1]; zcr in [0,1]; duration in seconds.
    """
    # Determine category from duration
    if duration_sec is not None:
        category: str | None = "loop" if duration_sec >= 1.5 else "oneshot"
    else:
        category = None

    # Determine instrument class only for short/oneshot-like sounds
    instrument_class: str | None = None
    if duration_sec is None or duration_sec < 1.5:
        if centroid_norm is not None and zcr is not None:
            # High centroid or high ZCR → hi-hat (noisy, bright)
            if centroid_norm > 0.45 or zcr > 0.15:
                instrument_class = "hat"
            # Low centroid → kick (heavy, low-frequency)
            elif centroid_norm < 0.15:
                instrument_class = "kick"
            # Mid centroid → snare
            elif centroid_norm < 0.45:
                instrument_class = "snare"

    return category, instrument_class

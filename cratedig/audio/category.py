"""Filename/path based sample category classification."""

from __future__ import annotations

import re
from pathlib import Path

CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("drum", ("drum", "drums", "beat", "breakbeat", "break", "loop")),
    ("kick", ("kick", "bd", "bassdrum", "kik")),
    ("snare", ("snare", "snr", "sd", "clap")),
    ("hat", ("hat", "hihat", "hi-hat", "hh", "openhihat", "openhat")),
    ("perc", ("perc", "percussion", "rim", "clave", "shaker", "tamb")),
    ("bass", ("bass", "sub", "808")),
    ("synth", ("synth", "lead", "pad", "arp", "pluck", "stab")),
    ("vocal", ("vocal", "vox", "voice", "chant", "phrase", "acapella")),
    ("fx", ("fx", "sfx", "riser", "impact", "transition", "sweep", "crash")),
)


def classify_category(path: str | Path) -> str | None:
    text = str(path).lower()
    tokens = {t for t in re.split(r"[^a-z0-9#]+", text) if t}
    compact = "".join(tokens)

    for category, words in CATEGORY_KEYWORDS:
        for word in words:
            if word in tokens or word in compact:
                return category
    return None

"""Configuration loading. Reads a TOML file into a typed Config object."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_NAME = "config.toml"
ENV_CONFIG = "CRATEDIG_CONFIG"


@dataclass(frozen=True)
class Paths:
    db: Path
    download_dir: Path
    library_dirs: tuple[Path, ...]
    saved_dir: Path


@dataclass(frozen=True)
class AudioCfg:
    analysis_sr: int = 22050
    extensions: tuple[str, ...] = (".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".m4a")


@dataclass(frozen=True)
class Config:
    paths: Paths
    audio: AudioCfg
    sources: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    root: Path = Path(".")

    def source(self, name: str) -> dict:
        return dict(self.sources.get(name, {}))


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p)


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config from `path`, env CRATEDIG_CONFIG, or ./config.toml.

    Missing file falls back to built-in defaults (data/ under CWD).
    """
    cfg_path = Path(path or os.environ.get(ENV_CONFIG, DEFAULT_CONFIG_NAME))
    root = cfg_path.parent if cfg_path.is_file() else Path(".")

    raw: dict = {}
    if cfg_path.is_file():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    p = raw.get("paths", {})
    paths = Paths(
        db=_resolve(root, p.get("db", "data/cratedig.db")),
        download_dir=_resolve(root, p.get("download_dir", "data/downloads")),
        library_dirs=tuple(_resolve(root, d) for d in p.get("library_dirs", [])),
        saved_dir=_resolve(root, p.get("saved_dir", "data/_saved")),
    )

    a = raw.get("audio", {})
    audio = AudioCfg(
        analysis_sr=int(a.get("analysis_sr", 22050)),
        extensions=tuple(e.lower() for e in a.get("extensions", AudioCfg.extensions)),
    )

    return Config(
        paths=paths,
        audio=audio,
        sources=raw.get("sources", {}),
        metadata=raw.get("metadata", {}),
        root=root,
    )

"""Configuration loading. Reads a TOML file into a typed Config object."""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_NAME = "config.toml"
EXAMPLE_CONFIG_NAME = "config.example.toml"
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
class PluginsCfg:
    scan_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    paths: Paths
    audio: AudioCfg
    sources: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    plugins: PluginsCfg = field(default_factory=PluginsCfg)
    root: Path = Path(".")

    def source(self, name: str) -> dict:
        return dict(self.sources.get(name, {}))


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p)


def _default_config_path() -> Path:
    """./config.toml in a source run; %APPDATA%\\cratedig\\config.toml when frozen."""
    if getattr(sys, "frozen", False):
        from .paths import user_data_dir

        return user_data_dir() / DEFAULT_CONFIG_NAME
    return Path(DEFAULT_CONFIG_NAME)


def _seed_config_if_frozen(cfg_path: Path) -> None:
    """On first frozen run, copy the bundled config.example.toml to the user dir."""
    if not getattr(sys, "frozen", False) or cfg_path.is_file():
        return
    from .paths import resource_path

    example = resource_path(EXAMPLE_CONFIG_NAME)
    if example.is_file():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, cfg_path)


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config from `path`, env CRATEDIG_CONFIG, or the default location.

    Source run: ./config.toml (missing → built-in defaults under CWD).
    Frozen build: %APPDATA%\\cratedig\\config.toml, seeded from the bundled
    config.example.toml on first run.
    """
    if path is not None:
        cfg_path = Path(path)
    else:
        env = os.environ.get(ENV_CONFIG)
        cfg_path = Path(env) if env else _default_config_path()
    _seed_config_if_frozen(cfg_path)
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

    pl = raw.get("plugins", {})
    scan_dirs = pl.get("scan_dirs", [])
    plugins = PluginsCfg(scan_dirs=tuple(str(d) for d in scan_dirs))

    return Config(
        paths=paths,
        audio=audio,
        sources=raw.get("sources", {}),
        metadata=raw.get("metadata", {}),
        plugins=plugins,
        root=root,
    )

"""Comment-preserving TOML writer using tomlkit.

Writes config.toml in place via atomic temp-file + os.replace, preserving all
comments, blank lines, and key ordering from the original file.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import tomlkit
from tomlkit import TOMLDocument

from cratedig.config import ENV_CONFIG, _default_config_path

EXAMPLE_CONFIG_NAME = "config.example.toml"


class ConfigWriterError(RuntimeError):
    """Raised on unrecoverable writer failures (missing example seed,
    unwritable target dir, malformed existing TOML)."""


def resolve_config_path(path: str | os.PathLike | None = None) -> Path:
    """Target path: explicit arg > CRATEDIG_CONFIG env > default location.

    Must mirror config.load_config exactly so the GUI writes where the app
    reads: source run → ./config.toml, frozen → %APPDATA%\\cratedig\\config.toml.
    """
    if path is not None:
        return Path(path)
    env = os.environ.get(ENV_CONFIG)
    if env:
        return Path(env)
    return _default_config_path()


def _example_path(target: Path) -> Path:
    """Locate config.example.toml next to the target (same dir load_config treats
    as root). Raise if absent — the example is the single source of seed truth."""
    candidate = target.parent / EXAMPLE_CONFIG_NAME
    if candidate.is_file():
        return candidate
    raise ConfigWriterError(
        f"Cannot find {EXAMPLE_CONFIG_NAME} next to {target}"
    )


def ensure_config_exists(path: str | os.PathLike | None = None) -> Path:
    """If the resolved target is missing, copy config.example.toml verbatim.

    Raises ConfigWriterError if the example seed cannot be found.
    """
    target = resolve_config_path(path)
    if target.is_file():
        return target
    example = _example_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)
    return target


def load_document(path: str | os.PathLike | None = None) -> TOMLDocument:
    """Seed if missing, then parse with tomlkit preserving all comments."""
    target = ensure_config_exists(path)
    return tomlkit.parse(target.read_text(encoding="utf-8"))


def write_document(doc: TOMLDocument, path: str | os.PathLike | None = None) -> Path:
    """Atomically write doc to target: temp file + os.fsync + os.replace.

    On any error, unlinks the temp so no .tmp leftovers remain.
    """
    target = resolve_config_path(path)
    content = tomlkit.dumps(doc)
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.replace(tmp_path, target)
        tmp_path = None
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    return target


# ---------------------------------------------------------------------------
# Helpers: ensure a table exists in the document
# ---------------------------------------------------------------------------

def _ensure_table(doc: TOMLDocument, key: str) -> tomlkit.container.Table:
    if key not in doc:
        doc.add(key, tomlkit.table())
    return doc[key]  # type: ignore[return-value]


def _ensure_nested_table(
    parent: tomlkit.container.Table, key: str
) -> tomlkit.container.Table:
    if key not in parent:
        parent.add(key, tomlkit.table())
    return parent[key]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Mutators — paths
# ---------------------------------------------------------------------------

def set_db_path(doc: TOMLDocument, value: str) -> None:
    _ensure_table(doc, "paths")["db"] = value


def set_download_dir(doc: TOMLDocument, value: str) -> None:
    _ensure_table(doc, "paths")["download_dir"] = value


def set_saved_dir(doc: TOMLDocument, value: str) -> None:
    _ensure_table(doc, "paths")["saved_dir"] = value


def set_library_dirs(doc: TOMLDocument, dirs: Sequence[str]) -> None:
    paths = _ensure_table(doc, "paths")
    new_array = tomlkit.array()
    for d in dirs:
        new_array.append(d)
    paths["library_dirs"] = new_array


# ---------------------------------------------------------------------------
# Mutators — audio
# ---------------------------------------------------------------------------

def set_audio_extensions(doc: TOMLDocument, extensions: Sequence[str]) -> None:
    """Normalize extensions: lowercase, dot-prefix, dedupe preserving order."""
    seen: dict[str, None] = {}
    for ext in extensions:
        normalized = ext.lower()
        if not normalized.startswith("."):
            normalized = "." + normalized
        seen[normalized] = None
    audio = _ensure_table(doc, "audio")
    new_array = tomlkit.array()
    for ext in seen:
        new_array.append(ext)
    audio["extensions"] = new_array


# ---------------------------------------------------------------------------
# Mutators — metadata
# ---------------------------------------------------------------------------

def set_metadata_cache_ttl_days(doc: TOMLDocument, days: int) -> None:
    _ensure_table(doc, "metadata")["cache_ttl_days"] = days


def set_metadata_enable_search_ranking(doc: TOMLDocument, enabled: bool) -> None:
    _ensure_table(doc, "metadata")["enable_search_ranking"] = enabled


def set_metadata_search_live_lookup(doc: TOMLDocument, enabled: bool) -> None:
    _ensure_table(doc, "metadata")["search_live_lookup"] = enabled


def set_metadata_search_max_live_lookup_hits(doc: TOMLDocument, n: int) -> None:
    _ensure_table(doc, "metadata")["search_max_live_lookup_hits"] = n


def set_discogs_token(doc: TOMLDocument, token: str) -> None:
    _ensure_table(doc, "metadata")["discogs_token"] = token


# ---------------------------------------------------------------------------
# Mutators — sources
# ---------------------------------------------------------------------------

def set_source_token(doc: TOMLDocument, name: str, token: str) -> None:
    """Set [sources.<name>].token; create the sub-table only if absent."""
    sources = _ensure_table(doc, "sources")
    _ensure_nested_table(sources, name)["token"] = token


def set_source_token_file(doc: TOMLDocument, name: str, token_file: str) -> None:
    """Set [sources.<name>].token_file; empty string keeps key but clears value."""
    sources = _ensure_table(doc, "sources")
    _ensure_nested_table(sources, name)["token_file"] = token_file


# ---------------------------------------------------------------------------
# Status helper
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TokenStatus:
    """Static token presence status. Token value never stored or shown."""
    name: str
    configured: bool
    via_file: bool

    def __repr__(self) -> str:
        return f"TokenStatus(name={self.name!r}, configured={self.configured}, via_file={self.via_file})"


def source_token_status(doc: TOMLDocument, name: str, root: Path) -> TokenStatus:
    """Static presence check — no network, token value never returned."""
    sources = doc.get("sources", {})
    source = sources.get(name, {}) if sources else {}

    inline_token: str = str(source.get("token", "") or "").strip()
    if inline_token:
        return TokenStatus(name=name, configured=True, via_file=False)

    token_file_raw: str = str(source.get("token_file", "") or "").strip()
    if token_file_raw:
        tf = Path(token_file_raw)
        if not tf.is_absolute():
            tf = root / tf
        if tf.is_file() and tf.stat().st_size > 0:
            return TokenStatus(name=name, configured=True, via_file=True)

    return TokenStatus(name=name, configured=False, via_file=False)

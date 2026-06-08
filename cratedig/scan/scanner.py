"""Filesystem scanning: walk library dirs, probe basic audio info, upsert rows.

Basic probe (duration/samplerate/channels/format/size/hash) uses soundfile +
mutagen and needs no heavy deps. Descriptor analysis (BPM/key/vector) is a
separate optional pass in `audio.analyzer`, run via index.analyze_pending.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from ..db import Database
from ..db.models import Sample
from ..audio.category import classify_category, classify_instrument


def _sha1(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def probe_file(path: Path) -> dict:
    """Return basic audio info. Each field is best-effort (None on failure)."""
    info = {
        "format": path.suffix.lstrip(".").lower() or None,
        "file_size": path.stat().st_size,
        "duration_sec": None,
        "samplerate": None,
        "channels": None,
    }
    try:
        import soundfile as sf

        si = sf.info(str(path))
        info["duration_sec"] = round(float(si.frames) / si.samplerate, 3) if si.samplerate else None
        info["samplerate"] = int(si.samplerate)
        info["channels"] = int(si.channels)
        return info
    except Exception:
        pass
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(str(path))
        if mf is not None and mf.info is not None:
            info["duration_sec"] = round(float(getattr(mf.info, "length", 0.0)), 3) or None
            info["samplerate"] = getattr(mf.info, "sample_rate", None)
            info["channels"] = getattr(mf.info, "channels", None)
    except Exception:
        pass
    return info


def index_file(db: Database, path: Path, source: str = "local") -> int | None:
    """Probe + upsert a single audio file. Returns sample id, or None on missing file."""
    if not path.is_file():
        return None
    spath = str(path.resolve())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = probe_file(path)
    sample = Sample(
        id=None,
        path=spath,
        filename=path.name,
        source=source,
        file_hash=_sha1(path),
        format=meta["format"],
        file_size=meta["file_size"],
        duration_sec=meta["duration_sec"],
        samplerate=meta["samplerate"],
        channels=meta["channels"],
        category=classify_category(path),
        instrument_class=classify_instrument(path),
        created_at=now,
    )
    return db.upsert_sample(sample)


def iter_audio_files(root: Path, extensions: tuple[str, ...]) -> Iterator[Path]:
    exts = {e.lower() for e in extensions}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _ensure_preview_cache(path: Path, preview_cache_dir: Path | None, file_hash: str) -> None:
    if preview_cache_dir is None:
        return
    try:
        from ..audio.playback import ensure_mono_preview_cache

        ensure_mono_preview_cache(path, preview_cache_dir, file_hash=file_hash)
    except Exception:
        # Scan should still index files even when a preview cache cannot be built.
        pass


def scan_directory(
    db: Database,
    root: Path,
    extensions: tuple[str, ...],
    source: str = "local",
    progress: Callable[[Path, int], None] | None = None,
    preview_cache_dir: Path | None = None,
) -> int:
    """Index every audio file under `root`. Returns count of files processed.

    Existing paths are skipped (cheap re-scan). Missing rows under `root` are
    pruned so deleted files disappear from the database on the next scan.
    `progress(path, n)` is called per newly indexed file if provided.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    count = 0
    seen_paths: set[str] = set()
    for fp in iter_audio_files(root, extensions):
        spath = str(fp.resolve())
        seen_paths.add(spath)
        if db.path_exists(spath):
            with db.lock:
                row = db.conn.execute(
                    "SELECT file_hash FROM samples WHERE path=?", (spath,)
                ).fetchone()
            file_hash = row["file_hash"] if row is not None else None
            if file_hash is None:
                file_hash = _sha1(fp)
            _ensure_preview_cache(fp, preview_cache_dir, file_hash)
            if source == "edit":
                meta = probe_file(fp)
                sample = Sample(
                    id=None,
                    path=spath,
                    filename=fp.name,
                    source=source,
                    file_hash=file_hash,
                    format=meta["format"],
                    file_size=meta["file_size"],
                    duration_sec=meta["duration_sec"],
                    samplerate=meta["samplerate"],
                    channels=meta["channels"],
                    category=classify_category(fp),
                    instrument_class=classify_instrument(fp),
                    created_at=now,
                )
                db.upsert_sample(sample)
            continue
        file_hash = _sha1(fp)
        meta = probe_file(fp)
        sample = Sample(
            id=None,
            path=spath,
            filename=fp.name,
            source=source,
            file_hash=file_hash,
            format=meta["format"],
            file_size=meta["file_size"],
            duration_sec=meta["duration_sec"],
            samplerate=meta["samplerate"],
            channels=meta["channels"],
            category=classify_category(fp),
            instrument_class=classify_instrument(fp),
            created_at=now,
        )
        db.upsert_sample(sample)
        _ensure_preview_cache(fp, preview_cache_dir, file_hash)
        count += 1
        if progress:
            progress(fp, count)
    db.prune_missing_samples(root, seen_paths)
    return count

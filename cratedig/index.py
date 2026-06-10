"""High-level indexing orchestration: scan libraries, run analysis, similarity.

This is the glue the TUI and CLI call. Keeps Textual code free of DB/audio
details.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Config
from .db import Database
from .audio.category import classify_category, classify_instrument, classify_from_audio
from .audio.features import FEATURE_DIM
from .audio.similarity import cosine_topk, aspect_topk
from .scan import scan_directory


def _worker_count() -> int:
    """Bounded thread pool size for CPU-bound librosa work (FFTs release the GIL)."""
    return max(1, min(os.cpu_count() or 1, 8))


def scan_libraries(
    db: Database, cfg: Config, progress: Callable[[Path, int], None] | None = None
) -> int:
    total = 0
    preview_cache_dir = cfg.paths.db.parent / "waveform_cache"
    for d in cfg.paths.library_dirs:
        if d.is_dir():
            total += scan_directory(db, d, cfg.audio.extensions, "local", progress, preview_cache_dir)
    # The Saved folder is a scanned root too, so Simpler exports auto-index;
    # its rows are tagged source='edit' for the pinned "Saved" tree branch.
    saved = cfg.paths.saved_dir
    if saved.is_dir():
        total += scan_directory(db, saved, cfg.audio.extensions, "edit", progress, preview_cache_dir)
    return total


def analyze_pending(
    db: Database, cfg: Config, progress: Callable[[int, int], None] | None = None
) -> int:
    """Compute descriptors for every sample lacking a feature vector.

    Imported lazily so the app runs without librosa until analysis is requested.
    """
    from .audio.analyzer import analyze

    with db.lock:
        rows = db.conn.execute(
            "SELECT id, path, duration_sec, file_hash FROM samples "
            "WHERE feature_vector IS NULL OR feature_dim IS NULL OR feature_dim != ? "
            "OR waveform_preview IS NULL",
            (FEATURE_DIM,),
        ).fetchall()
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache_dir = None
    paths = getattr(cfg, "paths", None)
    if paths is not None and getattr(paths, "db", None) is not None:
        cache_dir = paths.db.parent / "waveform_cache"

    def _process(r):
        """Decode + analyze one file once; returns the UPDATE param tuple (or None)."""
        sid, path, duration, file_hash = int(r["id"]), r["path"], r["duration_sec"], r["file_hash"]
        if not Path(path).is_file():
            return None
        d = analyze(path, sr=cfg.audio.analysis_sr)
        cat = classify_category(path) or None
        instr = classify_instrument(path) or None
        if cat is None or instr is None:
            fb_cat, fb_instr = classify_from_audio(duration, d.centroid_norm, d.zcr)
            cat = cat or fb_cat
            instr = instr or fb_instr
        # Build the GUI's high-res mono preview now so the first editor open of a
        # long sample is instant (no on-demand ffmpeg decode in the worker).
        if cache_dir is not None:
            try:
                from .audio.playback import ensure_mono_preview_cache

                ensure_mono_preview_cache(path, cache_dir, file_hash=file_hash)
            except Exception:
                pass
        return (
            d.bpm, d.musical_key, d.key_scale, d.loudness_lufs,
            d.waveform_preview,
            d.vector.astype("float32").tobytes() if d.vector is not None else None,
            int(d.vector.shape[0]) if d.vector is not None else None,
            now, cat, instr, sid,
        )

    # COALESCE keeps a previously-classified value when this pass yields None
    # (cryptic filename + failed audio fallback), so re-analyze never wipes a
    # good category/class.
    update_sql = (
        "UPDATE samples SET bpm=?, musical_key=?, key_scale=?, loudness_lufs=?, "
        "waveform_preview=?, feature_vector=?, feature_dim=?, analyzed_at=?, "
        "category=COALESCE(?, category), instrument_class=COALESCE(?, instrument_class) "
        "WHERE id=?"
    )
    total = len(rows)
    done = 0
    batch: list[tuple] = []

    def _flush() -> None:
        if not batch:
            return
        with db.lock:
            db.conn.executemany(update_sql, batch)
            db.conn.commit()
        batch.clear()

    with ThreadPoolExecutor(max_workers=_worker_count()) as pool:
        for params in pool.map(_process, rows):
            if params is not None:
                done += 1
                batch.append(params)
                if len(batch) >= 64:
                    _flush()
                if progress:
                    progress(done, total)
    _flush()
    return done


def classify_pending(
    db: Database, progress: Callable[[int, int], None] | None = None
) -> int:
    """Fill missing sample categories and instrument classes from filename/path heuristics."""
    with db.lock:
        rows = db.conn.execute(
            "SELECT id, path FROM samples "
            "WHERE (category IS NULL OR category = '' OR instrument_class IS NULL) "
            "AND classify_attempted = 0"
        ).fetchall()

    done = 0
    updates: list[tuple[str | None, str | None, int, int]] = []
    for r in rows:
        cat = classify_category(r["path"]) or None
        instr = classify_instrument(r["path"]) or None
        # Mark every processed row attempted=1. The filename heuristic is
        # deterministic, so re-running yields identical results; leaving partial
        # rows (e.g. instrument hit, no category) at attempted=0 only re-processed
        # them every pass for no gain.
        updates.append((cat, instr, 1, int(r["id"])))
        done += 1
        if progress:
            progress(done, len(rows))
    if updates:
        with db.lock:
            db.conn.executemany(
                "UPDATE samples SET "
                "category=COALESCE(?, category), "
                "instrument_class=COALESCE(?, instrument_class), "
                "classify_attempted=? "
                "WHERE id=?",
                updates,
            )
            db.conn.commit()
    return done


def tag_pending(
    db: Database, cfg: Config, progress: Callable[[int, int], None] | None = None
) -> int:
    """Derive character tags for indexed audio and replace only prior auto tags."""
    from .audio.descriptors import derive_character_tags

    try:
        import librosa
    except ImportError as e:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Auto-tagging needs librosa. Install: pip install 'cratedig[analysis]'"
        ) from e

    with db.lock:
        rows = db.conn.execute(
            """
            SELECT id, path FROM samples s
            WHERE (analyzed_at IS NOT NULL OR feature_vector IS NOT NULL OR waveform_preview IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM sample_tags st
                WHERE st.sample_id=s.id AND st.source='auto'
            )
            ORDER BY indexed_at DESC
            """
        ).fetchall()

    total = len(rows)

    def _compute(r):
        """Decode + derive tags for one file (pure CPU; no DB). Returns (sid, tags)."""
        sid, path = int(r["id"]), r["path"]
        if not Path(path).is_file():
            return None
        try:
            y_stereo, sr = librosa.load(path, sr=cfg.audio.analysis_sr, mono=False)
        except Exception:
            return None
        if getattr(y_stereo, "ndim", 0) == 2:
            y_mono = y_stereo.mean(axis=0)
        else:
            y_mono = y_stereo
            y_stereo = None
        return sid, derive_character_tags(y_mono, y_stereo, sr)

    done = 0
    with ThreadPoolExecutor(max_workers=_worker_count()) as pool:
        for res in pool.map(_compute, rows):
            if res is None:
                continue
            sid, tags = res
            db.set_auto_tags_for(sid, tags)
            done += 1
            if progress:
                progress(done, total)
    return done


def find_similar(db: Database, sample_id: int, k: int = 20) -> list[tuple[int, float]]:
    query = db.get_vector(sample_id)
    if query is None:
        return []
    return cosine_topk(query, db.vectors(), k=k, exclude_id=sample_id)


def find_similar_aspects(
    db: Database, sample_id: int, aspects: list[str] | tuple[str, ...], k: int = 20
) -> list[tuple[int, float, dict[str, float]]]:
    """Aspect-weighted similar search: (id, combined_score, per_aspect_scores)."""
    query = db.get_vector(sample_id)
    if query is None:
        return []
    return aspect_topk(query, db.vectors(), aspects, k=k, exclude_id=sample_id)

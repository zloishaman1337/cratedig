"""High-level indexing orchestration: scan libraries, run analysis, similarity.

This is the glue the TUI and CLI call. Keeps Textual code free of DB/audio
details.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Config
from .db import Database
from .audio.category import classify_category
from .audio.similarity import cosine_topk
from .scan import scan_directory


def scan_libraries(
    db: Database, cfg: Config, progress: Callable[[Path, int], None] | None = None
) -> int:
    total = 0
    for d in cfg.paths.library_dirs:
        if d.is_dir():
            total += scan_directory(db, d, cfg.audio.extensions, "local", progress)
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
            "SELECT id, path FROM samples WHERE feature_vector IS NULL"
        ).fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    done = 0
    for r in rows:
        sid, path = int(r["id"]), r["path"]
        if not Path(path).is_file():
            continue
        d = analyze(path, sr=cfg.audio.analysis_sr)
        with db.lock:
            db.conn.execute(
                "UPDATE samples SET bpm=?, musical_key=?, key_scale=?, loudness_lufs=?, "
                "feature_vector=?, feature_dim=?, analyzed_at=? WHERE id=?",
                (
                    d.bpm, d.musical_key, d.key_scale, d.loudness_lufs,
                    d.vector.astype("float32").tobytes() if d.vector is not None else None,
                    int(d.vector.shape[0]) if d.vector is not None else None,
                    now, sid,
                ),
            )
            db.conn.commit()
        done += 1
        if progress:
            progress(done, len(rows))
    return done


def classify_pending(
    db: Database, progress: Callable[[int, int], None] | None = None
) -> int:
    """Fill missing sample categories from filename/path heuristics."""
    with db.lock:
        rows = db.conn.execute(
            "SELECT id, path FROM samples WHERE category IS NULL OR category = ''"
        ).fetchall()

    done = 0
    updates: list[tuple[str, int]] = []
    for r in rows:
        category = classify_category(r["path"])
        if not category:
            continue
        updates.append((category, int(r["id"])))
        done += 1
        if progress:
            progress(done, len(rows))
    if updates:
        with db.lock:
            db.conn.executemany(
                "UPDATE samples SET category=? WHERE id=?",
                updates,
            )
            db.conn.commit()
    return done


def find_similar(db: Database, sample_id: int, k: int = 20) -> list[tuple[int, float]]:
    query = db.get_vector(sample_id)
    if query is None:
        return []
    return cosine_topk(query, db.vectors(), k=k, exclude_id=sample_id)

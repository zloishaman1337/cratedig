"""SQLite access layer. Thin wrapper over sqlite3 with helper queries."""

from __future__ import annotations

import sqlite3
from threading import RLock
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import numpy as np

from .models import Sample

SCHEMA_VERSION = "1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        # check_same_thread=False: TUI download runs in a Textual worker thread
        # (@work(thread=True)) but shares this connection created on the main thread.
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # --- schema ---------------------------------------------------------
    def _migrate(self) -> None:
        schema = resources.files("cratedig.db").joinpath("schema.sql").read_text("utf-8")
        with self.lock:
            self.conn.executescript(schema)
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SCHEMA_VERSION,),
            )
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- samples --------------------------------------------------------
    def upsert_sample(self, s: Sample, vector: np.ndarray | None = None) -> int:
        """Insert by unique path, or update the existing row. Returns id."""
        blob = vector.astype(np.float32).tobytes() if vector is not None else None
        dim = int(vector.shape[0]) if vector is not None else s.feature_dim
        now = _now()
        with self.lock:
            cur = self.conn.execute(
                """
                INSERT INTO samples (path, filename, source, file_hash, format, file_size,
                    duration_sec, samplerate, channels, bpm, musical_key, key_scale,
                    loudness_lufs, category, mood, feature_vector, feature_dim,
                    analyzed_at, created_at, indexed_at)
                VALUES (:path, :filename, :source, :file_hash, :format, :file_size,
                    :duration_sec, :samplerate, :channels, :bpm, :musical_key, :key_scale,
                    :loudness_lufs, :category, :mood, :vec, :dim, :analyzed_at, :created_at, :indexed_at)
                ON CONFLICT(path) DO UPDATE SET
                    filename=excluded.filename, source=excluded.source, file_hash=excluded.file_hash,
                    format=excluded.format, file_size=excluded.file_size, duration_sec=excluded.duration_sec,
                    samplerate=excluded.samplerate, channels=excluded.channels, bpm=excluded.bpm,
                    musical_key=excluded.musical_key, key_scale=excluded.key_scale,
                    loudness_lufs=excluded.loudness_lufs, category=excluded.category, mood=excluded.mood,
                    feature_vector=COALESCE(excluded.feature_vector, samples.feature_vector),
                    feature_dim=COALESCE(excluded.feature_dim, samples.feature_dim),
                    analyzed_at=COALESCE(excluded.analyzed_at, samples.analyzed_at),
                    indexed_at=excluded.indexed_at
                """,
                {
                    "path": s.path, "filename": s.filename, "source": s.source,
                    "file_hash": s.file_hash, "format": s.format, "file_size": s.file_size,
                    "duration_sec": s.duration_sec, "samplerate": s.samplerate, "channels": s.channels,
                    "bpm": s.bpm, "musical_key": s.musical_key, "key_scale": s.key_scale,
                    "loudness_lufs": s.loudness_lufs, "category": s.category, "mood": s.mood,
                    "vec": blob, "dim": dim, "analyzed_at": s.analyzed_at,
                    "created_at": s.created_at or now, "indexed_at": now,
                },
            )
            self.conn.commit()
            row = self.conn.execute("SELECT id FROM samples WHERE path=?", (s.path,)).fetchone()
            return int(row["id"])

    def get_sample(self, sample_id: int) -> Sample | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM samples WHERE id=?", (sample_id,)).fetchone()
        return Sample.from_row(row) if row else None

    def all_samples(self, limit: int = 1000) -> list[Sample]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM samples ORDER BY indexed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Sample.from_row(r) for r in rows]

    def count_samples(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COUNT(*) c FROM samples").fetchone()["c"])

    def duplicate_samples(self, limit: int = 1000) -> list[Sample]:
        """Samples whose file_hash appears more than once, grouped by hash."""
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT s.*
                FROM samples s
                JOIN (
                    SELECT file_hash
                    FROM samples
                    WHERE file_hash IS NOT NULL
                    GROUP BY file_hash
                    HAVING COUNT(*) > 1
                ) d ON d.file_hash = s.file_hash
                ORDER BY s.file_hash, s.filename, s.path
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [Sample.from_row(r) for r in rows]

    def get_vector(self, sample_id: int) -> np.ndarray | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT feature_vector FROM samples WHERE id=?", (sample_id,)
            ).fetchone()
        if not row or row["feature_vector"] is None:
            return None
        return np.frombuffer(row["feature_vector"], dtype=np.float32)

    def vectors(self) -> list[tuple[int, np.ndarray]]:
        """All samples that have a feature vector, as (id, vector)."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, feature_vector FROM samples WHERE feature_vector IS NOT NULL"
            ).fetchall()
        return [(int(r["id"]), np.frombuffer(r["feature_vector"], dtype=np.float32)) for r in rows]

    def path_exists(self, path: str) -> bool:
        with self.lock:
            return self.conn.execute("SELECT 1 FROM samples WHERE path=?", (path,)).fetchone() is not None

    # --- tags -----------------------------------------------------------
    def add_tag(self, sample_id: int, name: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
            self.conn.execute(
                "INSERT OR IGNORE INTO sample_tags(sample_id, tag_id) "
                "SELECT ?, id FROM tags WHERE name=?",
                (sample_id, name),
            )
            self.conn.commit()

    def tags_for(self, sample_id: int) -> list[str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT t.name FROM tags t JOIN sample_tags st ON st.tag_id=t.id "
                "WHERE st.sample_id=? ORDER BY t.name",
                (sample_id,),
            ).fetchall()
        return [r["name"] for r in rows]

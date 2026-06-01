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
            self._ensure_sample_columns()
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SCHEMA_VERSION,),
            )
            self.conn.commit()

    def _ensure_sample_columns(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(samples)").fetchall()
        }
        if "waveform_preview" not in columns:
            self.conn.execute("ALTER TABLE samples ADD COLUMN waveform_preview TEXT")

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
                    loudness_lufs, category, mood, waveform_preview, feature_vector, feature_dim,
                    analyzed_at, created_at, indexed_at)
                VALUES (:path, :filename, :source, :file_hash, :format, :file_size,
                    :duration_sec, :samplerate, :channels, :bpm, :musical_key, :key_scale,
                    :loudness_lufs, :category, :mood, :waveform_preview, :vec, :dim, :analyzed_at, :created_at, :indexed_at)
                ON CONFLICT(path) DO UPDATE SET
                    filename=excluded.filename, source=excluded.source, file_hash=excluded.file_hash,
                    format=excluded.format, file_size=excluded.file_size, duration_sec=excluded.duration_sec,
                    samplerate=excluded.samplerate, channels=excluded.channels, bpm=excluded.bpm,
                    musical_key=excluded.musical_key, key_scale=excluded.key_scale,
                    loudness_lufs=excluded.loudness_lufs, category=excluded.category, mood=excluded.mood,
                    waveform_preview=COALESCE(excluded.waveform_preview, samples.waveform_preview),
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
                    "waveform_preview": s.waveform_preview,
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

    def prune_missing_samples(self, root: Path, existing_paths: set[str], source: str | None = None) -> int:
        """Delete sample rows under root whose files are no longer present."""
        try:
            root_resolved = root.resolve()
        except OSError:
            root_resolved = root

        stale_ids: list[int] = []
        with self.lock:
            if source is None:
                rows = self.conn.execute("SELECT id, path FROM samples").fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id, path FROM samples WHERE source=?", (source,)
                ).fetchall()

        for row in rows:
            path = Path(row["path"])
            try:
                resolved = path.resolve()
                resolved.relative_to(root_resolved)
            except (OSError, ValueError):
                continue
            if str(resolved) not in existing_paths:
                stale_ids.append(int(row["id"]))

        if not stale_ids:
            return 0
        with self.lock:
            self.conn.executemany("DELETE FROM samples WHERE id=?", [(sid,) for sid in stale_ids])
            self.conn.commit()
        return len(stale_ids)

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

    # --- favorites ------------------------------------------------------
    def add_favorite(self, kind: str, ref: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO favorites(kind, ref, created_at) VALUES(?,?,?)",
                (kind, ref, _now()),
            )
            self.conn.commit()

    def remove_favorite(self, kind: str, ref: str) -> None:
        with self.lock:
            self.conn.execute(
                "DELETE FROM favorites WHERE kind=? AND ref=?",
                (kind, ref),
            )
            self.conn.commit()

    def toggle_favorite(self, kind: str, ref: str) -> bool:
        """Toggle favorite state; return the NEW state (True = now a favorite)."""
        # Single lock acquisition makes the check-then-act atomic; the reused
        # methods re-enter the same RLock.
        with self.lock:
            if self.is_favorite(kind, ref):
                self.remove_favorite(kind, ref)
                return False
            self.add_favorite(kind, ref)
            return True

    def is_favorite(self, kind: str, ref: str) -> bool:
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM favorites WHERE kind=? AND ref=? LIMIT 1",
                (kind, ref),
            ).fetchone()
        return row is not None

    def list_favorites(self, kind: str | None = None) -> list[dict]:
        with self.lock:
            if kind is not None:
                rows = self.conn.execute(
                    "SELECT kind, ref, created_at FROM favorites WHERE kind=? ORDER BY created_at, id",
                    (kind,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT kind, ref, created_at FROM favorites ORDER BY created_at, id"
                ).fetchall()
        return [dict(r) for r in rows]

    # --- recent folders -------------------------------------------------
    def touch_recent_folder(self, path: str) -> None:
        with self.lock:
            next_seq = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM recent_folders"
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO recent_folders(path, opened_at, seq) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET opened_at=excluded.opened_at, seq=excluded.seq",
                (path, _now(), next_seq),
            )
            self.conn.execute(
                "DELETE FROM recent_folders WHERE path NOT IN "
                "(SELECT path FROM recent_folders ORDER BY seq DESC LIMIT 20)"
            )
            self.conn.commit()

    def list_recent_folders(self, limit: int = 20) -> list[str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT path FROM recent_folders ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["path"] for r in rows]

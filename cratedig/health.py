"""Library health reporting layer.

Computes read-only aggregate statistics about the sample library so that a
future GUI page or CLI command can display them and offer fix actions.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cratedig.audio.features import FEATURE_DIM
from cratedig.db.database import Database


@dataclass(frozen=True)
class HealthReport:
    total: int
    unanalyzed: int          # feature_vector IS NULL OR feature_dim != FEATURE_DIM
    unknown_category: int    # category IS NULL OR category = ''
    unknown_class: int       # instrument_class IS NULL
    missing_files: int       # row.path not present on disk
    duplicate_groups: int    # number of file_hash groups with COUNT(*) > 1
    duplicate_files: int     # total files participating in duplicate groups
    stale_metadata: int      # metadata_cache rows older than ttl
    by_source: dict[str, int]


def library_health(db: Database, *, ttl_days: int = 30, check_files: bool = True) -> HealthReport:
    """Compute and return a HealthReport for the current library.

    All SQL queries are read-only and run inside db.lock. The filesystem
    missing-files check is skipped when check_files=False.
    """
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=ttl_days)
    ).isoformat(timespec="seconds")

    with db.lock:
        total: int = db.conn.execute(
            "SELECT COUNT(*) c FROM samples"
        ).fetchone()["c"]

        unanalyzed: int = db.conn.execute(
            "SELECT COUNT(*) c FROM samples "
            "WHERE feature_vector IS NULL OR feature_dim != ?",
            (FEATURE_DIM,),
        ).fetchone()["c"]

        unknown_category: int = db.conn.execute(
            "SELECT COUNT(*) c FROM samples "
            "WHERE category IS NULL OR category = ''"
        ).fetchone()["c"]

        unknown_class: int = db.conn.execute(
            "SELECT COUNT(*) c FROM samples WHERE instrument_class IS NULL"
        ).fetchone()["c"]

        dup_row = db.conn.execute(
            """
            SELECT
                COUNT(*)         AS groups,
                COALESCE(SUM(cnt), 0) AS files
            FROM (
                SELECT COUNT(*) AS cnt
                FROM samples
                WHERE file_hash IS NOT NULL
                GROUP BY file_hash
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        duplicate_groups: int = dup_row["groups"]
        duplicate_files: int = dup_row["files"]

        source_rows = db.conn.execute(
            "SELECT source, COUNT(*) cnt FROM samples GROUP BY source"
        ).fetchall()
        by_source: dict[str, int] = {r["source"]: r["cnt"] for r in source_rows}

        paths: list[str] = []
        if check_files:
            paths = [
                r["path"]
                for r in db.conn.execute("SELECT path FROM samples").fetchall()
            ]

    stale_metadata = _count_stale_metadata(db, cutoff_iso)

    missing_files = 0
    if check_files:
        missing_files = sum(1 for p in paths if not Path(p).is_file())

    return HealthReport(
        total=total,
        unanalyzed=unanalyzed,
        unknown_category=unknown_category,
        unknown_class=unknown_class,
        missing_files=missing_files,
        duplicate_groups=duplicate_groups,
        duplicate_files=duplicate_files,
        stale_metadata=stale_metadata,
        by_source=by_source,
    )


def _count_stale_metadata(db: Database, cutoff_iso: str) -> int:
    """Count metadata_cache rows with fetched_at older than cutoff_iso."""
    try:
        with db.lock:
            row = db.conn.execute(
                "SELECT COUNT(*) c FROM metadata_cache WHERE fetched_at < ?",
                (cutoff_iso,),
            ).fetchone()
        return int(row["c"])
    except sqlite3.OperationalError:
        return 0


def missing_sample_ids(db: Database) -> list[int]:
    """Return ids of samples whose path is not present on disk."""
    with db.lock:
        rows = db.conn.execute("SELECT id, path FROM samples").fetchall()
    return [int(r["id"]) for r in rows if not Path(r["path"]).is_file()]


def format_report(report: HealthReport) -> list[tuple[str, str]]:
    """Return (label, value) rows suitable for tabular display."""
    rows: list[tuple[str, str]] = [
        ("Total samples", str(report.total)),
        ("Unanalyzed", str(report.unanalyzed)),
        ("Unknown category", str(report.unknown_category)),
        ("Unknown instrument class", str(report.unknown_class)),
        ("Missing files", str(report.missing_files)),
        (
            "Duplicate groups",
            f"{report.duplicate_groups} ({report.duplicate_files} files)",
        ),
        ("Stale metadata cache", str(report.stale_metadata)),
    ]
    for source, count in sorted(report.by_source.items()):
        rows.append((f"Source: {source}", str(count)))
    return rows

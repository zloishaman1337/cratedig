"""Structured search over indexed samples: BPM range, key, mood, tags, text.

Builds parameterized SQL (no string interpolation of values).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..db import Database
from ..db.models import Sample


@dataclass
class SearchFilter:
    text: str | None = None          # matches filename
    bpm_min: float | None = None
    bpm_max: float | None = None
    musical_key: str | None = None   # e.g. 'A'
    key_scale: str | None = None     # 'major' | 'minor'
    mood: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)  # all-of (AND)
    source: str | None = None
    limit: int = 500


def run_search(db: Database, f: SearchFilter) -> list[Sample]:
    where: list[str] = []
    params: list = []

    if f.text:
        where.append("s.filename LIKE ?")
        params.append(f"%{f.text}%")
    if f.bpm_min is not None:
        where.append("s.bpm >= ?")
        params.append(f.bpm_min)
    if f.bpm_max is not None:
        where.append("s.bpm <= ?")
        params.append(f.bpm_max)
    if f.musical_key:
        where.append("s.musical_key = ?")
        params.append(f.musical_key)
    if f.key_scale:
        where.append("s.key_scale = ?")
        params.append(f.key_scale)
    if f.mood:
        where.append("s.mood = ?")
        params.append(f.mood)
    if f.category:
        where.append("s.category = ?")
        params.append(f.category)
    if f.source:
        where.append("s.source = ?")
        params.append(f.source)

    join = ""
    if f.tags:
        placeholders = ",".join("?" for _ in f.tags)
        join = (
            "JOIN sample_tags st ON st.sample_id = s.id "
            "JOIN tags t ON t.id = st.tag_id "
        )
        where.append(f"t.name IN ({placeholders})")
        params.extend(f.tags)

    sql = f"SELECT s.* FROM samples s {join}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if f.tags:
        # all-of semantics: require every requested tag to match
        sql += " GROUP BY s.id HAVING COUNT(DISTINCT t.name) = ?"
        params.append(len(f.tags))
    sql += " ORDER BY s.indexed_at DESC LIMIT ?"
    params.append(f.limit)

    with db.lock:
        rows = db.conn.execute(sql, params).fetchall()
    return [Sample.from_row(r) for r in rows]

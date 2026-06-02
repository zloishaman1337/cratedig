"""Incremental metadata lookup and ranking for track search hits."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from ..db.database import Database
from ..db.models import MetadataCacheRecord, MetadataRecord
from ..sources.base import SearchHit
from .base import MetadataQuery


_SEP_RE = re.compile(r"\s+[-–—]\s+")
_SPACE_RE = re.compile(r"\s+")


def rank_track_hits(
    db: Database | None,
    metadata_cfg: dict,
    providers: dict,
    query: str,
    hits: list[SearchHit],
) -> list[SearchHit]:
    if not db or not hits:
        return hits

    ttl_days = int(metadata_cfg.get("cache_ttl_days", 30))
    max_live_hits = int(metadata_cfg.get("search_max_live_lookup_hits", 3))
    live_allowed = _live_lookup_allowed(query, metadata_cfg)
    ranked: list[tuple[float, int, SearchHit]] = []
    for idx, hit in enumerate(hits):
        q = _query_for_hit(query, hit)
        allow_live = live_allowed and idx < max_live_hits and _query_is_specific(q)
        record = _lookup_best(db, metadata_cfg, providers, q, ttl_days, allow_live)
        score = _score(hit, record)
        if record is not None:
            _apply_metadata(hit, record, score)
        ranked.append((score, idx, hit))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [hit for _score, _idx, hit in ranked]


def _query_for_hit(query: str, hit: SearchHit) -> MetadataQuery:
    artist = hit.artist.strip() or None
    title = hit.title.strip() or query.strip() or None
    if (not artist or _looks_like_channel(artist)) and title:
        parsed_artist, parsed_title = _split_artist_title(title)
        if parsed_artist and parsed_title:
            artist, title = parsed_artist, parsed_title
    return MetadataQuery(artist=artist, title=title)


def _lookup_best(
    db: Database,
    metadata_cfg: dict,
    providers: dict,
    q: MetadataQuery,
    ttl_days: int,
    allow_live: bool,
) -> MetadataRecord | None:
    records: list[MetadataRecord] = []
    query_norm = normalize_query(q)
    for name, cls in providers.items():
        cached = db.get_metadata_cache(name, query_norm)
        if cached and not _is_stale(cached.fetched_at, ttl_days):
            record = _record_from_cache(cached)
            if record is not None:
                records.append(record)
            continue
        if not allow_live:
            continue

        provider = cls(metadata_cfg)
        try:
            if not provider.available():
                continue
            record = provider.lookup(0, q)
        except Exception:
            continue
        if record is None:
            db.upsert_metadata_cache(_negative_cache_record(name, query_norm))
            continue
        records.append(record)
        db.upsert_metadata_cache(_cache_from_record(query_norm, record))

    if not records:
        return None
    return max(records, key=lambda record: _record_quality(q, record))


def normalize_query(q: MetadataQuery) -> str:
    artist = _norm(q.artist or "")
    title = _norm(q.title or "")
    album = _norm(q.album or "")
    return f"{artist}|{title}|{album}"


def _score(hit: SearchHit, record: MetadataRecord | None) -> float:
    if record is None:
        return 0.0
    title_score = _similar(hit.title, record.title)
    artist_score = _similar(hit.artist, record.artist)
    score = 0.65 * title_score + 0.30 * artist_score
    if record.year:
        score += 0.05
        score += max(0.0, (2035 - min(record.year, 2035)) / 10000)
    return score


def _record_quality(q: MetadataQuery, record: MetadataRecord) -> float:
    quality = 0.65 * _similar(q.title, record.title)
    quality += 0.30 * _similar(q.artist, record.artist)
    if record.year:
        quality += 0.05
    return quality


def _apply_metadata(hit: SearchHit, record: MetadataRecord, score: float) -> None:
    meta = {
        "provider": record.provider,
        "ext_id": record.ext_id,
        "artist": record.artist,
        "title": record.title,
        "album": record.album,
        "year": record.year,
        "genre": record.genre,
        "score": score,
    }
    hit.extra["metadata"] = {k: v for k, v in meta.items() if v is not None}
    hit.extra["metadata_score"] = score
    if record.artist:
        hit.artist = record.artist
    if record.title:
        hit.title = record.title


def _cache_from_record(query_norm: str, record: MetadataRecord) -> MetadataCacheRecord:
    raw = record.raw_json or json.dumps(asdict(record), ensure_ascii=False)
    return MetadataCacheRecord(
        provider=record.provider,
        query_norm=query_norm,
        response_json=raw,
        ext_id=record.ext_id,
        artist=record.artist,
        title=record.title,
        album=record.album,
        year=record.year,
        genre=record.genre,
        fetched_at=_now(),
    )


def _record_from_cache(cached: MetadataCacheRecord) -> MetadataRecord:
    if cached.response_json == "{}" and not any((
        cached.ext_id, cached.artist, cached.title, cached.album, cached.year, cached.genre
    )):
        return None
    return MetadataRecord(
        sample_id=0,
        provider=cached.provider,
        ext_id=cached.ext_id,
        artist=cached.artist,
        title=cached.title,
        album=cached.album,
        year=cached.year,
        genre=cached.genre,
        raw_json=cached.response_json,
    )


def _negative_cache_record(provider: str, query_norm: str) -> MetadataCacheRecord:
    return MetadataCacheRecord(
        provider=provider,
        query_norm=query_norm,
        response_json="{}",
        fetched_at=_now(),
    )


def _is_stale(fetched_at: str | None, ttl_days: int) -> bool:
    if ttl_days <= 0 or not fetched_at:
        return True
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return fetched < datetime.now(timezone.utc) - timedelta(days=ttl_days)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _split_artist_title(text: str) -> tuple[str | None, str | None]:
    parts = _SEP_RE.split(text, maxsplit=1)
    if len(parts) != 2:
        return None, None
    artist, title = parts[0].strip(), parts[1].strip()
    return (artist or None), (title or None)


def _live_lookup_allowed(query: str, metadata_cfg: dict) -> bool:
    if not bool(metadata_cfg.get("enable_search_ranking", True)):
        return False
    if not bool(metadata_cfg.get("search_live_lookup", True)):
        return False
    min_words = int(metadata_cfg.get("search_live_lookup_min_words", 2))
    words = [word for word in _norm(query).split() if word]
    return len(words) >= min_words


def _query_is_specific(q: MetadataQuery) -> bool:
    title_words = [word for word in _norm(q.title or "").split() if word]
    if q.artist and q.title:
        return True
    return len(title_words) >= 2


def _looks_like_channel(artist: str) -> bool:
    low = artist.lower()
    return low.endswith("music") or "official" in low or "vevo" in low


def _similar(a: str | None, b: str | None) -> float:
    na, nb = _norm(a or ""), _norm(b or "")
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _norm(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\([^)]*(official|video|audio|lyrics|remaster)[^)]*\)", " ", value)
    value = re.sub(r"\[[^\]]*(official|video|audio|lyrics|remaster)[^\]]*\]", " ", value)
    value = re.sub(r"[^a-z0-9а-яё]+", " ", value)
    return _SPACE_RE.sub(" ", value).strip()

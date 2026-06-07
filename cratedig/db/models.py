"""Lightweight dataclasses mirroring DB rows. Plain data, no ORM."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Sample:
    id: int | None
    path: str
    filename: str
    source: str = "local"
    file_hash: str | None = None
    format: str | None = None
    file_size: int | None = None
    duration_sec: float | None = None
    samplerate: int | None = None
    channels: int | None = None
    bpm: float | None = None
    musical_key: str | None = None
    key_scale: str | None = None
    loudness_lufs: float | None = None
    category: str | None = None
    instrument_class: str | None = None
    mood: str | None = None
    waveform_preview: str | None = None
    classify_attempted: int = 0
    feature_dim: int | None = None
    analyzed_at: str | None = None
    created_at: str | None = None
    indexed_at: str | None = None

    @classmethod
    def from_row(cls, row) -> "Sample":
        d = dict(row)
        d.pop("feature_vector", None)  # blob handled separately
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class DownloadJob:
    id: int | None
    source: str
    query: str | None = None
    source_url: str | None = None
    status: str = "pending"
    dest_path: str | None = None
    sample_id: int | None = None
    error: str | None = None
    requested_at: str | None = None
    completed_at: str | None = None


@dataclass
class Crate:
    id: int
    name: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Crate":
        d = dict(row)
        return cls(id=int(d["id"]), name=d["name"], created_at=d["created_at"])


@dataclass
class MetadataRecord:
    sample_id: int
    provider: str
    ext_id: str | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: int | None = None
    genre: str | None = None
    raw_json: str | None = None


@dataclass
class MetadataCacheRecord:
    provider: str
    query_norm: str
    response_json: str
    ext_id: str | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: int | None = None
    genre: str | None = None
    fetched_at: str | None = None

    @classmethod
    def from_row(cls, row) -> "MetadataCacheRecord":
        d = dict(row)
        d.pop("id", None)
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})

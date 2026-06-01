-- cratedig SQLite schema. Applied idempotently on startup.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per indexed audio file (local or downloaded).
CREATE TABLE IF NOT EXISTS samples (
    id            INTEGER PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,
    filename      TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'local',   -- local | youtube | yandex | freesound | archive
    file_hash     TEXT,                            -- sha1 of file bytes (duplicate detection)
    format        TEXT,                            -- wav, mp3, ...
    file_size     INTEGER,
    duration_sec  REAL,
    samplerate    INTEGER,
    channels      INTEGER,

    -- descriptors (Sononym-style)
    bpm           REAL,
    musical_key   TEXT,                            -- e.g. 'A'
    key_scale     TEXT,                            -- 'major' | 'minor'
    loudness_lufs REAL,
    category      TEXT,                            -- oneshot/loop/drum/bass/synth/pad/vocal/fx
    instrument_class TEXT,                         -- kick/snare/hat/clap/tom/cymbal/perc (auto-classified)
    mood          TEXT,
    waveform_preview TEXT,                         -- compact TUI row preview

    -- feature vector for similarity (float32 little-endian blob) + dim for sanity
    feature_vector BLOB,
    feature_dim    INTEGER,

    analyzed_at   TEXT,                            -- ISO ts when descriptors computed
    created_at    TEXT NOT NULL,
    indexed_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_samples_bpm     ON samples(bpm);
CREATE INDEX IF NOT EXISTS idx_samples_key     ON samples(musical_key, key_scale);
CREATE INDEX IF NOT EXISTS idx_samples_hash    ON samples(file_hash);
CREATE INDEX IF NOT EXISTS idx_samples_source  ON samples(source);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sample_tags (
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (sample_id, tag_id)
);

-- Download queue / history.
CREATE TABLE IF NOT EXISTS downloads (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    query        TEXT,
    source_url   TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    dest_path    TEXT,
    sample_id    INTEGER REFERENCES samples(id) ON DELETE SET NULL,
    error        TEXT,
    requested_at TEXT NOT NULL,
    completed_at TEXT
);

-- External metadata (MusicBrainz / Discogs) keyed to a sample.
CREATE TABLE IF NOT EXISTS metadata (
    id         INTEGER PRIMARY KEY,
    sample_id  INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    provider   TEXT NOT NULL,                      -- musicbrainz | discogs
    ext_id     TEXT,                               -- mbid / discogs release id
    artist     TEXT,
    title      TEXT,
    album      TEXT,
    year       INTEGER,
    genre      TEXT,
    raw_json   TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(sample_id, provider)
);

CREATE TABLE IF NOT EXISTS favorites (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    ref        TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(kind, ref)
);

CREATE TABLE IF NOT EXISTS recent_folders (
    path      TEXT PRIMARY KEY,
    opened_at TEXT NOT NULL,
    seq       INTEGER NOT NULL
);

# cratedig — Architecture

A local, TUI-first fork of Sononym: index a sample library, search by descriptors
(BPM / key / mood / tags), find acoustically similar samples, and download new
audio from multiple sources into the same library.

## Layers

```
                 ┌───────────────────────────┐
                 │  tui/  (Textual)           │  presentation only
                 └─────────────┬─────────────┘
                               │ calls
                 ┌─────────────┴─────────────┐
                 │  index.py                 │  orchestration glue
                 │  (scan / analyze / similar)│
                 └───┬─────────┬─────────┬────┘
        ┌────────────┘         │         └────────────┐
   ┌────┴────┐          ┌──────┴──────┐         ┌──────┴──────┐
   │ scan/   │          │ audio/      │         │ search/     │
   │ probe + │          │ analyzer    │         │ query build │
   │ walk fs │          │ features    │         │ (SQL)       │
   └────┬────┘          │ similarity  │         └──────┬──────┘
        │               └──────┬──────┘                │
        └───────────┬──────────┴────────────┬──────────┘
                    │                        │
              ┌─────┴─────┐            ┌─────┴─────┐
              │ db/       │            │ config.py │
              │ sqlite    │            └───────────┘
              └─────┬─────┘
   ┌────────────────┴───────────────┐
   │ sources/ (downloaders)         │   metadata/ (enrichment)
   │ youtube · yandex · freesound   │   musicbrainz · discogs
   │ · archive  + manager(fallback) │
   └────────────────────────────────┘
```

## Data flow (Sononym-style indexing)

1. **Scan** (`scan/scanner.py`): walk `library_dirs`, probe each audio file
   (duration / samplerate / channels via soundfile→mutagen fallback), sha1 hash
   for duplicate detection, upsert a `samples` row. No heavy deps.
2. **Analyze** (`audio/analyzer.py`, optional librosa): compute BPM (beat_track),
   musical key (chroma × Krumhansl-Schmuckler profiles), loudness (RMS→dB), and a
   58-dim L2-normalized feature vector (`audio/features.py`). Stored as a float32
   blob on the sample row.
3. **Search** (`search/query.py`): parameterized SQL over descriptors — BPM range,
   key, scale, mood, tags (all-of), filename text, source.
4. **Similarity** (`audio/similarity.py`): cosine top-k over feature vectors;
   brute-force numpy now, swap to hnswlib (`[index]` extra) at scale behind the
   same `cosine_topk` interface.

## Download (combined fallback for stability)

`sources/manager.py` reads `sources.strategy`:
- `combined` → try backends in `sources.order` until one succeeds.
- `single` → use `sources.default` only.

Each backend implements the `Downloader` ABC (`sources/base.py`) and self-registers
via `@register`. Every attempt is logged to the `downloads` table.

| backend    | uses              | notes |
|------------|-------------------|-------|
| youtube    | yt-dlp + ffmpeg   | also Bandcamp/SoundCloud; `ytsearch1:` for text |
| yandex     | bundled yamdl.exe | confirm CLI flags in `yandex.py._build_args` |
| freesound  | FreeSound APIv2   | token-only → HQ mp3 previews (sampling-grade) |
| archive    | internetarchive   | public items, no key |

Downloaded files land in `download_dir`; re-scanning that folder indexes them with
the proper `source`.

## Metadata enrichment

`metadata/` providers (MusicBrainz, Discogs) implement `MetadataProvider` and write
`metadata` rows keyed `(sample_id, provider)`. Not wired into the TUI yet (next
session).

## Database

SQLite (WAL), schema in `cratedig/db/schema.sql`, applied idempotently on startup.
Tables: `samples`, `tags`, `sample_tags`, `downloads`, `metadata`, `meta`.

## Key decisions

- **Optional librosa.** Core app (scan/browse/search/download) runs with light
  deps; analysis is `pip install 'cratedig[analysis]'`. Imported lazily.
- **Plugin registries** for sources and metadata keep backends decoupled and make
  adding a source a one-file change.
- **No ORM.** Plain dataclasses + parameterized SQL; small surface, full control.

## Not done yet (roadmap)

- Auto-classification (drum/bass/synth/…) → `samples.category`.
- Duplicate-detection UI over `file_hash`.
- In-TUI audio playback / waveform.
- Download screen + metadata enrichment wired into TUI.
- hnswlib ANN index for large libraries.

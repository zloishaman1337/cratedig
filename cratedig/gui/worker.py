"""Background worker: all blocking DB/filesystem/ffmpeg work runs here."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot

from .. import files
from ..config import Config
from ..db.database import Database
from ..tui.browser import build_folder_tree
from .logic import match_als_samples, resolve_similar


def _is_saved_sample_path(path: str, saved_dir: Path) -> bool:
    try:
        Path(path).resolve().relative_to(saved_dir.resolve())
    except (OSError, ValueError):
        return False
    return True


class IndexWorker(QObject):
    """Runs all blocking operations on a QThread; results are emitted as signals."""

    # outbound signals
    treeReady = Signal(object, object, object, object, object, object, object)  # (nodes, favorites, crates, crate_samples_by_id, samples, tags_by_id, all_tags)
    progress = Signal(str, int, int)            # (phase, done, total)
    peaksReady = Signal(int, object)            # (seq, mono_ndarray)
    searchReady = Signal(int, object, str)      # (seq, hits_list[SearchHit], used_backend)
    searchProgress = Signal(int, str)           # (seq, phase)
    similarReady = Signal(int, object, int, object)  # (seq, samples_list[Sample], source_id, scores_dict)
    duplicatesReady = Signal(object)            # (samples_list[Sample])
    downloadDone = Signal(bool, str)            # (ok, message)
    failed = Signal(str, str)                   # (context, message)
    metadataReady = Signal(int, object)         # (seq, embedded_dict_or_None)
    renderReady = Signal(int, str)              # (seq, exported_wav_path)
    previewReady = Signal(int, str, float)      # (seq, staged_wav_path, duration_sec)
    stageReady = Signal(int, str)               # (seq, staged_wav_path) — drag pre-render
    healthReady = Signal(object)                # (HealthReport)
    alsMatchReady = Signal(int, object)         # (seq, match_result_dict)

    def __init__(self, db: Database, cfg: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._cfg = cfg
        self._dm = None  # lazy DownloadManager (imports source backends)
        self._last_search_seq = 0  # seq of the most recent search, reused by metadata refresh

    def _manager(self):
        """Lazily build the DownloadManager (backend imports are heavyweight)."""
        if self._dm is None:
            from ..sources import DownloadManager

            self._dm = DownloadManager(self._db, self._cfg)
        return self._dm

    @staticmethod
    def _library_load_limit() -> int | None:
        """User-configured cap on samples loaded into the tree. 0/unset → None (all)."""
        from PySide6.QtCore import QSettings
        from .settings_tabs import _keys

        raw = QSettings("cratedig", "cratedig").value(
            _keys.LIBRARY_LOAD_LIMIT, _keys.DEFAULTS[_keys.LIBRARY_LOAD_LIMIT], type=int
        )
        return int(raw) if int(raw) > 0 else None

    @Slot()
    def request_reload(self) -> None:
        """Load all samples, build folder tree, and resolve favorites."""
        try:
            limit = self._library_load_limit()
            with self._db.lock:
                samples = self._db.all_samples(limit=limit)
                fav_rows = self._db.list_favorites("sample")
                crates = self._db.list_crates()

            library_samples = [s for s in samples if getattr(s, "source", None) != "edit"]
            nodes = build_folder_tree(library_samples, self._cfg.paths.library_dirs)

            # Resolve favorite dicts (kind='sample', ref=str(sample_id)) to Sample objects.
            # We call get_sample for each, which takes db.lock internally.
            favorites: list = []
            for row in fav_rows:
                try:
                    sid = int(row["ref"])
                except (ValueError, KeyError):
                    continue
                s = self._db.get_sample(sid)
                if s is not None:
                    favorites.append(s)

            tags_map = self._db.tags_for_all()
            tags_by_id = {s.id: tags_map.get(s.id, []) for s in samples if s.id is not None}
            all_tags = self._db.all_tags()
            crate_samples_by_id = {crate.id: self._db.crate_samples(crate.id) for crate in crates}

            self.treeReady.emit(nodes, favorites, crates, crate_samples_by_id, samples, tags_by_id, all_tags)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("reload", str(exc))

    @Slot(str)
    def request_touch_recent_folder(self, path: str) -> None:
        """Record a folder visit in the recent_folders DB table."""
        try:
            self._db.touch_recent_folder(path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("touch_recent_folder", str(exc))

    @Slot(int)
    def request_toggle_favorite(self, sample_id: int) -> None:
        """Toggle a sample's favorite state in the DB, then reload the tree."""
        try:
            self._db.toggle_favorite("sample", str(sample_id))
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("toggle_favorite", str(exc))

    @Slot(int, object)
    def request_set_tags(self, sample_id: int, desired) -> None:
        """Replace sample_id's tags with the desired set (atomic), then reload."""
        try:
            self._db.set_tags_for(sample_id, list(desired))
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("set_tags", str(exc))

    @Slot(int, int)
    def request_add_to_crate(self, sample_id: int, crate_id: int) -> None:
        try:
            self._db.add_to_crate(crate_id, sample_id)
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("add_to_crate", str(exc))

    @Slot(int, str)
    def request_create_crate_with_sample(self, sample_id: int, name: str) -> None:
        try:
            crate_id = self._db.create_crate(name)
            self._db.add_to_crate(crate_id, sample_id)
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("create_crate", str(exc))

    @Slot(int)
    def request_delete(self, sample_id: int) -> None:
        """Trash the sample file and remove it from the DB, then reload."""
        from PySide6.QtCore import QSettings as _QSettings
        try:
            sample = self._db.get_sample(sample_id)
            if sample is not None:
                is_saved = (
                    getattr(sample, "source", None) == "edit"
                    or _is_saved_sample_path(sample.path, self._cfg.paths.saved_dir)
                )
                _settings = _QSettings("cratedig", "cratedig")
                recycle_for_saved = _settings.value(
                    "safety/recycle_bin_for_saved", True, type=bool
                )
                if is_saved and not recycle_for_saved:
                    Path(sample.path).unlink(missing_ok=True)
                else:
                    files.trash_file(sample.path)
            self._db.delete_sample(sample_id)
            self.request_reload()
        except RuntimeError as exc:
            self.failed.emit("delete", f"{exc} (install cratedig[gui])")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("delete", str(exc))

    @Slot(int, str)
    def request_rename(self, sample_id: int, new_name: str) -> None:
        """Rename the sample file and update DB, then reload."""
        try:
            sample = self._db.get_sample(sample_id)
            if sample is None:
                self.failed.emit("rename", "sample not found")
                return
            # FS op first, then DB: if the DB update fails the file has moved
            # but a later re-scan re-indexes it under the new path.
            new_path = files.rename_file(sample.path, new_name)
            self._db.update_sample_location(sample_id, new_path, Path(new_path).name)
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("rename", str(exc))

    @Slot(int, str)
    def request_move(self, sample_id: int, dest_dir: str) -> None:
        """Move the sample file to dest_dir and update DB, then reload."""
        try:
            sample = self._db.get_sample(sample_id)
            if sample is None:
                self.failed.emit("move", "sample not found")
                return
            new_path = files.move_file(sample.path, dest_dir)
            self._db.update_sample_location(sample_id, new_path, Path(new_path).name)
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("move", str(exc))

    @Slot()
    def request_scan_analyze(self) -> None:
        """Scan libraries, analyze pending, then reload the tree."""
        from .. import index as indexer

        try:
            def scan_progress(path: Path, count: int) -> None:
                self.progress.emit("scan", count, 0)

            with self._db.lock:
                pass  # ensure connection is accessible
            indexer.scan_libraries(self._db, self._cfg, scan_progress)

            def analyze_progress(done: int, total: int) -> None:
                self.progress.emit("analyze", done, total)

            indexer.analyze_pending(self._db, self._cfg, analyze_progress)
            indexer.tag_pending(
                self._db,
                self._cfg,
                lambda done, total: self.progress.emit("tag", done, total),
            )
            self.progress.emit("analyze", 0, 0)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("scan_analyze", str(exc))
            return

        # Auto-reload tree after scan+analyze
        self.request_reload()

    @Slot(int, str, int)
    def request_peaks(self, seq: int, path: str, width: int) -> None:
        """Decode waveform for path to mono samples used by the GUI canvas."""
        from ..audio.playback import (
            decode_waveform_mono_samples,
            load_mono_preview_cache,
            save_mono_preview_cache,
        )

        try:
            cache_dir = self._cfg.paths.db.parent / "waveform_cache"
            sample_hash = None
            with self._db.lock:
                row = self._db.conn.execute(
                    "SELECT file_hash FROM samples WHERE path=?", (path,)
                ).fetchone()
            if row is not None:
                sample_hash = row["file_hash"]
            mono = load_mono_preview_cache(cache_dir, sample_hash)
            if mono is None:
                mono = decode_waveform_mono_samples(path)
                if sample_hash:
                    save_mono_preview_cache(mono, cache_dir, sample_hash)
            self.peaksReady.emit(seq, mono)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("peaks", str(exc))

    @Slot(int, int, int, object)
    def request_similar(self, seq: int, sample_id: int, k: int, aspects) -> None:
        """Find samples nearest to sample_id by feature aspects; emit tagged with seq."""
        from .. import index as indexer

        try:
            hits = indexer.find_similar_aspects(self._db, sample_id, list(aspects), k=k)
            samples_by_id = self._db.get_samples_by_ids([sid for sid, _, _ in hits])
            samples = resolve_similar([(sid, c) for sid, c, _ in hits], samples_by_id)
            scores = {sid: combined for sid, combined, _ in hits}
            self.similarReady.emit(seq, samples, sample_id, scores)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("similar", str(exc))

    @Slot(int, str)
    def request_metadata(self, seq: int, path: str) -> None:
        """Read embedded tags from path via mutagen; emit metadataReady."""
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(path, easy=True)
            tags = {}
            if mf is not None and mf.tags:
                for k in ("artist", "title", "album", "genre", "date", "albumartist", "tracknumber"):
                    v = mf.tags.get(k)
                    if v:
                        tags[k] = v[0] if isinstance(v, list) else str(v)
            self.metadataReady.emit(seq, tags or None)
        except Exception:  # noqa: BLE001
            self.metadataReady.emit(seq, None)

    @Slot(int, str, object)
    def request_render(self, seq: int, path: str, params) -> None:
        """Render an edit of `path` to the Saved folder, auto-index it, reload.

        `params` is a plain dict: region (start,end)|None, reverse, gain_db,
        fade_in, fade_out, adsr (a,d,s,r). Emits renderReady(seq, dest_path).
        """
        from ..audio.editor import ADSR, dated_export_dir, default_export_name, render_edit, write_wav

        try:
            adsr_vals = params.get("adsr")
            adsr = ADSR(*adsr_vals) if adsr_vals else None
            edited, sr = render_edit(
                path,
                params.get("region"),
                reverse=bool(params.get("reverse", False)),
                gain_db=float(params.get("gain_db", 0.0)),
                fade_in=float(params.get("fade_in", 0.0)),
                fade_out=float(params.get("fade_out", 0.0)),
                adsr=adsr,
            )
            dest = dated_export_dir(self._cfg.paths.saved_dir) / default_export_name(path)
            write_wav(edited, sr, dest)
            self._index_saved()
            self.renderReady.emit(seq, str(dest))
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("render", str(exc))

    @Slot(int, str, object)
    def request_preview_render(self, seq: int, path: str, params) -> None:
        """Render an edit of `path` to a temp staging WAV for preview; emit previewReady.

        Does NOT auto-index or reload — the staged file is throwaway.
        """
        import tempfile
        from ..audio.editor import ADSR, render_edit, write_wav

        try:
            adsr_vals = params.get("adsr")
            adsr = ADSR(*adsr_vals) if adsr_vals else None
            edited, sr = render_edit(
                path,
                params.get("region"),
                reverse=bool(params.get("reverse", False)),
                gain_db=float(params.get("gain_db", 0.0)),
                fade_in=float(params.get("fade_in", 0.0)),
                fade_out=float(params.get("fade_out", 0.0)),
                adsr=adsr,
            )
            tmpdir = Path(tempfile.gettempdir())
            (tmpdir / f"cratedig_preview_{seq - 1}.wav").unlink(missing_ok=True)
            dest = tmpdir / f"cratedig_preview_{seq}.wav"
            write_wav(edited, sr, dest)
            frames = edited.shape[0] if hasattr(edited, "shape") else len(edited)
            duration = frames / float(max(1, sr))
            self.previewReady.emit(seq, str(dest), duration)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("preview_render", str(exc))

    @Slot(int, str, object)
    def request_stage_render(self, seq: int, path: str, params) -> None:
        """Pre-render an edit to a temp staging WAV for drag-export; emit stageReady.

        Same as a preview render but the result is kept (not played) so a drag can
        reuse it instead of rendering synchronously on the GUI thread.
        """
        import tempfile
        from ..audio.editor import ADSR, render_edit, write_wav

        try:
            adsr_vals = params.get("adsr")
            adsr = ADSR(*adsr_vals) if adsr_vals else None
            edited, sr = render_edit(
                path,
                params.get("region"),
                reverse=bool(params.get("reverse", False)),
                gain_db=float(params.get("gain_db", 0.0)),
                fade_in=float(params.get("fade_in", 0.0)),
                fade_out=float(params.get("fade_out", 0.0)),
                adsr=adsr,
            )
            tmpdir = Path(tempfile.gettempdir())
            (tmpdir / f"cratedig_stage_{seq - 1}.wav").unlink(missing_ok=True)
            dest = tmpdir / f"cratedig_stage_{seq}.wav"
            write_wav(edited, sr, dest)
            self.stageReady.emit(seq, str(dest))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("stage_render", str(exc))

    @Slot()
    def request_index_saved(self) -> None:
        """Re-scan the Saved folder (e.g. after a synchronous drag-export) and reload."""
        try:
            self._index_saved()
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("index_saved", str(exc))

    def _index_saved(self) -> None:
        """Scan only the Saved folder so exports appear without a full re-scan."""
        from ..scan import scan_directory

        saved = self._cfg.paths.saved_dir
        if saved.is_dir():
            scan_directory(
                self._db,
                saved,
                self._cfg.audio.extensions,
                "edit",
                None,
                self._cfg.paths.db.parent / "waveform_cache",
            )

    @Slot()
    def request_duplicates(self) -> None:
        """Find samples sharing a file_hash; emit the grouped list."""
        try:
            samples = self._db.duplicate_samples()
            self.duplicatesReady.emit(samples)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("duplicates", str(exc))

    @Slot(int, str, str, int)
    def request_search(self, seq: int, query: str, mode: str, limit: int) -> None:
        """Search source backends for a query; emit hits tagged with seq."""
        self._last_search_seq = seq
        try:
            def _progress(phase: str) -> None:
                self.searchProgress.emit(seq, phase)

            hits, used = self._manager().search(query, mode=mode, limit=limit, progress=_progress)
            self.searchReady.emit(seq, hits, used)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("search", str(exc))

    @Slot()
    def request_health(self) -> None:
        """Compute a library health report and emit healthReady."""
        from ..health import library_health
        try:
            ttl = int(self._cfg.metadata.get("cache_ttl_days", 30))
            report = library_health(self._db, ttl_days=ttl, check_files=True)
            self.healthReady.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("health", str(exc))

    @Slot()
    def request_remove_missing(self) -> None:
        """Delete DB rows whose file is missing on disk, then recompute health + reload."""
        from ..health import missing_sample_ids
        try:
            for sid in missing_sample_ids(self._db):
                self._db.delete_sample(sid)
            self.request_health()
            self.request_reload()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("remove_missing", str(exc))

    @Slot()
    def request_refresh_metadata(self) -> None:
        """Re-query metadata providers for the current download results with force_live=True.

        Emits searchReady with re-ranked hits so the download pane updates its list,
        then emits downloadDone(True, 'metadata refreshed') for status feedback.
        """
        try:
            mgr = self._manager()
            if hasattr(mgr, "refresh_metadata_cache"):
                hits = mgr.refresh_metadata_cache()
                if hits:
                    self.searchReady.emit(self._last_search_seq, hits, "metadata refreshed")
                self.downloadDone.emit(True, "metadata refreshed")
            else:
                self.failed.emit("refresh_metadata", "metadata refresh not available")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("refresh_metadata", str(exc))

    @Slot(int, object)
    def request_als_match(self, seq: int, names) -> None:
        """Build the basename index and match ALS sample names against the library."""
        try:
            index = self._db.samples_basename_index()
            result = match_als_samples(list(names), index)
            self.alsMatchReady.emit(seq, result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("als_match", str(exc))

    @Slot(object)
    def request_download(self, hit) -> None:
        """Download a chosen SearchHit, auto-index it, then reload the tree."""
        try:
            def progress(detail: str) -> None:
                self.progress.emit(f"download: {detail}", 0, 0)

            res = self._manager().fetch_hit(hit, auto_index=True, progress=progress)
            if res.ok:
                self.downloadDone.emit(True, f"downloaded [{res.source}] → {res.path}")
                self.request_reload()  # surface the new sample in the tree
            else:
                self.downloadDone.emit(False, f"FAILED [{res.source}] {res.error}")
        except Exception as exc:  # noqa: BLE001
            self.downloadDone.emit(False, f"download failed: {exc}")

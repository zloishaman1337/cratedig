"""Textual TUI: browse / search / scan / analyze / similarity / download.

Single main screen with two modes:
  - "browse" (default): library DataTable, search filename, find similar.
  - "download": search a backend (samples=FreeSound, tracks=Yandex→YT fallback),
    pick a candidate, download (auto-indexes into the library on success).

Long-running work (scan, analyze, search, download) runs on worker threads so
the UI stays responsive.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..config import Config
from ..audio.playback import AudioPlayer, WaveformData, decode_waveform_data, render_waveform_panel
from ..db import Database
from ..db.models import Sample
from .. import index as indexer
from ..search import SearchFilter, run_search
from ..sources import DownloadManager, SearchHit
from ..web.server import ensure_web_server, sample_url
from .status import OPERATION_ORDER, format_operations, progress_label

COLUMNS = ("id", "filename", "cat", "bpm", "key", "dur(s)", "src")
DL_COLUMNS = ("#", "title", "artist", "dur(s)", "src")
DUP_COLUMNS = ("hash", "id", "filename", "cat", "dur(s)", "src", "path")


def _row(s: Sample) -> tuple:
    key = f"{s.musical_key} {s.key_scale[:3]}" if s.musical_key and s.key_scale else "-"
    return (
        str(s.id),
        s.filename[:48],
        s.category or "-",
        f"{s.bpm:.0f}" if s.bpm else "-",
        key,
        f"{s.duration_sec:.1f}" if s.duration_sec else "-",
        s.source,
    )


def _tree_rows(samples: list[Sample], roots: tuple[Path, ...]) -> list[tuple[str, tuple]]:
    rows: list[tuple[str, tuple]] = []
    seen_folders: set[tuple[str, ...]] = set()
    resolved_roots = [r.resolve() for r in roots if str(r)]

    for sample in sorted(samples, key=lambda s: s.path.lower()):
        path = Path(sample.path)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        root_label = "Library"
        rel_parts: tuple[str, ...] = (path.name,)
        for root in resolved_roots:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            root_label = root.name or str(root)
            rel_parts = rel.parts
            break
        folder_key = (root_label,)
        if folder_key not in seen_folders:
            rows.append((f"folder:{root_label}", ("", f"▾ {root_label}", "", "", "", "", "")))
            seen_folders.add(folder_key)
        for depth, part in enumerate(rel_parts[:-1], start=1):
            folder_key = (root_label, *rel_parts[:depth])
            if folder_key in seen_folders:
                continue
            rows.append((f"folder:{'/'.join(folder_key)}", ("", f"{'  ' * depth}▾ {part}", "", "", "", "", "")))
            seen_folders.add(folder_key)

        key = str(sample.id)
        row = list(_row(sample))
        row[1] = f"{'  ' * len(rel_parts)}{sample.filename[:48]}"
        rows.append((key, tuple(row)))

    return rows


def _hit_row(i: int, h: SearchHit) -> tuple:
    dur = f"{h.duration_sec:.1f}" if h.duration_sec else "-"
    return (str(i), h.title[:50], (h.artist or "")[:24], dur, h.backend)


def _dup_row(s: Sample) -> tuple:
    dur = f"{s.duration_sec:.1f}" if s.duration_sec else "-"
    return ((s.file_hash or "-")[:10], str(s.id), s.filename[:42], s.category or "-", dur, s.source, s.path[:80])


class CratedigApp(App):
    CSS = """
    #search { dock: top; height: 3; }
    #waveform { dock: bottom; height: 13; color: $accent; }
    #operation { height: 5; color: $warning; }
    #status { dock: bottom; height: 1; color: $text-muted; }
    #mode_hint { dock: bottom; height: 1; color: $accent; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("s", "scan", "Scan libs"),
        ("a", "analyze", "Analyze"),
        ("c", "classify", "Classify"),
        ("f", "similar", "Find similar"),
        ("u", "duplicates", "Duplicates"),
        ("t", "library_tree", "Library"),
        ("p", "play", "Play/stop"),
        ("w", "waveform", "Waveform"),
        ("v", "web_panel", "Web"),
        ("z", "waveform_zoom_in", "Zoom+"),
        ("o", "waveform_zoom_out", "Zoom-"),
        ("h", "waveform_pan_left", "Pan left"),
        ("l", "waveform_pan_right", "Pan right"),
        ("j", "waveform_playhead_left", "Head left"),
        ("k", "waveform_playhead_right", "Head right"),
        ("b", "waveform_mark_start", "Sel start"),
        ("e", "waveform_mark_end", "Sel end"),
        ("g", "waveform_loop", "Loop sel"),
        ("y", "waveform_clear_selection", "Clear sel"),
        ("x", "stop", "Stop"),
        ("r", "refresh", "Refresh"),
        ("d", "toggle_download", "Download mode"),
        ("1", "set_mode_samples", "samples"),
        ("2", "set_mode_tracks", "tracks"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.db = Database(cfg.paths.db)
        self.dm = DownloadManager(self.db, cfg)
        self.mode: str = "browse"            # browse | download
        self.dl_mode: str = "samples"        # samples | tracks
        self.hits: list[SearchHit] = []
        self.player = AudioPlayer()
        self.last_preview_target: str | None = None
        self.waveform: WaveformData | None = None
        self.waveform_path: str | None = None
        self.waveform_filename: str | None = None
        self.waveform_zoom: float = 1.0
        self.waveform_offset: float = 0.0
        self.waveform_playhead: float = 0.0
        self.waveform_selection: tuple[float, float] | None = None
        self.operations: dict[str, str] = {name: "idle" for name in OPERATION_ORDER}
        self.library_operation: str | None = None
        self.browse_view: str = "library"    # library | duplicates

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Input(placeholder="search filename… (Enter)", id="search")
            yield DataTable(id="results", cursor_type="row", zebra_stripes=True)
            yield Static(format_operations(self.operations), id="operation")
        yield Static("", id="waveform")
        yield Static("", id="mode_hint")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results", DataTable)
        table.add_columns(*COLUMNS)
        self._refresh_mode_hint()
        self.refresh_results()

    # --- mode hint / status ---------------------------------------------------
    def _refresh_mode_hint(self) -> None:
        hint = self.query_one("#mode_hint", Static)
        if self.mode == "browse":
            hint.update("[browse]  arrows/click=preview  t=library  p=play  w=waveform  v=web  z/o=zoom  h/l=pan  j/k=head  b/e=sel  g=loop  y=clear  x=stop  d=download  q=quit")
        else:
            avail = self.dm.available_backends()
            badge = " ".join(f"{n}{'✓' if ok else '✗'}" for n, ok in avail.items())
            hint.update(
                f"[download · {self.dl_mode}]  arrows/click=preview  1=samples 2=tracks  Enter=download  d=back  ({badge})"
            )

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _set_operation(self, name: str, msg: str) -> None:
        self.operations[name] = msg
        self.query_one("#operation", Static).update(format_operations(self.operations))

    def _set_waveform(self, msg: str) -> None:
        self.query_one("#waveform", Static).update(msg)

    def _waveform_visible_seconds(self) -> float:
        if self.waveform is None:
            return 0.0
        return self.waveform.duration_sec / max(1.0, self.waveform_zoom)

    def _render_waveform_view(self) -> None:
        if self.waveform is None:
            return
        width = max(20, min(140, self.size.width - 4))
        selection = self.waveform_selection
        body = render_waveform_panel(
            self.waveform,
            width=width,
            lane_height=5,
            zoom=self.waveform_zoom,
            offset=self.waveform_offset,
            playhead_sec=self.waveform_playhead,
            selection=selection,
        )
        sel = ""
        if selection:
            a, b = sorted(selection)
            sel = f"  sel {a:.2f}-{b:.2f}s"
        title = f"{(self.waveform_filename or 'waveform')[:48]}  head {self.waveform_playhead:.2f}s{sel}"
        self._set_waveform(f"{title}\n{body}")

    def _has_waveform_for_selected_sample(self, sample: Sample | None) -> bool:
        return bool(sample and self.waveform is not None and self.waveform_path == sample.path)

    # --- data (browse) --------------------------------------------------------
    def refresh_results(self, samples: list[Sample] | None = None) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*COLUMNS)
        rows = samples if samples is not None else self.db.all_samples(limit=20000)
        self.browse_view = "library"
        if samples is None:
            for key, row in _tree_rows(rows, self.cfg.paths.library_dirs):
                table.add_row(*row, key=key)
        else:
            for s in rows:
                table.add_row(*_row(s), key=str(s.id))
        self._set_status(f"{len(rows)} shown · {self.db.count_samples()} indexed")

    def show_duplicates(self) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*DUP_COLUMNS)
        rows = self.db.duplicate_samples()
        self.browse_view = "duplicates"
        for s in rows:
            table.add_row(*_dup_row(s), key=str(s.id))
        groups = len({s.file_hash for s in rows if s.file_hash})
        self._set_status(f"{len(rows)} duplicate files across {groups} hash groups · r=library")

    def _selected_id(self) -> int | None:
        table = self.query_one("#results", DataTable)
        if table.row_count == 0:
            return None
        try:
            key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value
            return int(key)
        except Exception:
            return None

    def _selected_sample(self) -> Sample | None:
        sid = self._selected_id()
        return self.db.get_sample(sid) if sid is not None else None

    # --- data (download) ------------------------------------------------------
    def _show_hits(self, hits: list[SearchHit]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*DL_COLUMNS)
        self.hits = hits
        for i, h in enumerate(hits):
            table.add_row(*_hit_row(i, h), key=str(i))

    def _selected_hit(self) -> SearchHit | None:
        table = self.query_one("#results", DataTable)
        if table.row_count == 0 or not self.hits:
            return None
        try:
            key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value
            return self.hits[int(key)]
        except Exception:
            return None

    def _preview_hit(self, hit: SearchHit | None) -> None:
        if hit is None:
            return
        preview = hit.preview_url()
        if not preview:
            self._set_status(f"no preview for [{hit.backend}] {hit.title[:50]} · Enter downloads")
            return
        self._preview_target(preview, f"preview [{hit.backend}] {hit.title[:50]}")

    def _preview_sample(self, sample: Sample | None) -> None:
        if sample is None:
            return
        self._preview_target(sample.path, f"preview {sample.filename[:60]}")

    def _preview_target(self, target: str, status: str) -> None:
        if self.last_preview_target == target and self.player.is_playing():
            return
        try:
            self.player.play(target)
        except RuntimeError as e:
            self._set_status(str(e))
            return
        self.last_preview_target = target
        self._set_status(status)

    # --- events ---------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if self.mode == "browse":
            results = run_search(self.db, SearchFilter(text=text or None))
            self.refresh_results(results)
        else:
            if not text:
                self._set_status("type a query, Enter to search")
                return
            self._set_status(f"searching {self.dl_mode}…")
            self._do_search(text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self.mode != "download" or not self.hits:
            return
        self.action_download_selected()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self.mode == "download":
            self._preview_hit(self._selected_hit())
        else:
            self._preview_sample(self._selected_sample())

    # --- actions (browse) -----------------------------------------------------
    def action_refresh(self) -> None:
        if self.mode == "browse":
            self.refresh_results()
        else:
            self._show_hits([])
            self._set_status("hits cleared")

    def action_scan(self) -> None:
        if not self.cfg.paths.library_dirs:
            self._set_status("no library_dirs in config.toml")
            return
        if self.library_operation:
            self._set_status(f"{self.library_operation} already running")
            self._set_operation("scan", f"blocked by {self.library_operation}")
            return
        self.library_operation = "scan"
        self._set_status("scanning…")
        self._set_operation("scan", "starting")
        self._do_scan()

    def action_analyze(self) -> None:
        if self.library_operation:
            self._set_status(f"{self.library_operation} already running")
            self._set_operation("analyze", f"blocked by {self.library_operation}")
            return
        self.library_operation = "analyze"
        self._set_status("analyzing (needs librosa)…")
        self._set_operation("analyze", "starting")
        self._do_analyze()

    def action_classify(self) -> None:
        if self.library_operation:
            self._set_status(f"{self.library_operation} already running")
            self._set_operation("classify", f"blocked by {self.library_operation}")
            return
        self.library_operation = "classify"
        self._set_status("classifying categories…")
        self._set_operation("classify", "starting")
        self._do_classify()

    def action_similar(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        sid = self._selected_id()
        if sid is None:
            self._set_status("select a row first")
            return
        hits = indexer.find_similar(self.db, sid, k=30)
        if not hits:
            self._set_status("no vector — run Analyze (a) first")
            return
        samples = [self.db.get_sample(i) for i, _ in hits]
        self.refresh_results([s for s in samples if s])
        self._set_status(f"{len(hits)} similar to #{sid}")

    def action_duplicates(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        self.show_duplicates()

    def action_library_tree(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        self.refresh_results()

    def action_play(self) -> None:
        if self.mode == "download":
            self._preview_hit(self._selected_hit())
            return
        sample = self._selected_sample()
        if sample is None:
            self._set_status("select a row first")
            return
        target = sample.path
        if self.last_preview_target == target and self.player.is_playing():
            self.player.stop()
            self._set_status("stopped " + sample.filename[:60])
            return
        if self._has_waveform_for_selected_sample(sample):
            try:
                self.player.play(target, start_sec=self.waveform_playhead)
            except RuntimeError as e:
                self._set_status(str(e))
                return
            self.last_preview_target = target
            self._set_status(f"playing {sample.filename[:50]} from {self.waveform_playhead:.2f}s")
            return
        self._preview_sample(sample)

    def action_stop(self) -> None:
        self.player.stop()
        self.last_preview_target = None
        self._set_status("playback stopped")

    def action_waveform(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        sample = self._selected_sample()
        if sample is None:
            self._set_status("select a row first")
            return
        width = max(20, min(120, self.size.width - 2))
        self._set_status(f"rendering waveform for {sample.filename[:50]}…")
        self._set_operation("waveform", f"rendering {sample.filename[:40]}")
        self._do_waveform(sample.path, sample.filename, sample.channels or 2, width)

    def action_web_panel(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        sample = self._selected_sample()
        try:
            base_url = ensure_web_server(self.cfg)
        except OSError as e:
            self._set_status(f"web panel failed: {e}")
            return
        url = sample_url(base_url, sample.id if sample and sample.id is not None else None)
        webbrowser.open(url)
        if sample:
            self._set_status(f"opened web panel for {sample.filename[:50]}")
        else:
            self._set_status("opened web panel")

    def action_waveform_zoom_in(self) -> None:
        if self.waveform is None:
            return
        self.waveform_zoom = min(64.0, self.waveform_zoom * 2.0)
        self._render_waveform_view()
        self._set_status(f"waveform zoom {self.waveform_zoom:.1f}x")

    def action_waveform_zoom_out(self) -> None:
        if self.waveform is None:
            return
        self.waveform_zoom = max(1.0, self.waveform_zoom / 2.0)
        if self.waveform_zoom == 1.0:
            self.waveform_offset = 0.0
        self._render_waveform_view()
        self._set_status(f"waveform zoom {self.waveform_zoom:.1f}x")

    def action_waveform_pan_left(self) -> None:
        self._pan_waveform(-0.15)

    def action_waveform_pan_right(self) -> None:
        self._pan_waveform(0.15)

    def _pan_waveform(self, delta: float) -> None:
        if self.waveform is None:
            return
        self.waveform_offset = max(0.0, min(1.0, self.waveform_offset + delta))
        self._render_waveform_view()

    def action_waveform_playhead_left(self) -> None:
        self._move_waveform_playhead(-0.1)

    def action_waveform_playhead_right(self) -> None:
        self._move_waveform_playhead(0.1)

    def _move_waveform_playhead(self, visible_fraction: float) -> None:
        if self.waveform is None:
            return
        step = max(0.05, self._waveform_visible_seconds() * abs(visible_fraction))
        if visible_fraction < 0:
            step = -step
        self.waveform_playhead = max(0.0, min(self.waveform.duration_sec, self.waveform_playhead + step))
        if self.waveform.duration_sec > 0:
            visible = 1.0 / max(1.0, self.waveform_zoom)
            ratio = self.waveform_playhead / self.waveform.duration_sec
            if ratio < self.waveform_offset:
                self.waveform_offset = max(0.0, ratio)
            elif ratio > self.waveform_offset + visible:
                self.waveform_offset = min(1.0, ratio - visible)
        self._render_waveform_view()
        self._set_status(f"playhead {self.waveform_playhead:.2f}s")

    def action_waveform_mark_start(self) -> None:
        if self.waveform is None:
            return
        _, end = self.waveform_selection or (self.waveform_playhead, self.waveform_playhead)
        self.waveform_selection = (self.waveform_playhead, end)
        self._render_waveform_view()

    def action_waveform_mark_end(self) -> None:
        if self.waveform is None:
            return
        start, _ = self.waveform_selection or (self.waveform_playhead, self.waveform_playhead)
        self.waveform_selection = (start, self.waveform_playhead)
        self._render_waveform_view()

    def action_waveform_clear_selection(self) -> None:
        self.waveform_selection = None
        self._render_waveform_view()
        self._set_status("waveform selection cleared")

    def action_waveform_loop(self) -> None:
        sample = self._selected_sample()
        if not self._has_waveform_for_selected_sample(sample) or not self.waveform_selection:
            self._set_status("load waveform and mark b/e first")
            return
        assert sample is not None
        start, end = sorted(self.waveform_selection)
        if end - start < 0.05:
            self._set_status("selection is too short to loop")
            return
        try:
            self.player.play(sample.path, start_sec=start, duration_sec=end - start, loop=True)
        except RuntimeError as e:
            self._set_status(str(e))
            return
        self.last_preview_target = sample.path
        self._set_status(f"looping {sample.filename[:40]} {start:.2f}-{end:.2f}s")

    # --- actions (download mode) ----------------------------------------------
    def action_toggle_download(self) -> None:
        self.mode = "download" if self.mode == "browse" else "browse"
        if self.mode == "browse":
            self.refresh_results()
            self.query_one("#search", Input).placeholder = "search filename… (Enter)"
        else:
            self._show_hits([])
            self.query_one("#search", Input).placeholder = (
                f"search {self.dl_mode}… (Enter)"
            )
        self._refresh_mode_hint()

    def action_set_mode_samples(self) -> None:
        if self.mode != "download":
            return
        self.dl_mode = "samples"
        self.query_one("#search", Input).placeholder = "search samples (FreeSound)… (Enter)"
        self._refresh_mode_hint()
        self._set_status("mode: samples (FreeSound)")

    def action_set_mode_tracks(self) -> None:
        if self.mode != "download":
            return
        self.dl_mode = "tracks"
        self.query_one("#search", Input).placeholder = "search tracks (Yandex→YT)… (Enter)"
        self._refresh_mode_hint()
        self._set_status("mode: tracks (Yandex → YouTube fallback)")

    def action_download_selected(self) -> None:
        if self.mode != "download":
            return
        hit = self._selected_hit()
        if hit is None:
            self._set_status("select a hit first (after a search)")
            return
        self._set_status(f"downloading [{hit.backend}] {hit.title[:50]}…")
        self._set_operation("download", "starting")
        self._do_download(hit)

    # --- workers --------------------------------------------------------------
    @work(thread=True, group="library", exclusive=True, exit_on_error=False)
    def _do_scan(self) -> None:
        def progress(path, n) -> None:
            self.call_from_thread(
                self._set_operation,
                "scan",
                progress_label("scan", n, detail=path.name[:60]),
            )

        try:
            n = indexer.scan_libraries(self.db, self.cfg, progress=progress)
            msg = f"scanned {n} new files"
        except Exception as e:
            msg = f"scan failed: {type(e).__name__}: {e}"
        self.call_from_thread(self._after_library_work, "scan", msg)

    @work(thread=True, group="library", exclusive=True, exit_on_error=False)
    def _do_analyze(self) -> None:
        def progress(done: int, total: int) -> None:
            self.call_from_thread(
                self._set_operation,
                "analyze",
                progress_label("analyze", done, total),
            )

        try:
            n = indexer.analyze_pending(self.db, self.cfg, progress=progress)
            msg = f"analyzed {n} files"
        except RuntimeError as e:
            msg = str(e)
        except Exception as e:
            msg = f"analyze failed: {type(e).__name__}: {e}"
        self.call_from_thread(self._after_library_work, "analyze", msg)

    @work(thread=True, group="library", exclusive=True, exit_on_error=False)
    def _do_classify(self) -> None:
        def progress(done: int, total: int) -> None:
            self.call_from_thread(
                self._set_operation,
                "classify",
                progress_label("classify", done, total),
            )

        try:
            n = indexer.classify_pending(self.db, progress=progress)
            msg = f"classified {n} files"
        except Exception as e:
            msg = f"classify failed: {type(e).__name__}: {e}"
        self.call_from_thread(self._after_library_work, "classify", msg)

    @work(thread=True, group="search", exclusive=True, exit_on_error=False)
    def _do_search(self, query: str) -> None:
        hits, used = self.dm.search(query, mode=self.dl_mode, limit=20)
        self.call_from_thread(self._after_search, hits, used)

    @work(thread=True, group="download", exclusive=False, exit_on_error=False)
    def _do_download(self, hit: SearchHit) -> None:
        def progress(detail: str) -> None:
            self.call_from_thread(
                self._set_operation,
                "download",
                progress_label("download", detail=detail),
            )

        try:
            res = self.dm.fetch_hit(hit, auto_index=True, progress=progress)
            if res.ok:
                msg = f"downloaded [{res.source}] → {res.path}"
            else:
                msg = f"FAILED [{res.source}] {res.error}"
        except Exception as e:
            msg = f"download failed: {type(e).__name__}: {e}"
        self.call_from_thread(self._after_download, msg)

    @work(thread=True, group="waveform", exclusive=True, exit_on_error=False)
    def _do_waveform(self, path: str, filename: str, channels: int, width: int) -> None:
        try:
            wave = decode_waveform_data(path, bins=max(2048, width * 64), channels=channels)
            msg = wave
            status = "waveform ready"
        except RuntimeError as e:
            msg = None
            status = str(e)
        self.call_from_thread(self._after_waveform, msg, status, path, filename)

    # --- after-callbacks ------------------------------------------------------
    def _after_library_work(self, name: str, msg: str) -> None:
        self.library_operation = None
        if self.mode == "browse":
            self.refresh_results()
        self._set_operation(name, msg)
        self._set_status(msg)

    def _after_search(self, hits: list[SearchHit], used: str) -> None:
        self._show_hits(hits)
        if hits:
            self._set_status(f"{len(hits)} hits via {used} · select+Enter to download")
        else:
            self._set_status(f"no hits ({used})")

    def _after_download(self, msg: str) -> None:
        self._set_operation("download", msg)
        self._set_status(msg)

    def _after_waveform(self, msg: WaveformData | None, status: str, path: str, filename: str) -> None:
        if msg is not None:
            self.waveform = msg
            self.waveform_path = path
            self.waveform_filename = filename
            self.waveform_zoom = 1.0
            self.waveform_offset = 0.0
            self.waveform_playhead = 0.0
            self.waveform_selection = None
            self._render_waveform_view()
        else:
            self._set_waveform("")
        self._set_operation("waveform", status)
        self._set_status(status)

    def on_unmount(self) -> None:
        self.player.stop()
        self.db.close()

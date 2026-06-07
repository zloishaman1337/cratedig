"""Textual TUI: browse / search / scan / analyze / similarity / download.

Single main screen with two modes:
  - "browse" (default): library DataTable, search filename, find similar.
  - "download": search a backend (samples=FreeSound, tracks=Yandex→YT fallback),
    pick a candidate, download (auto-indexes into the library on success).

Long-running work (scan, analyze, search, download) runs on worker threads so
the UI stays responsive.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static, Tree
from textual.widgets.tree import TreeNode

from ..config import Config
from ..audio.playback import AudioPlayer
from ..db import Database
from ..db.models import Sample
from .. import index as indexer
from ..search import SearchFilter, run_search
from ..sources import DownloadManager, SearchHit
from .browser import FolderNode, build_folder_tree
from .status import OPERATION_ORDER, format_operations, progress_label

COLUMNS = ("id", "filename", "wave", "cat", "bpm", "key", "dur(s)", "src")
DL_COLUMNS = ("#", "title", "artist", "year", "album", "dur(s)", "src")
DUP_COLUMNS = ("hash", "id", "filename", "cat", "dur(s)", "src", "path")
WAVE_PLACEHOLDER = " " * 28


def _row(s: Sample) -> tuple:
    key = f"{s.musical_key} {s.key_scale[:3]}" if s.musical_key and s.key_scale else "-"
    return (
        str(s.id),
        s.filename[:48],
        s.waveform_preview or WAVE_PLACEHOLDER,
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
            rows.append((f"folder:{root_label}", ("", f"▾ {root_label}", "", "", "", "", "", "")))
            seen_folders.add(folder_key)
        for depth, part in enumerate(rel_parts[:-1], start=1):
            folder_key = (root_label, *rel_parts[:depth])
            if folder_key in seen_folders:
                continue
            rows.append((f"folder:{'/'.join(folder_key)}", ("", f"{'  ' * depth}▾ {part}", "", "", "", "", "", "")))
            seen_folders.add(folder_key)

        key = str(sample.id)
        row = list(_row(sample))
        row[1] = f"{'  ' * len(rel_parts)}{sample.filename[:48]}"
        rows.append((key, tuple(row)))

    return rows


def _hit_row(i: int, h: SearchHit) -> tuple:
    meta = h.extra.get("metadata", {}) if h.extra else {}
    dur = f"{h.duration_sec:.1f}" if h.duration_sec else "-"
    title = meta.get("title") or h.title
    artist = meta.get("artist") or h.artist or ""
    year = str(meta.get("year") or "-")
    album = meta.get("album") or ""
    return (str(i), title[:50], artist[:24], year, album[:28], dur, h.backend)


def _dup_row(s: Sample) -> tuple:
    dur = f"{s.duration_sec:.1f}" if s.duration_sec else "-"
    return ((s.file_hash or "-")[:10], str(s.id), s.filename[:42], s.category or "-", dur, s.source, s.path[:80])


class CratedigApp(App):
    CSS = """
    #search { dock: top; height: 3; }
    #operation { height: 5; color: $warning; }
    #status { dock: bottom; height: 1; color: $text-muted; }
    #mode_hint { dock: bottom; height: 1; color: $accent; }
    DataTable { height: 1fr; }
    #browse_container { height: 1fr; }
    #folder_tree { width: 30; border-right: solid $panel; }
    #contents_panel { width: 1fr; }
    #breadcrumb { height: 1; color: $text-muted; padding: 0 1; }
    #contents { height: 1fr; }
    #results { height: 1fr; }
    """

    BINDINGS = [
        ("s", "scan", "Scan libs"),
        ("a", "analyze", "Analyze"),
        ("c", "classify", "Classify"),
        ("f", "similar", "Find similar"),
        ("u", "duplicates", "Duplicates"),
        ("t", "library_tree", "Library"),
        ("p", "play", "Play/stop"),
        ("x", "stop", "Stop"),
        ("r", "refresh", "Refresh"),
        ("d", "toggle_download", "Download mode"),
        ("1", "set_mode_samples", "samples"),
        ("2", "set_mode_tracks", "tracks"),
        ("b", "toggle_favorite", "Fav"),
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
        self.operations: dict[str, str] = {name: "idle" for name in OPERATION_ORDER}
        self.library_operation: str | None = None
        self.browse_view: str = "library"    # library | duplicates
        self._folder_nodes: dict[str, FolderNode] = {}
        self._selected_folder_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Input(placeholder="search filename… (Enter)", id="search")
            # Browse view: collapsible folder tree + contents table
            with Horizontal(id="browse_container"):
                yield Tree("Library", id="folder_tree")
                with Vertical(id="contents_panel"):
                    yield Static("", id="breadcrumb")
                    yield DataTable(id="contents", cursor_type="row", zebra_stripes=True)
            # Download / duplicates view: flat results table
            yield DataTable(id="results", cursor_type="row", zebra_stripes=True)
            yield Static(format_operations(self.operations), id="operation")
        yield Static("", id="mode_hint")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        results = self.query_one("#results", DataTable)
        results.add_columns(*COLUMNS)
        results.display = False

        contents = self.query_one("#contents", DataTable)
        contents.add_columns(*COLUMNS)

        self._refresh_mode_hint()
        self.refresh_results()

    # --- mode hint / status ---------------------------------------------------
    def _refresh_mode_hint(self) -> None:
        hint = self.query_one("#mode_hint", Static)
        if self.mode == "browse":
            hint.update(
                "[browse]  arrows/enter=expand  t=library  p=play  b=fav  x=stop  d=download  q=quit"
            )
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

    # --- browse tree ----------------------------------------------------------
    def _rebuild_folder_tree(self, samples: list[Sample] | None = None) -> None:
        """Rebuild the Tree widget from the current library samples."""
        if samples is None:
            samples = self.db.all_samples(limit=20000)

        self._folder_nodes = build_folder_tree(samples, self.cfg.paths.library_dirs)

        tree = self.query_one("#folder_tree", Tree)
        tree.clear()
        tree.root.expand()

        # Favorites branch at the top
        fav_folders = [f["ref"] for f in self.db.list_favorites("folder")]
        fav_samples_rows = self.db.list_favorites("sample")
        if fav_folders or fav_samples_rows:
            fav_branch = tree.root.add("★ Favorites", expand=True)
            for fk in fav_folders:
                fav_branch.add_leaf(fk, data={"type": "fav_folder", "key": fk})
            for row in fav_samples_rows:
                try:
                    sid = int(row["ref"])
                except (ValueError, KeyError):
                    continue
                s = self.db.get_sample(sid)
                if s is not None:
                    fav_branch.add_leaf(f"★ {s.filename[:40]}", data={"type": "fav_sample", "sample_id": sid})

        # Folder hierarchy
        def _add_node(parent: TreeNode, node: FolderNode) -> None:
            child_folders = sorted(node.children.values(), key=lambda n: n.name.lower())
            if child_folders:
                branch = parent.add(node.name, data={"type": "folder", "key": node.key})
                for child in child_folders:
                    _add_node(branch, child)
            else:
                parent.add_leaf(node.name, data={"type": "folder", "key": node.key})

        root_nodes = sorted(
            (n for n in self._folder_nodes.values() if n.parent_key is None),
            key=lambda n: n.name.lower(),
        )
        for rn in root_nodes:
            _add_node(tree.root, rn)

    def _load_folder_contents(self, folder_key: str) -> None:
        """Populate the contents DataTable with direct samples of folder_key."""
        self._selected_folder_key = folder_key
        self.query_one("#breadcrumb", Static).update(folder_key)
        self.db.touch_recent_folder(folder_key)

        node = self._folder_nodes.get(folder_key)
        samples = node.samples if node else []

        contents = self.query_one("#contents", DataTable)
        contents.clear(columns=True)
        contents.add_columns(*COLUMNS)
        for s in sorted(samples, key=lambda x: x.filename.lower()):
            contents.add_row(*_row(s), key=str(s.id))

        self._set_status(f"{folder_key} · {len(samples)} sample(s)")

    def _refresh_favorites_branch(self) -> None:
        """Rebuild the entire tree (simplest way to refresh favorites)."""
        self._rebuild_folder_tree()

    # --- data (browse) --------------------------------------------------------
    def refresh_results(self, samples: list[Sample] | None = None) -> None:
        self.browse_view = "library"

        if self.mode == "browse":
            self._rebuild_folder_tree(samples)
            total = self.db.count_samples()
            shown = len(samples) if samples is not None else total
            self._set_status(f"{shown} shown · {total} indexed")
            return

        # Non-browse mode: use flat #results table
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*COLUMNS)
        rows = samples if samples is not None else self.db.all_samples(limit=20000)
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
        """Return selected sample id from whichever table is active."""
        # Browse-library shows the #contents table; duplicates and download
        # both live in the flat #results table.
        if self.mode == "browse" and self.browse_view != "duplicates":
            table = self.query_one("#contents", DataTable)
        else:
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

    # --- widget display toggling ----------------------------------------------
    def _show_browse_widgets(self) -> None:
        self.query_one("#browse_container").display = True
        self.query_one("#results").display = False

    def _show_results_widget(self) -> None:
        self.query_one("#browse_container").display = False
        self.query_one("#results").display = True

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

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if self.mode != "browse":
            return
        data = event.node.data
        if data is None:
            return
        node_type = data.get("type")
        if node_type == "folder":
            self._load_folder_contents(data["key"])
        elif node_type == "fav_folder":
            fk = data["key"]
            if fk in self._folder_nodes:
                self._load_folder_contents(fk)
            else:
                self._set_status(f"folder not found: {fk}")
        elif node_type == "fav_sample":
            sample = self.db.get_sample(data["sample_id"])
            self._preview_sample(sample)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self.mode != "download" or not self.hits:
            return
        self.action_download_selected()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "contents":
            self._preview_sample(self._selected_sample())
        elif self.mode == "download":
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
        self._show_results_widget()
        self.show_duplicates()

    def action_library_tree(self) -> None:
        if self.mode != "browse":
            self._set_status("press d to leave download mode first")
            return
        self._show_browse_widgets()
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
        self._preview_sample(sample)

    def action_stop(self) -> None:
        self.player.stop()
        self.last_preview_target = None
        self._set_status("playback stopped")

    def action_toggle_favorite(self) -> None:
        if self.mode != "browse":
            return
        # Check if a folder is highlighted in the tree
        tree = self.query_one("#folder_tree", Tree)
        node = tree.cursor_node
        if node is not None and node.data is not None:
            node_type = node.data.get("type")
            if node_type == "folder":
                fk = node.data["key"]
                if self.db.is_favorite("folder", fk):
                    self.db.remove_favorite("folder", fk)
                    self._set_status(f"removed folder favorite: {fk}")
                else:
                    self.db.add_favorite("folder", fk)
                    self._set_status(f"added folder favorite: {fk}")
                self._refresh_favorites_branch()
                return

        # Otherwise try selected sample in contents table
        sid = self._selected_id()
        if sid is None:
            self._set_status("select a sample or folder first")
            return
        ref = str(sid)
        if self.db.is_favorite("sample", ref):
            self.db.remove_favorite("sample", ref)
            self._set_status(f"removed sample favorite: #{sid}")
        else:
            self.db.add_favorite("sample", ref)
            self._set_status(f"added sample favorite: #{sid}")
        self._refresh_favorites_branch()

    # --- actions (download mode) ----------------------------------------------
    def action_toggle_download(self) -> None:
        self.mode = "download" if self.mode == "browse" else "browse"
        if self.mode == "browse":
            self._show_browse_widgets()
            self.refresh_results()
            self.query_one("#search", Input).placeholder = "search filename… (Enter)"
        else:
            self._show_results_widget()
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
            tagged = indexer.tag_pending(self.db, self.cfg, progress=progress)
            msg = f"analyzed {n} files · tagged {tagged}"
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

    # --- after-callbacks ------------------------------------------------------
    def _after_library_work(self, name: str, msg: str) -> None:
        self.library_operation = None
        if self.mode == "browse" and self.browse_view != "duplicates":
            self._show_browse_widgets()
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

    def on_unmount(self) -> None:
        self.player.stop()
        self.db.close()

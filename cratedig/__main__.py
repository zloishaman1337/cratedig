"""CLI entry point. `cratedig` launches the TUI; subcommands for headless ops."""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .db import Database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cratedig", description="TUI sample browser + downloader")
    parser.add_argument("-c", "--config", help="path to config.toml")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("tui", help="launch the TUI (default)")
    sub.add_parser("gui", help="launch the desktop GUI (requires cratedig[gui])")
    sub.add_parser("scan", help="scan library_dirs and index files")
    sub.add_parser("analyze", help="compute descriptors for unanalyzed samples")
    sub.add_parser("tag", help="derive character tags for untagged samples")
    sub.add_parser("classify", help="fill missing sample categories")
    sub.add_parser("health", help="print library health counts")
    sub.add_parser("dedup", help="list duplicate groups and their resolution plan (dry-run)")

    dl = sub.add_parser("download", help="download audio by query or URL")
    dl.add_argument("query")
    dl.add_argument("--url", action="store_true", help="treat query as a URL")
    dl.add_argument("--source", help="force a single backend")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "gui":
        try:
            from .gui import run_gui
        except ImportError as exc:
            print(f"PySide6 is required for the GUI. Install it with: pip install 'cratedig[gui]'\n({exc})", file=sys.stderr)
            return 1
        return run_gui(cfg)

    if args.cmd in (None, "tui"):
        from .tui import CratedigApp

        CratedigApp(cfg).run()
        return 0

    if args.cmd == "scan":
        from . import index as indexer

        with Database(cfg.paths.db) as db:
            n = indexer.scan_libraries(db, cfg, progress=lambda p, i: print(f"[{i}] {p.name}"))
            print(f"indexed {n} new files")
        return 0

    if args.cmd == "analyze":
        from . import index as indexer

        with Database(cfg.paths.db) as db:
            n = indexer.analyze_pending(db, cfg, progress=lambda d, t: print(f"{d}/{t}"))
            tagged = indexer.tag_pending(db, cfg, progress=lambda d, t: print(f"tag {d}/{t}"))
            print(f"analyzed {n} files")
            print(f"tagged {tagged} files")
        return 0

    if args.cmd == "tag":
        from . import index as indexer

        with Database(cfg.paths.db) as db:
            n = indexer.tag_pending(db, cfg, progress=lambda d, t: print(f"{d}/{t}"))
            print(f"tagged {n} files")
        return 0

    if args.cmd == "classify":
        from . import index as indexer

        with Database(cfg.paths.db) as db:
            n = indexer.classify_pending(db, progress=lambda d, t: print(f"{d}/{t}"))
            print(f"classified {n} files")
        return 0

    if args.cmd == "health":
        from .health import library_health, format_report

        ttl = int(cfg.metadata.get("cache_ttl_days", 30))
        with Database(cfg.paths.db) as db:
            report = library_health(db, ttl_days=ttl)
            for label, value in format_report(report):
                print(f"{label:<22} {value}")
        return 0

    if args.cmd == "dedup":
        from .dedup import plan_all

        with Database(cfg.paths.db) as db:
            plans = plan_all(db.duplicate_samples(), saved_dir=cfg.paths.saved_dir)
            if not plans:
                print("no duplicates found")
                return 0
            for i, plan in enumerate(plans, 1):
                protected_ids = {id(s) for s in plan.protected}
                print(f"\n[group {i}] keep: {plan.keep.path}")
                for s in plan.remove:
                    flag = " (GENERATED EDIT - extra confirm)" if id(s) in protected_ids else ""
                    print(f"  remove: {s.path}{flag}")
            print(f"\n{len(plans)} duplicate groups (dry-run; no files deleted)")
        return 0

    if args.cmd == "download":
        from .sources import DownloadManager

        with Database(cfg.paths.db) as db:
            res = DownloadManager(db, cfg).fetch(args.query, is_url=args.url, source=args.source)
            if res.ok:
                print(f"OK [{res.source}] {res.path}")
                return 0
            print(f"FAILED [{res.source}] {res.error}", file=sys.stderr)
            return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

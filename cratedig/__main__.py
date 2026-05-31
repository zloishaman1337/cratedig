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
    sub.add_parser("scan", help="scan library_dirs and index files")
    sub.add_parser("analyze", help="compute descriptors for unanalyzed samples")
    sub.add_parser("classify", help="fill missing sample categories")
    web = sub.add_parser("web", help="launch the local web sample panel")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    web.add_argument("--sample-id", type=int, help="open a specific sample")

    dl = sub.add_parser("download", help="download audio by query or URL")
    dl.add_argument("query")
    dl.add_argument("--url", action="store_true", help="treat query as a URL")
    dl.add_argument("--source", help="force a single backend")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

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
            print(f"analyzed {n} files")
        return 0

    if args.cmd == "classify":
        from . import index as indexer

        with Database(cfg.paths.db) as db:
            n = indexer.classify_pending(db, progress=lambda d, t: print(f"{d}/{t}"))
            print(f"classified {n} files")
        return 0

    if args.cmd == "web":
        from .web import run_web

        run_web(
            cfg,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
            sample_id=args.sample_id,
        )
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

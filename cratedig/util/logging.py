"""Minimal file logger. The TUI owns the screen, so logs go to a file."""

from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str = "cratedig", logfile: str | Path = "cratedig.log") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    handler = logging.FileHandler(logfile, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    return log

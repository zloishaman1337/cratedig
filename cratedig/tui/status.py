"""Small status formatting helpers for TUI operations."""

from __future__ import annotations

OPERATION_ORDER = ("scan", "analyze", "classify", "download", "waveform")


def progress_label(name: str, done: int | None = None, total: int | None = None, detail: str = "") -> str:
    parts = [name]
    if done is not None and total:
        pct = int((done / total) * 100)
        parts.append(f"{done}/{total} {pct}%")
    elif done is not None:
        parts.append(str(done))
    if detail:
        parts.append(detail)
    return " · ".join(parts)


def format_operations(statuses: dict[str, str], order: tuple[str, ...] = OPERATION_ORDER) -> str:
    return "\n".join(f"{name}: {statuses.get(name, 'idle')}" for name in order)

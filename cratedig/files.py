"""Filesystem operations for sample file management (rename/move/trash)."""
from __future__ import annotations

import shutil
from pathlib import Path

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


def rename_file(old_path, new_name: str) -> str:
    """Rename within the same parent directory, preserving the original suffix."""
    src = Path(old_path)
    new_stem = Path(new_name).name
    if src.suffix and new_stem.lower().endswith(src.suffix.lower()):
        new_stem = new_stem[: -len(src.suffix)]
    dst = src.with_name(f"{new_stem}{src.suffix}")
    src.rename(dst)
    return str(dst.resolve())


def move_file(old_path, dest_dir) -> str:
    """Ensure dest_dir exists, move file into it; return new absolute path str."""
    src = Path(old_path)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / src.name
    if target.exists():
        raise FileExistsError(f"destination already exists: {target}")
    result = shutil.move(str(src), str(target))
    return str(Path(result).resolve())


def trash_file(path) -> None:
    """Send file to the OS recycle bin via send2trash."""
    if send2trash is None:
        raise RuntimeError("send2trash is not installed; cannot trash file")
    send2trash(str(path))

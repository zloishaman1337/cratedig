"""Cross-platform reveal-in-file-manager helper."""
from __future__ import annotations

import os
import subprocess
import sys


def reveal_in_file_manager(path: str) -> None:
    """Reveal a file in the OS file manager (select it where supported)."""
    norm = os.path.normpath(os.path.abspath(path))
    try:
        if sys.platform == "win32":
            # Single command string: quoting the /select token breaks explorer.
            subprocess.run(f'explorer /select,"{norm}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", norm])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(norm)])
    except Exception:  # noqa: BLE001
        pass

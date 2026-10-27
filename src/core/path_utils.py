"""Windows MAX_PATH compatibility and path utilities."""

from __future__ import annotations

import os
from pathlib import Path


def safe_path(p: Path | str) -> str:
    """Ensure Windows extended-length path compatibility (\\\\?\\).

    Resolves the path and normalizes forward slashes to backslashes.
    On Windows (os.name == "nt"):
    - If already starting with \\\\?\\ or \\\\.\\, returns as-is with backslashes.
    - If starting with \\\\ (UNC share), formats as \\\\?\\UNC\\...
    - Otherwise, prepends \\\\?\\.
    On non-Windows systems, returns the resolved path string.
    """
    if not p or str(p) == "" or (isinstance(p, Path) and not p.parts):
        return ""
    resolved = Path(p).resolve()
    s = str(resolved).replace("/", "\\")
    if os.name == "nt":
        if s.startswith(("\\\\?\\", "\\\\.\\")):
            return s
        if s.startswith("\\\\"):
            return "\\\\?\\UNC\\" + s.lstrip("\\")
        return "\\\\?\\" + s
    return str(resolved)


__all__ = ["safe_path"]

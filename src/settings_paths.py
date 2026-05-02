"""Stable short hashes for QSettings keys keyed by file path."""

from __future__ import annotations

import hashlib
from pathlib import Path


def path_settings_hash(path: str | Path) -> str:
    """16-char hex from resolved path (UTF-8)."""
    p = str(Path(path).expanduser().resolve())
    return hashlib.sha256(p.encode("utf-8", errors="replace")).hexdigest()[:16]

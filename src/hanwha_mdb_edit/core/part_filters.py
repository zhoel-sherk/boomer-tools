"""Heuristics to detect Hanwha «standard library (S)» rows (T-OLP blue S icon pattern)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def is_standard_library_s_row(partname: Any, partdesc: Any) -> bool:
    """
    True if the row looks like a locked vendor «S» standard-library part in T-OLP.

    Uses observable GUI patterns from shop libraries (not an official Jet field):
    - Part Name starts with ``__`` (e.g. ``__BGA_...``)
    - Part Description contains ``[STDVER.`` (standard version tag)
    """
    pn = "" if partname is None or (isinstance(partname, float) and pd.isna(partname)) else str(partname).strip()
    pd_ = "" if partdesc is None or (isinstance(partdesc, float) and pd.isna(partdesc)) else str(partdesc).strip()
    if pn.startswith("__"):
        return True
    if "[STDVER." in pd_.upper():
        return True
    return False

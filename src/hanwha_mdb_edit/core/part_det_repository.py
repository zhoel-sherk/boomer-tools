"""Load PART_Det into a pandas DataFrame via existing hanwha_mdbtools."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from machine_library.hanwha_mdbtools import (
    HanwhaMdbToolsError,
    load_part_det_from_mdb,
    part_det_rows_to_dataframe,
)


def load_part_det_dataframe(mdb_path: str | Path) -> pd.DataFrame:
    """Return PART_Det as DataFrame (same columns as Machine lib preview)."""
    try:
        rows = load_part_det_from_mdb(mdb_path)
    except HanwhaMdbToolsError:
        raise
    return part_det_rows_to_dataframe(rows)


def dataframe_to_rows(
    df: pd.DataFrame,
) -> list[tuple[str, str, str, int, int, int]]:
    """Stable row tuples for validation / PART_Det save."""
    cols = [
        "PARTNAME",
        "PROFILENAME",
        "PARTDESC",
        "CONFIDENCE_LEVEL",
        "USED_MACHINE_SET",
        "VENDORID",
    ]
    for c in cols:
        if c not in df.columns:
            raise ValueError(f"DataFrame missing column {c!r}")
    out: list[tuple[str, str, str, int, int, int]] = []
    for _, r in df.iterrows():
        partname = str(r["PARTNAME"] if pd.notna(r["PARTNAME"]) else "").strip()
        profilename = str(r["PROFILENAME"] if pd.notna(r["PROFILENAME"]) else "").strip()
        partdesc = str(r["PARTDESC"] if pd.notna(r["PARTDESC"]) else "").strip()
        try:
            conf = int(r["CONFIDENCE_LEVEL"]) if pd.notna(r["CONFIDENCE_LEVEL"]) else 0
        except (TypeError, ValueError):
            conf = 0
        try:
            used = int(r["USED_MACHINE_SET"]) if pd.notna(r["USED_MACHINE_SET"]) else 0
        except (TypeError, ValueError):
            used = 0
        try:
            vid = int(r["VENDORID"]) if pd.notna(r["VENDORID"]) else 0
        except (TypeError, ValueError):
            vid = 0
        out.append((partname, profilename, partdesc, conf, used, vid))
    return out

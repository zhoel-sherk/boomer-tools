"""
Join PART_Det with PROFILE_Det / PROFILECOMDATA_Det / Q_HANDDATA_Det.

Semantics (Hanwha UPD):

- ``PARENTPROFILE`` — parent/base profile template (PROFILE_Det).
- ``FEEDINGSPEEDLEVEL`` — feeding speed level (PROFILECOMDATA_Det).
- ``OVERALL_SPEED_LEVEL`` — overall motion speed level Q-hand sheet (Q_HANDDATA_Det).
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from machine_library.hanwha_mdbtools import export_table_csv, list_mdb_tables

# Safety limits while scanning every joinable table (temporary wide mode).
_MAX_WIDE_TABLES = 120
_MAX_WIDE_COLUMNS = 800

_MERGED_IN_BASE = frozenset(
    {"PART_Det", "PROFILE_Det", "PROFILECOMDATA_Det", "Q_HANDDATA_Det"}
)

PART_DET_COLUMNS = (
    "PARTNAME",
    "PROFILENAME",
    "PARTDESC",
    "CONFIDENCE_LEVEL",
    "USED_MACHINE_SET",
    "VENDORID",
)

PROFILE_JOIN_COLS = ("PARENTPROFILE", "UPDPARTGROUPID")
SPEED_COM_COL = "FEEDINGSPEEDLEVEL"
SPEED_Q_COL = "OVERALL_SPEED_LEVEL"


def load_table_dataframe(mdb_path: str | Path, table: str) -> pd.DataFrame:
    csv_text = export_table_csv(mdb_path, table)
    return pd.read_csv(io.StringIO(csv_text))


def load_enriched_parts_dataframe(mdb_path: str | Path) -> pd.DataFrame:
    """PART_Det plus profile base + speed columns (one row per part)."""
    parts = load_table_dataframe(mdb_path, "PART_Det")

    prof = load_table_dataframe(mdb_path, "PROFILE_Det")
    prof = prof.drop_duplicates(subset=["PROFILENAME"], keep="first")
    prof_cols = ["PROFILENAME"] + [c for c in PROFILE_JOIN_COLS if c in prof.columns]
    prof = prof[prof_cols]

    com = load_table_dataframe(mdb_path, "PROFILECOMDATA_Det")
    com = com.drop_duplicates(subset=["PROFILENAME"], keep="first")
    if SPEED_COM_COL in com.columns:
        com = com[["PROFILENAME", SPEED_COM_COL]]
    else:
        com = pd.DataFrame(columns=["PROFILENAME", SPEED_COM_COL])

    qh = load_table_dataframe(mdb_path, "Q_HANDDATA_Det")
    qh = qh.drop_duplicates(subset=["PROFILENAME"], keep="first")
    if SPEED_Q_COL in qh.columns:
        qh = qh[["PROFILENAME", SPEED_Q_COL]]
    else:
        qh = pd.DataFrame(columns=["PROFILENAME", SPEED_Q_COL])

    out = parts.merge(prof, on="PROFILENAME", how="left")
    out = out.merge(com, on="PROFILENAME", how="left")
    out = out.merge(qh, on="PROFILENAME", how="left")
    return out


def strip_to_part_det_only(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only PART_Det columns present in ``df`` (default ``VENDORID`` = 0 if absent)."""
    out = df.copy()
    if "VENDORID" not in out.columns:
        out["VENDORID"] = 0
    cols = [c for c in PART_DET_COLUMNS if c in out.columns]
    return out[cols].copy()


def build_patch_tables(enriched: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split aggregated profile edits into per-table patches (one row per PROFILENAME)."""
    if "PROFILENAME" not in enriched.columns:
        return {"PROFILE_Det": pd.DataFrame(), "PROFILECOMDATA": pd.DataFrame(), "Q_HANDDATA": pd.DataFrame()}
    g = enriched.groupby("PROFILENAME", dropna=False).first().reset_index()

    prof_cols = ["PROFILENAME"] + [c for c in PROFILE_JOIN_COLS if c in g.columns]
    prof_patch = g[prof_cols] if len(prof_cols) > 1 else pd.DataFrame()

    com_patch = (
        g[["PROFILENAME", SPEED_COM_COL]]
        if SPEED_COM_COL in g.columns
        else pd.DataFrame(columns=["PROFILENAME", SPEED_COM_COL])
    )
    qh_patch = (
        g[["PROFILENAME", SPEED_Q_COL]]
        if SPEED_Q_COL in g.columns
        else pd.DataFrame(columns=["PROFILENAME", SPEED_Q_COL])
    )

    return {"PROFILE_Det": prof_patch, "PROFILECOMDATA": com_patch, "Q_HANDDATA": qh_patch}


def load_wide_editor_dataframe(mdb_path: str | Path) -> pd.DataFrame:
    """
    Enriched PART row plus **all** other tables that expose ``PARTNAME`` or ``PROFILENAME``,
    merged with ``TableName__column`` prefixes (except the base join keys).

    Intended as a temporary exploration mode until the schema is narrowed again.
    """
    base = load_enriched_parts_dataframe(mdb_path)
    tables = [t for t in list_mdb_tables(mdb_path) if not str(t).startswith("~")]
    merged_count = 0

    for table in tables:
        if table in _MERGED_IN_BASE:
            continue
        if len(base.columns) >= _MAX_WIDE_COLUMNS:
            break
        if merged_count >= _MAX_WIDE_TABLES:
            break
        try:
            sub = load_table_dataframe(mdb_path, table)
        except Exception:
            continue
        if sub is None or sub.empty or len(sub.columns) < 2:
            continue

        merge_key: str | None = None
        if "PARTNAME" in sub.columns and "PARTNAME" in base.columns:
            merge_key = "PARTNAME"
        elif "PROFILENAME" in sub.columns and "PROFILENAME" in base.columns:
            merge_key = "PROFILENAME"
        else:
            continue

        sub = sub.drop_duplicates(subset=[merge_key], keep="first")
        rename: dict[str, str] = {}
        for c in sub.columns:
            if c == merge_key:
                continue
            nc = f"{table}__{c}"
            n = 2
            while nc in base.columns:
                nc = f"{table}__{c}__{n}"
                n += 1
            rename[c] = nc
        sub2 = sub.rename(columns=rename)
        try:
            base = base.merge(sub2, on=merge_key, how="left")
        except Exception:
            continue
        merged_count += 1

    return base

"""
Persist PART_Det plus PROFILE / COM / Q_HANDDATA snapshots derived from enriched editor state.

Linux: CSV sidecars for PART_Det, PROFILE_Det, PROFILECOMDATA_Det, Q_HANDDATA_Det.
Windows: ODBC DELETE+INSERT PART_Det; UPDATE sibling profile tables where possible.
"""

from __future__ import annotations

import csv
import io
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from hanwha_mdb_edit.core.errors import HanwhaSaveError, HanwhaValidationError
from hanwha_mdb_edit.core.part_det_model import EditablePartDetRow
from hanwha_mdb_edit.core.part_det_repository import dataframe_to_rows
from hanwha_mdb_edit.core.part_enriched import (
    build_patch_tables,
    load_table_dataframe,
    strip_to_part_det_only,
)


@dataclass(frozen=True)
class SaveResult:
    """Outcome of persistence (PART only or full library snapshot)."""

    backup_path: Path
    mode: Literal["mdb_pyodbc", "csv_sidecar"]
    exported_paths: tuple[Path, ...]


def backup_mdb(mdb_path: str | Path) -> Path:
    """Copy ``*.mdb`` to ``*.bak-YYYYMMDDTHHMMSS`` next to it."""
    p = Path(mdb_path).resolve()
    if not p.is_file():
        raise HanwhaSaveError(f"Not a file: {p}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = p.with_name(f"{p.name}.bak-{ts}")
    shutil.copy2(p, bak)
    return bak


def _validate_part_det(df: pd.DataFrame) -> None:
    try:
        tuples = dataframe_to_rows(df)
    except ValueError as e:
        raise HanwhaValidationError(str(e)) from e
    for t in tuples:
        row = EditablePartDetRow(
            partname=t[0],
            profilename=t[1],
            partdesc=t[2],
            confidence_level=t[3],
            used_machine_set=t[4],
            vendor_id=t[5],
        )
        row.validate()


def format_part_det_csv(df: pd.DataFrame) -> str:
    """CSV text for PART_Det (mdb-export compatible)."""
    tf = dataframe_to_rows(df)
    buf = io.StringIO(newline="")
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(
        ["PARTNAME", "PROFILENAME", "PARTDESC", "CONFIDENCE_LEVEL", "USED_MACHINE_SET", "VENDORID"]
    )
    for partname, profilename, partdesc, conf, used, vid in tf:
        w.writerow([partname, profilename, partdesc, conf, used, vid])
    return buf.getvalue()


def _dataframe_to_csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue()


def _merge_snapshot(
    main: pd.DataFrame,
    patch: pd.DataFrame,
    join_key: str,
    value_cols: list[str],
) -> pd.DataFrame:
    """Overwrite ``value_cols`` in ``main`` where ``patch`` provides values for ``join_key``."""
    out = main.copy()
    if patch.empty or join_key not in patch.columns:
        return out
    pm = patch.drop_duplicates(subset=[join_key], keep="last").set_index(join_key)
    for c in value_cols:
        if c not in pm.columns or c not in out.columns:
            continue
        mapped = out[join_key].map(pm[c])
        out[c] = mapped.where(pd.notna(mapped), out[c])
    return out


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as e:
        raise HanwhaSaveError(f"Could not write {path}") from e


def _save_part_pyodbc(mdb_path: Path, df: pd.DataFrame) -> None:
    try:
        import pyodbc  # type: ignore[import-untyped]
    except ImportError as e:
        raise HanwhaSaveError("pyodbc is not installed.") from e

    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={mdb_path.resolve()};"
        r"ExtendedAnsiSQL=1;"
    )
    try:
        conn = pyodbc.connect(conn_str)
    except pyodbc.Error as e:
        raise HanwhaSaveError(
            "Could not open .mdb via ODBC (install Microsoft Access Database Engine / Office driver?)."
        ) from e

    rows = dataframe_to_rows(df)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM [PART_Det]")
        for partname, profilename, partdesc, conf, used, vid in rows:
            cur.execute(
                "INSERT INTO [PART_Det] ([PARTNAME], [PROFILENAME], [PARTDESC], [CONFIDENCE_LEVEL], [USED_MACHINE_SET], [VENDORID]) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (partname, profilename, partdesc, conf, used, vid),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HanwhaSaveError(f"ODBC PART_Det write failed: {e}") from e
    finally:
        conn.close()


def _save_profiles_pyodbc(mdb_path: Path, enriched: pd.DataFrame) -> None:
    try:
        import pyodbc  # type: ignore[import-untyped]
    except ImportError as e:
        raise HanwhaSaveError("pyodbc is not installed.") from e

    patches = build_patch_tables(enriched)
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={mdb_path.resolve()};"
        r"ExtendedAnsiSQL=1;"
    )
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    try:
        pd_tbl = patches["PROFILE_Det"]
        for _, row in pd_tbl.iterrows():
            fn = row.get("PROFILENAME")
            if pd.isna(fn) or str(fn).strip() == "":
                continue
            sets: list[str] = []
            vals: list[object] = []
            if "PARENTPROFILE" in row.index and pd.notna(row["PARENTPROFILE"]):
                sets.append("[PARENTPROFILE]=?")
                vals.append(row["PARENTPROFILE"])
            if "UPDPARTGROUPID" in row.index and pd.notna(row["UPDPARTGROUPID"]):
                sets.append("[UPDPARTGROUPID]=?")
                vals.append(int(row["UPDPARTGROUPID"]))
            if sets:
                vals.append(str(fn).strip())
                sql = f"UPDATE [PROFILE_Det] SET {', '.join(sets)} WHERE [PROFILENAME]=?"
                cur.execute(sql, tuple(vals))

        com_tbl = patches["PROFILECOMDATA"]
        for _, row in com_tbl.iterrows():
            fn = row.get("PROFILENAME")
            if pd.isna(fn) or "FEEDINGSPEEDLEVEL" not in row.index or pd.isna(row["FEEDINGSPEEDLEVEL"]):
                continue
            cur.execute(
                "UPDATE [PROFILECOMDATA_Det] SET [FEEDINGSPEEDLEVEL]=? WHERE [PROFILENAME]=?",
                (int(row["FEEDINGSPEEDLEVEL"]), str(fn).strip()),
            )

        qh_tbl = patches["Q_HANDDATA"]
        for _, row in qh_tbl.iterrows():
            fn = row.get("PROFILENAME")
            if pd.isna(fn) or "OVERALL_SPEED_LEVEL" not in row.index or pd.isna(row["OVERALL_SPEED_LEVEL"]):
                continue
            cur.execute(
                "UPDATE [Q_HANDDATA_Det] SET [OVERALL_SPEED_LEVEL]=? WHERE [PROFILENAME]=?",
                (int(row["OVERALL_SPEED_LEVEL"]), str(fn).strip()),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HanwhaSaveError(f"ODBC profile tables failed: {e}") from e
    finally:
        conn.close()


def save_enriched_library(mdb_path: str | Path, enriched_df: pd.DataFrame) -> SaveResult:
    """
    Validate PART_Det slice, merge profile patches into full exported tables,
    write CSV sidecars (always), optionally ODBC on Windows.
    """
    mdb_p = Path(mdb_path).resolve()
    part_only = strip_to_part_det_only(enriched_df)
    _validate_part_det(part_only)

    bak = backup_mdb(mdb_p)

    patches = build_patch_tables(enriched_df)

    prof_full = load_table_dataframe(mdb_p, "PROFILE_Det")
    prof_merged = _merge_snapshot(prof_full, patches["PROFILE_Det"], "PROFILENAME", ["PARENTPROFILE", "UPDPARTGROUPID"])

    com_full = load_table_dataframe(mdb_p, "PROFILECOMDATA_Det")
    com_merged = _merge_snapshot(com_full, patches["PROFILECOMDATA"], "PROFILENAME", ["FEEDINGSPEEDLEVEL"])

    qh_full = load_table_dataframe(mdb_p, "Q_HANDDATA_Det")
    qh_merged = _merge_snapshot(qh_full, patches["Q_HANDDATA"], "PROFILENAME", ["OVERALL_SPEED_LEVEL"])

    stem = mdb_p.stem
    p_part = mdb_p.with_name(f"{stem}_PART_Det_saved.csv")
    p_prof = mdb_p.with_name(f"{stem}_PROFILE_Det_saved.csv")
    p_com = mdb_p.with_name(f"{stem}_PROFILECOMDATA_saved.csv")
    p_qh = mdb_p.with_name(f"{stem}_Q_HANDDATA_saved.csv")

    _write_text(p_part, format_part_det_csv(part_only))
    _write_text(p_prof, _dataframe_to_csv(prof_merged))
    _write_text(p_com, _dataframe_to_csv(com_merged))
    _write_text(p_qh, _dataframe_to_csv(qh_merged))

    paths = (p_part, p_prof, p_com, p_qh)

    if sys.platform == "win32":
        try:
            _save_part_pyodbc(mdb_p, part_only)
            _save_profiles_pyodbc(mdb_p, enriched_df)
            return SaveResult(backup_path=bak, mode="mdb_pyodbc", exported_paths=paths)
        except HanwhaSaveError as e:
            raise HanwhaSaveError(f"{e}\nCSV snapshots still written next to:\n{mdb_p.parent}") from e

    return SaveResult(backup_path=bak, mode="csv_sidecar", exported_paths=paths)


def save_part_det(mdb_path: str | Path, df: pd.DataFrame) -> SaveResult:
    """PART_Det-only snapshot (no PROFILE/COM/Q merges). Accepts stripped or enriched ``df``."""
    part_only = strip_to_part_det_only(df)
    _validate_part_det(part_only)
    mdb_p = Path(mdb_path).resolve()
    bak = backup_mdb(mdb_p)
    p_part = mdb_p.with_name(f"{mdb_p.stem}_PART_Det_saved.csv")
    _write_text(p_part, format_part_det_csv(part_only))

    if sys.platform == "win32":
        try:
            _save_part_pyodbc(mdb_p, part_only)
            return SaveResult(backup_path=bak, mode="mdb_pyodbc", exported_paths=(p_part,))
        except HanwhaSaveError as e:
            raise HanwhaSaveError(f"{e}\nCSV snapshot still written:\n{p_part}") from e

    return SaveResult(backup_path=bak, mode="csv_sidecar", exported_paths=(p_part,))

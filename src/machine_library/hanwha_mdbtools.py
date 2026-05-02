"""
Read Hanwha/Samsung-style UPD Microsoft Access .mdb using mdbtools CLI.

Primary table for machine component names: PART_Det
  PARTNAME, PROFILENAME, PARTDESC, CONFIDENCE_LEVEL, USED_MACHINE_SET, VENDORID

Requires: mdb-tables, mdb-export on PATH (Fedora: dnf install mdbtools).
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


class HanwhaMdbToolsError(RuntimeError):
    """mdb-export / mdb-tables failed or is missing."""


@dataclass(frozen=True)
class HanwhaPartDetRow:
    """One row of PART_Det — machine library part name + vision profile link."""

    partname: str
    profilename: str
    partdesc: str
    confidence_level: int
    used_machine_set: int
    vendor_id: int = 0


def _which_or_raise(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise HanwhaMdbToolsError(f"{binary} not found on PATH; install mdbtools.")
    return path


def list_mdb_tables(mdb_path: str | Path) -> list[str]:
    """Table names as reported by mdb-tables (space-separated)."""
    p = Path(mdb_path)
    if not p.is_file():
        raise HanwhaMdbToolsError(f"Not a file: {p}")
    exe = _which_or_raise("mdb-tables")
    r = subprocess.run(
        [exe, str(p)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise HanwhaMdbToolsError(err or f"mdb-tables failed with code {r.returncode}")
    line = (r.stdout or "").strip()
    if not line:
        return []
    return line.split()


def export_table_csv(mdb_path: str | Path, table: str) -> str:
    """Raw CSV text for one table (mdb-export stdout)."""
    p = Path(mdb_path)
    if not p.is_file():
        raise HanwhaMdbToolsError(f"Not a file: {p}")
    if not re.fullmatch(r"[A-Za-z0-9_~]+", table):
        raise HanwhaMdbToolsError(f"Refusing unsafe table name: {table!r}")
    exe = _which_or_raise("mdb-export")
    r = subprocess.run(
        [exe, str(p), table],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        raise HanwhaMdbToolsError(err or f"mdb-export failed for table {table!r}")
    return r.stdout or ""


def parse_part_det_csv(csv_text: str) -> list[HanwhaPartDetRow]:
    """Parse mdb-export CSV for PART_Det."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return []
    fields = {n.upper(): n for n in reader.fieldnames}
    need = ("PARTNAME", "PROFILENAME", "PARTDESC", "CONFIDENCE_LEVEL", "USED_MACHINE_SET")
    for k in need:
        if k not in fields:
            raise HanwhaMdbToolsError(f"PART_Det CSV missing column {k}; got {reader.fieldnames!r}")

    def col(name: str) -> str:
        return fields[name.upper()]

    has_vendor = "VENDORID" in fields
    vend_col = fields.get("VENDORID")

    out: list[HanwhaPartDetRow] = []
    for d in reader:
        raw_conf = (d.get(col("CONFIDENCE_LEVEL")) or "").strip()
        raw_used = (d.get(col("USED_MACHINE_SET")) or "").strip()
        try:
            conf = int(raw_conf) if raw_conf else 0
        except ValueError:
            conf = 0
        try:
            used = int(raw_used) if raw_used else 0
        except ValueError:
            used = 0
        vid = 0
        if has_vendor and vend_col:
            raw_v = (d.get(vend_col) or "").strip()
            try:
                vid = int(raw_v) if raw_v else 0
            except ValueError:
                vid = 0
        out.append(
            HanwhaPartDetRow(
                partname=(d.get(col("PARTNAME")) or "").strip(),
                profilename=(d.get(col("PROFILENAME")) or "").strip(),
                partdesc=(d.get(col("PARTDESC")) or "").strip(),
                confidence_level=conf,
                used_machine_set=used,
                vendor_id=vid,
            )
        )
    return out


def part_det_rows_to_dataframe(rows: Sequence[HanwhaPartDetRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "PARTNAME",
                "PROFILENAME",
                "PARTDESC",
                "CONFIDENCE_LEVEL",
                "USED_MACHINE_SET",
                "VENDORID",
            ]
        )
    return pd.DataFrame(
        {
            "PARTNAME": [r.partname for r in rows],
            "PROFILENAME": [r.profilename for r in rows],
            "PARTDESC": [r.partdesc for r in rows],
            "CONFIDENCE_LEVEL": [r.confidence_level for r in rows],
            "USED_MACHINE_SET": [r.used_machine_set for r in rows],
            "VENDORID": [r.vendor_id for r in rows],
        }
    )


def load_part_det_from_mdb(mdb_path: str | Path) -> list[HanwhaPartDetRow]:
    """Export PART_Det from .mdb and parse into rows."""
    csv_text = export_table_csv(mdb_path, "PART_Det")
    return parse_part_det_csv(csv_text)

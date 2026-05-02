"""Tests for Hanwha UPD .mdb reading via mdbtools."""

from __future__ import annotations

from pathlib import Path

import pytest

from machine_library.hanwha_mdbtools import (
    HanwhaMdbToolsError,
    export_table_csv,
    list_mdb_tables,
    load_part_det_from_mdb,
    parse_part_det_csv,
    part_det_rows_to_dataframe,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_CSV = _FIXTURE_DIR / "hanwha_PART_Det_sample.csv"
# Workspace root when repo lives at …/cursor/boomer (sibling UPD.MDB).
_UPD_MDB = Path(__file__).resolve().parents[2] / "UPD.MDB"


def test_parse_part_det_fixture() -> None:
    text = _SAMPLE_CSV.read_text(encoding="utf-8")
    rows = parse_part_det_csv(text)
    assert len(rows) == 2
    assert rows[0].partname == "_NewC0201"
    assert rows[0].profilename == "_NewC0201"
    assert rows[1].partname == "_NewR0201"


def test_part_det_rows_to_dataframe() -> None:
    text = _SAMPLE_CSV.read_text(encoding="utf-8")
    df = part_det_rows_to_dataframe(parse_part_det_csv(text))
    assert list(df.columns) == [
        "PARTNAME",
        "PROFILENAME",
        "PARTDESC",
        "CONFIDENCE_LEVEL",
        "USED_MACHINE_SET",
        "VENDORID",
    ]
    assert len(df) == 2


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not present")
def test_list_tables_on_sample_upd_mdb() -> None:
    names = list_mdb_tables(_UPD_MDB)
    assert "PART_Det" in names
    assert "PARTGROUP_Map" in names
    assert "FEEDERTYPE_Map" in names


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not present")
def test_load_part_det_from_sample_upd_mdb() -> None:
    rows = load_part_det_from_mdb(_UPD_MDB)
    assert len(rows) >= 2
    names = {r.partname for r in rows}
    assert "_NewC0201" in names
    assert "_NewR0201" in names


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not present")
def test_export_table_rejects_bad_name() -> None:
    with pytest.raises(HanwhaMdbToolsError, match="unsafe"):
        export_table_csv(_UPD_MDB, "PART_Det;DROP")

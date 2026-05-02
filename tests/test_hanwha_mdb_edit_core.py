"""Qt-free tests for hanwha_mdb_edit core."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hanwha_mdb_edit.core.errors import HanwhaValidationError
from hanwha_mdb_edit.core.part_det_model import EditablePartDetRow, MAX_PARTNAME_LEN
from hanwha_mdb_edit.core.save import SaveResult, format_part_det_csv, save_enriched_library, save_part_det

_CURSOR_ROOT = Path(__file__).resolve().parents[2]
_UPD_MDB = _CURSOR_ROOT / "UPD.MDB"


def test_editable_row_validates_partname_length() -> None:
    long_name = "x" * (MAX_PARTNAME_LEN + 1)
    row = EditablePartDetRow(long_name, "p", "d", 0, 0)
    with pytest.raises(HanwhaValidationError):
        row.validate()


def test_format_part_det_csv_headers() -> None:
    df = pd.DataFrame(
        {
            "PARTNAME": ["A"],
            "PROFILENAME": ["A"],
            "PARTDESC": [" "],
            "CONFIDENCE_LEVEL": [0],
            "USED_MACHINE_SET": [0],
            "VENDORID": [0],
        }
    )
    text = format_part_det_csv(df)
    lines = text.strip().splitlines()
    assert lines[0].startswith("PARTNAME,")
    assert "A" in lines[1]


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not next to boomer/")
def test_save_creates_backup_and_csv_sidecar(tmp_path: Path) -> None:
    import shutil

    from hanwha_mdb_edit.core.part_det_repository import load_part_det_dataframe

    mdb_copy = tmp_path / "lib.mdb"
    shutil.copy2(_UPD_MDB, mdb_copy)
    df = load_part_det_dataframe(mdb_copy)
    result = save_part_det(mdb_copy, df)
    assert isinstance(result, SaveResult)
    assert result.mode == "csv_sidecar"
    assert result.backup_path.is_file()
    assert result.exported_paths
    assert result.exported_paths[0].name.endswith("_PART_Det_saved.csv")
    assert result.exported_paths[0].read_text(encoding="utf-8").startswith("PARTNAME,")


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not next to boomer/")
def test_load_wide_has_at_least_enriched_columns() -> None:
    from hanwha_mdb_edit.core.part_enriched import load_enriched_parts_dataframe, load_wide_editor_dataframe

    wide = load_wide_editor_dataframe(_UPD_MDB)
    base = load_enriched_parts_dataframe(_UPD_MDB)
    assert len(wide.columns) >= len(base.columns)
    for c in base.columns:
        assert c in wide.columns


@pytest.mark.skipif(not _UPD_MDB.is_file(), reason="UPD.MDB not next to boomer/")
def test_save_enriched_writes_four_sidecars(tmp_path: Path) -> None:
    import shutil

    from hanwha_mdb_edit.core.part_enriched import load_enriched_parts_dataframe

    mdb_copy = tmp_path / "lib.mdb"
    shutil.copy2(_UPD_MDB, mdb_copy)
    df = load_enriched_parts_dataframe(mdb_copy)
    result = save_enriched_library(mdb_copy, df)
    assert len(result.exported_paths) == 4
    names = {p.name for p in result.exported_paths}
    assert any("PART_Det_saved" in n for n in names)
    assert any("PROFILE_Det_saved" in n for n in names)


def test_bulk_paren_updates_rows() -> None:
    from hanwha_mdb_edit.core.part_bulk import bulk_update_paren_profile

    df = pd.DataFrame(
        {
            "PARTNAME": ["a", "b"],
            "PROFILENAME": ["p", "p"],
            "PARENTPROFILE": ["old", "old"],
        }
    )
    out = bulk_update_paren_profile(df, "old", "new")
    assert list(out["PARENTPROFILE"]) == ["new", "new"]

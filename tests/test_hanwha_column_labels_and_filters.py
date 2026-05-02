"""Unit tests for T-OLP-style column labels and standard-library row heuristics."""

from __future__ import annotations

import pytest

from hanwha_mdb_edit.core.column_labels import build_column_header_metadata, format_column_for_checklist, label_and_tooltip_for_column
from hanwha_mdb_edit.core.part_filters import is_standard_library_s_row


def test_standard_s_heuristic_double_underscore() -> None:
    assert is_standard_library_s_row("__BGA_1x1", "")
    assert not is_standard_library_s_row("C0402_1", "Basic")


def test_standard_s_heuristic_stdver_in_desc() -> None:
    assert is_standard_library_s_row("ANY", "[STDVER.18]")
    assert is_standard_library_s_row("x", "[stdver.10]")


def test_part_name_core_label() -> None:
    label, tip = label_and_tooltip_for_column("PARTNAME")
    assert "Part Name" == label
    assert "PARTNAME" in tip


def test_merged_column_label() -> None:
    label, tip = label_and_tooltip_for_column("FOO_Det__BAR_THRESHOLD")
    assert "THRESHOLD" in tip.upper() or "threshold" in tip.lower()
    assert "FOO_Det__BAR_THRESHOLD" in tip


def test_build_metadata_same_keys() -> None:
    disp, tips = build_column_header_metadata(["PARTNAME", "PROFILENAME"])
    assert disp["PARTNAME"] != "PARTNAME" or "Part" in disp["PARTNAME"]
    assert len(tips) == 2


def test_format_column_for_checklist() -> None:
    s = format_column_for_checklist("PARTNAME")
    assert "PARTNAME" in s
    assert "—" in s


def test_apply_row_patch_roundtrip() -> None:
    pytest.importorskip("PySide6")
    import pandas as pd

    from qt_models import PandasTableModel

    df = pd.DataFrame({"A": [1], "B": ["x"]})
    m = PandasTableModel(df, editable=True)
    assert m.apply_row_patch(0, {"A": "2", "B": "y"})
    assert m.get_dataframe().iloc[0]["A"] == 2
    assert m.get_dataframe().iloc[0]["B"] == "y"

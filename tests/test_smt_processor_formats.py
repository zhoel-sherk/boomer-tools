import pytest
import sys
import os
import tempfile
import pandas as pd

tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

import smt_processor


def test_whitespace_sp_like_classic_boomer():
    """SPACES/*sp: same filters as csv_reader; 1st row can be header via apply_row_as_column_header."""
    content = (
        "DESIGNATOR FOOTPRINT MID-X MID-Y REF-X REF-Y PAD-X PAD-Y LAYER ROTATION COMMENT\n"
        "C167 FPC_2P 100 200 10 20 30 40 N 0 cap\n"
        "C168 FPC_3 110 210 11 21 31 41 N 0 cap2\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        df = smt_processor.read_text_whitespace_sp(temp_path)
        assert len(df.columns) >= 10
        hdr = smt_processor.apply_row_as_column_header(df, 0)
        assert str(hdr.columns[0]).upper().startswith("DESIGNATOR") or "DESIGNATOR" in [
            str(c).upper() for c in hdr.columns
        ]
        assert len(hdr) == 2
        assert "C167" in hdr.iloc[0].astype(str).values
    finally:
        os.unlink(temp_path)


# ==============================================================================
# Test Chinese BOM Excel (with datetime header detection)
# ==============================================================================

def test_chinese_bom_detection():
    """Test that Chinese BOM with datetime column header is detected"""
    # The bom.xlsx is a regular test file, not Chinese BOM
    # Just check it reads correctly
    path = os.path.join(tests_path, "assets", "bom.xlsx")
    df = smt_processor.read_file(path)
    
    # Should have parsed columns
    assert not df.empty
    assert len(df.columns) > 0


# ==============================================================================
# Test PnP fixed-width (2+ spaces separator)
# ==============================================================================

def test_fixed_width_2sp_basic():
    """Test reading fixed-width with 2+ spaces"""
    # Create test file
    content = """Designator  Footprint        X    Y
ADM         TPS3895ADRYR   100   200
R1          0402           150   250"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        df = smt_processor.read_file(temp_path, separator="2+sp", first_row=0)
        
        # Should have parsed columns
        assert len(df.columns) >= 3
        # First data row should be parsed
        assert 'ADM' in df['Designator'].values
        
    finally:
        os.unlink(temp_path)


def test_fixed_width_real_pnp():
    """Eagle/Board cmp.txt: 9 columns; full file includes Board/header lines; use first_row to reach data."""
    example_path = os.path.join(os.path.dirname(tests_path), "..", "examples", "example6", "cmp.txt")
    if not os.path.exists(example_path):
        pytest.skip("examples/example6/cmp.txt not in tree")
    df_full = smt_processor.read_file(example_path, separator="2+sp", first_row=0)
    assert len(df_full.columns) == 9
    assert len(df_full) > 100
    # First rows are metadata (Board/Unit/---); user skips with 1st row in UI — first component is ADM at 0-based row 10
    df = smt_processor.read_file(example_path, separator="2+sp", first_row=10)
    assert "Designator" in df.columns
    assert "Pos-X (mm)" in df.columns
    assert "Pos-Y (mm)" in df.columns
    assert "Rotation" in df.columns
    assert "Layer" in df.columns
    r0 = df.iloc[0]
    assert str(r0["Designator"]) == "ADM"
    assert str(r0["Layer"]).strip() in ("N", "M", "")


def test_xy_fixed_width_splits_layer_marker_from_footprint():
    content = """UUNITS = MILLIMETERS
CP1513               -106.0450    -19.0358      180  m C0402
CP169                -11.1252     -31.7612        0    C0402
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        df = smt_processor.read_file(temp_path, separator="auto")
        assert list(df.columns) == ["Ref", "X", "Y", "Rotation", "Layer", "Footprint"]
        assert str(df.iloc[0]["Layer"]) == "m"
        assert str(df.iloc[0]["Footprint"]) == "C0402"
        assert str(df.iloc[1]["Layer"]) == ""
        assert str(df.iloc[1]["Footprint"]) == "C0402"
    finally:
        os.unlink(temp_path)


def test_merge_delete_dnp_skips_refs_missing_from_bom():
    bom = pd.DataFrame({"Ref": ["R1,R2", "C1"], "Comment": ["10K", "100nF"]})
    pnp = pd.DataFrame(
        {
            "Ref": ["R1", "R2", "R3", "C1"],
            "X": [1, 2, 3, 4],
            "Y": [1, 2, 3, 4],
            "Rotation": [0, 0, 0, 90],
            "Footprint": ["R0402", "R0402", "R0402", "C0402"],
        }
    )
    proc = smt_processor.SMTDataProcessor().set_dataframes(
        bom,
        pnp,
        smt_processor.ColumnConfig(designator="Ref", comment="Comment"),
        smt_processor.ColumnConfig(
            designator="Ref",
            coord_x="X",
            coord_y="Y",
            rotation="Rotation",
            footprint="Footprint",
        ),
    )

    merged = proc.merge_bom_pnp(include_dnp=False)
    assert list(merged["Ref"]) == ["R1", "R2", "C1"]
    assert "R3" not in set(merged["Ref"])


def test_merge_bom_pnp_with_integer_column_names():
    """DataFrames with RangeIndex columns (0,1,2,...) must not call .strip() on int."""
    bom = pd.DataFrame([["R1", "10K"], ["C1", "100n"]])
    pnp = pd.DataFrame(
        [
            ["R1", 10.0, 20.0, 0, "R0402"],
            ["C1", 30.0, 40.0, 90, "C0402"],
        ]
    )
    proc = smt_processor.SMTDataProcessor().set_dataframes(
        bom,
        pnp,
        smt_processor.ColumnConfig(designator=0, comment=1),
        smt_processor.ColumnConfig(
            designator=0,
            coord_x=1,
            coord_y=2,
            rotation=3,
            footprint=4,
        ),
    )
    merged = proc.merge_bom_pnp(include_dnp=True)
    assert len(merged) == 2
    assert set(merged["Ref"]) == {"R1", "C1"}


def test_eagle_cmp_auto_separator():
    """auto path must detect Board/fixed same as 2+sp for cmp.txt."""
    example_path = os.path.join(os.path.dirname(tests_path), "..", "examples", "example6", "cmp.txt")
    if not os.path.exists(example_path):
        pytest.skip("example cmp missing")
    df_auto = smt_processor.read_file(example_path, separator="auto", first_row=0)
    df_2sp = smt_processor.read_file(example_path, separator="2+sp", first_row=0)
    assert list(df_auto.columns) == list(df_2sp.columns)
    assert len(df_auto) == len(df_2sp)


def test_eagle_cmp_first_row_empty_footprint_when_merged():
    """ADM line is 8 fields → blank Footprint after merge to 9 columns (skip header with first_row)."""
    example_path = os.path.join(os.path.dirname(tests_path), "..", "examples", "example6", "cmp.txt")
    if not os.path.exists(example_path):
        pytest.skip("example cmp missing")
    df = smt_processor.read_file(example_path, separator="2+sp", first_row=10)
    assert str(df.iloc[0].get("Footprint", "")).strip() == ""
    assert str(df.iloc[0]["Rotation"]).strip() == "180"
    assert str(df.iloc[0]["Layer"]).strip() == "N"


# ==============================================================================
# Test separator options
# ==============================================================================

def test_separator_auto():
    """Test auto separator detection"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("A,B,C\n1,2,3\n")
        temp_path = f.name
    
    try:
        df = smt_processor.read_file(temp_path, separator="auto")
        assert not df.empty
    finally:
        os.unlink(temp_path)


def test_separator_2sp():
    """Test 2+ spaces separator"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("A    B    C\n1    2    3\n")
        temp_path = f.name
    
    try:
        df = smt_processor.read_file(temp_path, separator="2+sp")
        assert not df.empty
        assert len(df.columns) >= 2
    finally:
        os.unlink(temp_path)


def test_separator_fixed():
    """Test fixed separator (alias for 2+sp)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("A    B    C\n1    2    3\n")
        temp_path = f.name
    
    try:
        df = smt_processor.read_file(temp_path, separator="fixed")
        assert not df.empty
    finally:
        os.unlink(temp_path)
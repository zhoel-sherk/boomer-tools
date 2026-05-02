import pytest
import sys
import os

# adding src path to search list
tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

# tested module
import xlsx_reader

# -----------------------------------------------------------------------------

def test_no_file():
    with pytest.raises(AssertionError):
        xlsx_reader.read_xlsx_sheet(None)

def test_bom():
    grid = xlsx_reader.read_xlsx_sheet(f"{tests_path}/assets/bom.xlsx")
    assert grid.nrows == 22  # rows with ≥4 populated leading cells kept (see __check_row_valid)
    assert grid.ncols == 8
    assert grid.rows_raw()[-1][3] == "MURA-BLM18PG_KG-CHIP-2_V1"
    # check if empty cell was appended
    assert grid.rows_raw()[1][7] == ""

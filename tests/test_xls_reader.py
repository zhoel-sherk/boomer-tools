import pytest
import sys
import os

# adding src path to search list
tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

# tested module
import xls_reader

# -----------------------------------------------------------------------------

def test_no_file():
    with pytest.raises(AssertionError):
        xls_reader.read_xls_sheet(None)

def test_bom():
    grid = xls_reader.read_xls_sheet(f"{tests_path}/assets/bom.xls")
    assert grid.nrows == 54
    assert grid.ncols == 10
    assert grid.rows_raw()[4][9] == "50"
    assert grid.rows_raw()[-1][2] == "HC-49U"
    # check if empty cells were appended
    assert grid.rows_raw()[5][9] == ""

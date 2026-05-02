import pytest
import sys
import os

# adding src path to search list
tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

# tested module
import csv_reader

# -----------------------------------------------------------------------------

def test_no_file():
    with pytest.raises(AssertionError):
        csv_reader.read_csv(None, " ")

def test_no_separator():
    with pytest.raises(AssertionError):
        csv_reader.read_csv(".", None)

def test_csv_comma():
    # using a full asset path makes possible to run the tests from the VSCode
    grid = csv_reader.read_csv(f"{tests_path}/assets/comma.csv", ",")
    # Fixture is short Altium-style export: preamble lines lack enough columns and are skipped.
    assert grid.nrows == 3  # header + 2 component rows
    assert grid.ncols == 13
    assert grid.rows_raw()[0][0] == "Designator"
    assert grid.rows_raw()[0][-1] == "Pad-Y(mm)"
    assert grid.rows_raw()[1][0] == "R52"

def test_csv_spaces():
    grid = csv_reader.read_csv(f"{tests_path}/assets/spaces.csv", "*sp")
    assert grid.nrows == 8  # variant line + header + 6 fiducials (see tests/assets/spaces.csv)
    assert grid.ncols == 8
    assert grid.rows_raw()[2][0] == "Fid6"

def test_csv_tabs():
    grid = csv_reader.read_csv(f"{tests_path}/assets/tabs.csv", "\t")
    assert grid.nrows == 21-2 # skip empty and lines that begins with '___'
    assert grid.ncols == 10
    assert grid.rows_raw()[-2][2] == "SOT23_S4C"

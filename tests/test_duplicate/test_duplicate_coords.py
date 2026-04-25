import os
import sys

tests_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

import csv_reader
import cross_check
import text_grid


def create_configured_grid(csv_path: str) -> text_grid.ConfiguredTextGrid:
    """Create ConfiguredTextGrid from CSV file"""
    tg = csv_reader.read_csv(csv_path, ",")
    cfg = text_grid.ConfiguredTextGrid()
    cfg.text_grid = tg
    cfg.has_column_headers = True
    cfg.first_row = 0
    cfg.last_row = -1  # -1 means "read all rows"
    cfg.designator_col = "Designator"
    cfg.comment_col = "Comment"
    return cfg


def create_pnp_grid(csv_path: str) -> text_grid.ConfiguredTextGrid:
    """Create PnP ConfiguredTextGrid from CSV file"""
    tg = csv_reader.read_csv(csv_path, ",")
    cfg = text_grid.ConfiguredTextGrid()
    cfg.text_grid = tg
    cfg.has_column_headers = True
    cfg.first_row = 0
    cfg.last_row = -1  # -1 means "read all rows"
    cfg.designator_col = "Designator"
    cfg.comment_col = "Comment"
    cfg.coord_x_col = "Mid-X"
    cfg.coord_y_col = "Mid-Y"
    cfg.layer_col = "Layer"
    cfg.footprint_col = "Footprint"
    return cfg


def _asset(name: str) -> str:
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), name)


def test_duplicate_coords_absent_for_normal_pnp():
    bom = create_configured_grid(_asset("test_bom.csv"))
    pnp = create_pnp_grid(_asset("test_pnp1.csv"))

    result = cross_check.compare(bom, pnp, min_distance=0.1, coord_unit_mils=False)

    assert result.parts_duplicate_coords == []


def test_duplicate_coords_detect_exact_xy_match():
    bom = create_configured_grid(_asset("test_bom.csv"))
    pnp = create_pnp_grid(_asset("test_pnp2.csv"))

    result = cross_check.compare(bom, pnp, min_distance=0.1, coord_unit_mils=False)

    assert len(result.parts_duplicate_coords) == 1
    dup = result.parts_duplicate_coords[0]
    assert {dup[0], dup[1]} == {"C1", "C2"}
    assert dup[2:] == (50.0, 60.0)
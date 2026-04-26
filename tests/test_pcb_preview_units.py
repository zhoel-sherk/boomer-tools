import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pcb_preview_bridge import infer_declared_coord_unit_mm, placements_from_pnp_dataframe


def test_infer_uunits_millimeters():
    df = pd.DataFrame(
        [
            ["UUNITS = MILLIMETERS", None, None, None, None],
            ["CD91", -29.464, 10.3012, 90, "SMC0201"],
        ]
    )
    assert infer_declared_coord_unit_mm(df) is True


def test_placements_override_mils_ui_when_file_declares_mm():
    df = pd.DataFrame(
        [
            ["UUNITS = MILLIMETERS", "", "", "", ""],
            ["CD91", -29.464, 10.3012, 90, "SMC0201"],
        ],
        columns=["Ref", "X", "Y", "Rotation", "Footprint"],
    )
    pl, warns = placements_from_pnp_dataframe(
        df,
        designator_col="Ref",
        x_col="X",
        y_col="Y",
        rot_col="Rotation",
        footprint_col="Footprint",
        coord_unit_mm=False,
    )
    assert any("file declares" in w.lower() for w in warns)
    assert len(pl) == 1
    assert abs(pl[0].x_mm - (-29.464)) < 1e-6

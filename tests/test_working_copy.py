from __future__ import annotations

import os
import sys

import pandas as pd

tests_path = os.path.dirname(os.path.realpath(__file__))
_boomer_root = os.path.dirname(tests_path)
sys.path.append(os.path.join(_boomer_root, "src"))

import working_copy


def test_working_copy_snapshot_roundtrip(tmp_path):
    src = tmp_path / "bom.xlsx"
    src.write_text("source", encoding="utf-8")
    autosave = tmp_path / "autosave"
    df = pd.DataFrame({"Comment": ["100R", "10nF"], "Extra": ["A", "B"]})

    meta_path = working_copy.save_snapshot(df, src, "bom", autosave, dirty=True)
    assert meta_path.exists()

    snap = working_copy.find_snapshot(src, "bom", autosave)
    assert snap is not None
    assert snap.meta["kind"] == "bom"
    assert snap.meta["dirty"] is True
    pd.testing.assert_frame_equal(snap.dataframe, df)


def test_working_copy_exact_snapshot_can_be_marked_clean(tmp_path):
    src = tmp_path / "pnp.csv"
    src.write_text("source", encoding="utf-8")
    autosave = tmp_path / "autosave"
    df = pd.DataFrame({"Designator": ["R1"]})

    working_copy.save_snapshot(df, src, "pnp", autosave, dirty=False)
    snap = working_copy.find_snapshot(src, "pnp", autosave)
    assert snap is not None
    assert snap.meta["dirty"] is False

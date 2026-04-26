import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pcb_preview.gerber_io import peek_rs274x_linear_unit


def test_allegro_pastemask_is_moin():
    p = os.path.join(
        os.path.dirname(__file__), "..", "examples", "example9", "gerber", "PASTEMASKTOP.art"
    )
    assert os.path.isfile(p), f"missing fixture: {p}"
    assert peek_rs274x_linear_unit(p) == "inch"


def test_minimal_momm(tmp_path):
    p = tmp_path / "m.gbr"
    p.write_text("%MOMM*%\n", encoding="ascii")
    assert peek_rs274x_linear_unit(str(p)) == "mm"

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pcb_preview.gerber_io import load_gerber_svg


def test_minimal_gerber_roundtrip(tmp_path) -> None:
    g = """G04 Test*
%FSLAX26Y26*%
%MOMM*%
%ADD10C,0.5*%
D10*
X0Y0D02*
X1000000Y0D01*
X1000000Y1000000D01*
X0Y1000000D01*
X0Y0D01*
M02*
"""
    p = tmp_path / "t.gbr"
    p.write_text(g, encoding="ascii")
    payload = load_gerber_svg(str(p))
    assert not payload.errors, payload.errors
    assert "svg" in payload.svg.lower() or payload.svg.startswith("<?xml")
    assert payload.bbox_mm.max_x > payload.bbox_mm.min_x

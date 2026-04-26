"""
Gerber → SVG via **gerbonara** (Apache-2.0 on PyPI): parse + vectorize without KiCad GerbView.

KiCad GerbView is GPL; embedding it would be a separate optional process. Raster in the GUI uses
QSvgRenderer on the returned SVG (see pcb_preview_tab).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pcb_preview.types import BBoxMM, GerberSvgPayload

_RS274_MOIN = re.compile(br"%?MOIN\*?%?", re.IGNORECASE)
_RS274_MOMM = re.compile(br"%?MOMM\*?%?", re.IGNORECASE)


def peek_rs274x_linear_unit(path: str, max_bytes: int = 262144) -> Literal["inch", "mm", "unknown"]:
    """
    Best-effort scan of RS-274X header for %MOIN*% (inch) vs %MOMM*% (mm).

    Many tools (e.g. Cadence Allegro .art) emit MOIN; parsers usually convert to mm for output,
    but this hint is useful for UI defaults and logging.
    """
    p = Path(path)
    if not p.is_file():
        return "unknown"
    try:
        head = p.read_bytes()[:max_bytes]
    except OSError:
        return "unknown"
    if _RS274_MOMM.search(head):
        return "mm"
    if _RS274_MOIN.search(head):
        return "inch"
    return "unknown"


def scale_bbox_mm(bb: BBoxMM, factor: float) -> BBoxMM:
    if factor == 1.0:
        return bb
    return BBoxMM(bb.min_x * factor, bb.min_y * factor, bb.max_x * factor, bb.max_y * factor)


def load_gerber_svg(path: str) -> GerberSvgPayload:
    """
    Read a single Gerber file and return SVG plus axis-aligned bounds in mm.

    On import/parse failure, returns an empty payload with errors set.
    """
    errors: list[str] = []
    p = Path(path)
    if not p.is_file():
        return GerberSvgPayload(
            source_path=path,
            svg="",
            bbox_mm=BBoxMM(0.0, 0.0, 0.0, 0.0),
            errors=(f"Not a file: {path}",),
        )
    try:
        from gerbonara import GerberFile  # type: ignore[import-untyped]
    except ImportError as e:
        return GerberSvgPayload(
            source_path=path,
            svg="",
            bbox_mm=BBoxMM(0.0, 0.0, 0.0, 0.0),
            errors=(f"gerbonara not installed: {e}",),
        )
    try:
        gbr = GerberFile.open(str(p))
    except Exception as e:
        return GerberSvgPayload(
            source_path=path,
            svg="",
            bbox_mm=BBoxMM(0.0, 0.0, 0.0, 0.0),
            errors=(f"Gerber open failed: {e}",),
        )
    try:
        bb = gbr.bounding_box()
        (x0, y0), (x1, y1) = bb
        bbox = BBoxMM(float(x0), float(y0), float(x1), float(y1))
        svg_tag = gbr.to_svg()
        svg = str(svg_tag)
    except Exception as e:
        errors.append(f"Gerber SVG/bbox failed: {e}")
        return GerberSvgPayload(
            source_path=path,
            svg="",
            bbox_mm=BBoxMM(0.0, 0.0, 0.0, 0.0),
            errors=tuple(errors),
        )
    return GerberSvgPayload(source_path=path, svg=svg, bbox_mm=bbox, errors=tuple(errors))

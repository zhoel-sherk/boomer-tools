"""Qt/pandas-free data types for PCB preview (Gerber + PnP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

BoardSide = Literal["top", "bottom", "unknown"]
LengthUnit = Literal["mm", "mil", "inch"]


@dataclass(frozen=True)
class PlacementRecord:
    """One pick-and-place row in millimeters (core canonical unit)."""

    ref: str
    x_mm: float
    y_mm: float
    rotation_deg: float
    side: BoardSide = "unknown"
    footprint_name: str = ""
    value: str = ""
    comment: str = ""
    row_index: int = -1


@dataclass(frozen=True)
class BBoxMM:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass(frozen=True)
class GerberSvgPayload:
    """Gerber layer converted to SVG (gerbonara); bounds in mm."""

    source_path: str
    svg: str
    bbox_mm: BBoxMM
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrokeLineMM:
    x1: float
    y1: float
    x2: float
    y2: float
    width_mm: float = 0.12


@dataclass(frozen=True)
class StrokeCircleMM:
    cx: float
    cy: float
    radius_mm: float
    width_mm: float = 0.12


@dataclass(frozen=True)
class PadRectMM:
    cx: float
    cy: float
    width_mm: float
    height_mm: float
    rotation_deg: float
    number: str = ""


@dataclass(frozen=True)
class FootprintOutlineMM:
    """Footprint geometry in local mm (origin at footprint 0,0); Tier A or B."""

    lines: tuple[StrokeLineMM, ...] = ()
    circles: tuple[StrokeCircleMM, ...] = ()
    pads: tuple[PadRectMM, ...] = ()
    bbox: BBoxMM = field(default_factory=lambda: BBoxMM(0.0, 0.0, 0.0, 0.0))
    source: Literal["heuristic", "kicad_mod", "none"] = "none"


def union_bbox(boxes: Sequence[BBoxMM]) -> BBoxMM:
    xs0 = [b.min_x for b in boxes]
    ys0 = [b.min_y for b in boxes]
    xs1 = [b.max_x for b in boxes]
    ys1 = [b.max_y for b in boxes]
    if not boxes:
        return BBoxMM(0.0, 0.0, 0.0, 0.0)
    return BBoxMM(min(xs0), min(ys0), max(xs1), max(ys1))

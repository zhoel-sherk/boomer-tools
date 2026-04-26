"""Tier B: parse KiCad .kicad_mod via kiutils → outline primitives (mm)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pcb_preview.types import (
    BBoxMM,
    FootprintOutlineMM,
    PadRectMM,
    StrokeCircleMM,
    StrokeLineMM,
    union_bbox,
)


def _stroke_width(obj: Any) -> float:
    st = getattr(obj, "stroke", None)
    if st is not None and getattr(st, "width", None) is not None:
        return float(st.width)
    w = getattr(obj, "width", None)
    return float(w) if w is not None else 0.12


def _arc_polyline(sx: float, sy: float, mx: float, my: float, ex: float, ey: float, segments: int = 24) -> list[tuple[float, float]]:
    """Approximate KiCad fp_arc (start, mid, end) as polyline points including start..end."""
    # Circle through three points (2D)
    ax, ay = sx, sy
    bx, by = mx, my
    cx, cy = ex, ey
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [(sx, sy), (ex, ey)]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    def ang(px: float, py: float) -> float:
        return math.atan2(py - uy, px - ux)
    a0 = ang(sx, sy)
    a1 = ang(mx, my)
    a2 = ang(ex, ey)
    # choose direction so mid lies between start and end along arc
    def norm(a: float) -> float:
        while a <= -math.pi:
            a += 2 * math.pi
        while a > math.pi:
            a -= 2 * math.pi
        return a
    da1 = norm(a1 - a0)
    da2 = norm(a2 - a0)
    if da1 * da2 < 0 or abs(da1) < 1e-9:
        sweep = norm(a2 - a0)
    else:
        sweep = da2 if abs(da2) >= abs(da1) else norm(2 * math.pi - abs(da2)) * (1 if da2 > 0 else -1)
    r = math.hypot(sx - ux, sy - uy)
    pts: list[tuple[float, float]] = []
    for i in range(segments + 1):
        t = i / segments
        ang = a0 + sweep * t
        pts.append((ux + r * math.cos(ang), uy + r * math.sin(ang)))
    return pts


def outline_from_kicad_mod(path: str) -> tuple[FootprintOutlineMM, tuple[str, ...]]:
    """Load .kicad_mod and convert supported graphics + SMD/rect pads."""
    errors: list[str] = []
    p = Path(path)
    if not p.is_file():
        return FootprintOutlineMM(source="none"), (f"Not a file: {path}",)
    try:
        from kiutils.footprint import Footprint  # type: ignore[import-untyped]
    except ImportError as e:
        return FootprintOutlineMM(source="none"), (f"kiutils not installed: {e}",)
    try:
        fp = Footprint.from_file(str(p))
    except Exception as e:
        return FootprintOutlineMM(source="none"), (f"Footprint parse failed: {e}",)

    lines: list[StrokeLineMM] = []
    circles: list[StrokeCircleMM] = []
    pads: list[PadRectMM] = []
    bbs: list[BBoxMM] = []

    try:
        from kiutils.items.fpitems import FpArc, FpCircle, FpLine, FpPoly, FpRect  # type: ignore[import-untyped]
    except ImportError as e:
        return FootprintOutlineMM(source="none"), (f"kiutils fpitems: {e}",)

    for item in fp.graphicItems:
        lw = _stroke_width(item)
        if isinstance(item, FpLine):
            sx, sy = item.start.X, item.start.Y
            ex, ey = item.end.X, item.end.Y
            lines.append(StrokeLineMM(sx, sy, ex, ey, lw))
            bbs.append(BBoxMM(min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)))
        elif isinstance(item, FpRect):
            sx, sy = item.start.X, item.start.Y
            ex, ey = item.end.X, item.end.Y
            x0, x1 = min(sx, ex), max(sx, ex)
            y0, y1 = min(sy, ey), max(sy, ey)
            lines.extend(
                (
                    StrokeLineMM(x0, y0, x1, y0, lw),
                    StrokeLineMM(x1, y0, x1, y1, lw),
                    StrokeLineMM(x1, y1, x0, y1, lw),
                    StrokeLineMM(x0, y1, x0, y0, lw),
                )
            )
            bbs.append(BBoxMM(x0, y0, x1, y1))
        elif isinstance(item, FpCircle):
            cx, cy = item.center.X, item.center.Y
            ex, ey = item.end.X, item.end.Y
            r = math.hypot(ex - cx, ey - cy)
            circles.append(StrokeCircleMM(cx, cy, r, lw))
            bbs.append(BBoxMM(cx - r, cy - r, cx + r, cy + r))
        elif isinstance(item, FpArc):
            pts = _arc_polyline(item.start.X, item.start.Y, item.mid.X, item.mid.Y, item.end.X, item.end.Y)
            for i in range(len(pts) - 1):
                ax, ay = pts[i]
                bx, by = pts[i + 1]
                lines.append(StrokeLineMM(ax, ay, bx, by, lw))
                bbs.append(BBoxMM(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))
        elif isinstance(item, FpPoly):
            pts = [(pt.X, pt.Y) for pt in getattr(item, "coordinates", []) or []]
            for i in range(len(pts) - 1):
                ax, ay = pts[i]
                bx, by = pts[i + 1]
                lines.append(StrokeLineMM(ax, ay, bx, by, lw))
                bbs.append(BBoxMM(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))
            if pts:
                ax, ay = pts[-1]
                bx, by = pts[0]
                lines.append(StrokeLineMM(ax, ay, bx, by, lw))

    for pad in fp.pads:
        try:
            pos = pad.position
            px, py = float(pos.X), float(pos.Y)
            ang = getattr(pos, "angle", None)
            rot = float(ang) if ang is not None else 0.0
            sz = pad.size
            w, h = float(sz.X), float(sz.Y)
            if pad.type in ("smd", "thru_hole") and pad.shape in ("rect", "roundrect", "oval", "circle"):
                if pad.shape == "circle":
                    r = min(w, h) / 2.0
                    circles.append(StrokeCircleMM(px, py, r, 0.05))
                    bbs.append(BBoxMM(px - r, py - r, px + r, py + r))
                else:
                    pads.append(PadRectMM(px, py, w, h, rot, str(pad.number)))
                    bbs.append(BBoxMM(px - w / 2, py - h / 2, px + w / 2, py + h / 2))
        except Exception:
            continue

    bbox = union_bbox(bbs) if bbs else BBoxMM(0.0, 0.0, 0.0, 0.0)
    out = FootprintOutlineMM(
        lines=tuple(lines),
        circles=tuple(circles),
        pads=tuple(pads),
        bbox=bbox,
        source="kicad_mod",
    )
    if not lines and not circles and not pads:
        errors.append("No drawable geometry extracted (unsupported pad/graphics).")
    return out, tuple(errors)

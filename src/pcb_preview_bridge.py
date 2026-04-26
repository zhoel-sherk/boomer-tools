"""Thin bridge: pandas DataFrame → pcb_preview.PlacementRecord (depends on pandas only here)."""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from pcb_preview.types import BoardSide, PlacementRecord

_RE_UNITS_MM = re.compile(r"(?i)UUNITS\s*=\s*MILLIMETERS?")
_RE_UNITS_MIL = re.compile(r"(?i)UUNITS\s*=\s*MILS?")
_RE_UNITS_INCH = re.compile(r"(?i)UUNITS\s*=\s*INCH(?:ES)?")


def infer_declared_coord_unit_mm(df: pd.DataFrame, scan_rows: int = 40) -> Optional[bool]:
    """
    Scan early rows for Cadence/Allegro-style `UUNITS = MILLIMETERS` (or MILS/INCH).

    Returns True if mm, False if file declares mils/inch, None if not found.
    """
    n = min(scan_rows, len(df))
    for i in range(n):
        for c in df.columns:
            v = df.iloc[i][c]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            s = str(v).strip()
            if not s:
                continue
            if _RE_UNITS_MM.search(s):
                return True
            if _RE_UNITS_MIL.search(s) or _RE_UNITS_INCH.search(s):
                return False
    return None


def _col(df: pd.DataFrame, name: Optional[Any]) -> Optional[pd.Series]:
    if name is None or name == "?" or str(name).strip() == "":
        return None
    if name not in df.columns:
        return None
    return df[name]


def placements_from_pnp_dataframe(
    df: pd.DataFrame,
    *,
    designator_col: Any,
    x_col: Any,
    y_col: Any,
    rot_col: Any,
    layer_col: Optional[Any] = None,
    footprint_col: Optional[Any] = None,
    value_col: Optional[Any] = None,
    comment_col: Optional[Any] = None,
    coord_unit_mm: bool,
) -> tuple[list[PlacementRecord], list[str]]:
    """
    Build placement records. Coordinates are converted to mm (mils × 0.0254 if not mm).

    Returns (placements, warnings).
    """
    warnings: list[str] = []
    s_ref = _col(df, designator_col)
    s_x = _col(df, x_col)
    s_y = _col(df, y_col)
    if s_ref is None or s_x is None or s_y is None:
        return [], ["Missing REF/X/Y column mapping for PnP."]
    s_rot = _col(df, rot_col)
    s_layer = _col(df, layer_col) if layer_col else None
    s_fp = _col(df, footprint_col) if footprint_col else None
    s_val = _col(df, value_col) if value_col else None
    s_com = _col(df, comment_col) if comment_col else None

    declared = infer_declared_coord_unit_mm(df)
    effective_mm = coord_unit_mm
    if declared is not None and declared != coord_unit_mm:
        warnings.append(
            "PnP file declares "
            + ("millimeters" if declared else "mils/inches")
            + " but the PnP tab Units toggle is "
            + ("mm" if coord_unit_mm else "mils")
            + " — using the file declaration for PCB preview."
        )
        effective_mm = declared

    mil_to_mm = 0.0254
    out: list[PlacementRecord] = []
    for i in range(len(df)):
        ref = str(s_ref.iloc[i]).strip()
        if not ref or ref.lower() in ("nan", "none"):
            continue
        if ref.upper().startswith("UUNITS") or ref.startswith("#"):
            continue
        try:
            xv = float(s_x.iloc[i])
            yv = float(s_y.iloc[i])
        except (TypeError, ValueError):
            warnings.append(f"Row {i}: non-numeric X/Y for {ref}")
            continue
        if not effective_mm:
            xv *= mil_to_mm
            yv *= mil_to_mm
        rot = 0.0
        if s_rot is not None:
            try:
                rot = float(s_rot.iloc[i])
            except (TypeError, ValueError):
                rot = 0.0
        side: BoardSide = "unknown"
        if s_layer is not None:
            lv = str(s_layer.iloc[i]).upper()
            if "BOT" in lv or "BOTTOM" in lv or "B." in lv:
                side = "bottom"
            elif "TOP" in lv or "T." in lv or "F." in lv:
                side = "top"
        fp = ""
        if s_fp is not None:
            fp = str(s_fp.iloc[i]).strip()
            if fp.lower() == "nan":
                fp = ""
        val = ""
        if s_val is not None:
            val = str(s_val.iloc[i]).strip()
            if val.lower() == "nan":
                val = ""
        com = ""
        if s_com is not None:
            com = str(s_com.iloc[i]).strip()
            if com.lower() == "nan":
                com = ""
        out.append(
            PlacementRecord(
                ref=ref,
                x_mm=xv,
                y_mm=yv,
                rotation_deg=rot,
                side=side,
                footprint_name=fp,
                value=val,
                comment=com,
                row_index=i,
            )
        )
    return out, warnings

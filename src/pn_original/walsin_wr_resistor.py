"""
Walsin thick-film chip resistors, ``WR[package]X…`` (e.g. WR04X1001FTL).

Walsin WR / WF series part structure (simplified; size + X + value + F/J + tape code).
https://www.passivecomponent.com/ — Walsin Tech ordering guides.
"""

from __future__ import annotations

import re

from ._resistor_decode import decode_ohms_suffix

VENDOR_NAME = "Walsin_WR"
COMPONENT_TYPES = ["RES"]
PARSER_PRIORITY = 70

_RE_ZERO = re.compile(
    r"^WR(02|04|06|08|10|12|20|25)X(0+)(P)(AL|TL|PTL|FTL|JTL|L)$",
    re.I,
)
_RE_VAL = re.compile(
    r"^WR(02|04|06|08|10|12|20|25)[XW](10R[0-9]|[0-9]{1,4}R[0-9]{1,2}|[0-9]{1,4})(F|J)([A-Z]{2,5})$",
    re.I,
)
_SIZE = {
    "02": "0201",
    "04": "0402",
    "06": "0603",
    "08": "0805",
    "10": "0805",
    "12": "1210",
    "20": "2010",
    "25": "2512",
}
_TOL = {"F": "1%", "J": "5%"}


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "RES":
        return None
    pn2 = re.sub(r"\s+", "", pn).strip().upper()

    z = _RE_ZERO.match(pn2)
    if z:
        s = _SIZE.get(z.group(1))
        if not s:
            return None
        return f"{s}_0R_5%"

    m = _RE_VAL.match(pn2)
    if not m:
        return None
    size = _SIZE.get(m.group(1))
    if not size:
        return None
    val_raw, tol_c, _tape = m.group(2), m.group(3).upper(), m.group(4)
    tol = _TOL.get(tol_c, "")
    ohm = decode_ohms_suffix(val_raw)
    if ohm is None:
        return None
    parts = [size, ohm]
    if tol:
        parts.append(tol)
    return "_".join(parts)

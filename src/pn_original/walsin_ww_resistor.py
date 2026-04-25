"""
Walsin WW low-ohm / current-sense chip resistors (subset used in BOMs).
"""

from __future__ import annotations

import re

VENDOR_NAME = "Walsin_WW"
COMPONENT_TYPES = ["RES"]
PARSER_PRIORITY = 75

_SIZE = {
    "06": "0603",
    "08": "0805",
    "12": "1206",
    "20": "2010",
    "25": "2512",
}
_TOL = {"F": "1%", "J": "5%"}

_RE_WW = re.compile(r"^WW(06|08|12|20|25)R(R[0-9]{3})(F|J)([A-Z]+)$", re.I)


def _low_ohm(token: str) -> str | None:
    m = re.match(r"^R([0-9]{3})$", token.strip().upper())
    if not m:
        return None
    milli = int(m.group(1))
    if milli == 0:
        return "0R"
    return f"{milli / 1000.0:.3f}".rstrip("0").rstrip(".") + "R"


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "RES":
        return None
    pn0 = re.sub(r"\s+", "", str(pn).strip()).upper()
    m = _RE_WW.match(pn0)
    if not m:
        return None
    size_code, raw, tol_code, _tail = m.groups()
    size = _SIZE.get(size_code)
    ohm = _low_ohm(raw)
    tol = _TOL.get(tol_code.upper(), "")
    if not size or not ohm:
        return None
    return "_".join(p for p in (size, ohm, tol) if p)

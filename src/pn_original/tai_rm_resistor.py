"""
TA-I (Tai) thick-film chip resistors: ``RM…TN`` and ``RB…BTP`` (e.g. RM04JTN100, RB04BTP1000).

Part numbering reference (excerpt, ordering guide for RM series; verify against current datasheet):
https://www.tai-ohm.com/ — RM thick film, size 02/04/06/10/12 = 0201/0402/0603/0805/1210.
"""

from __future__ import annotations

import re

from ._resistor_decode import decode_ohms_suffix

VENDOR_NAME = "TAI_RM"
COMPONENT_TYPES = ["RES"]
PARSER_PRIORITY = 70

_RE_RM = re.compile(
    r"^RM(02|04|06|10|12|20|25)([FGJ])TN(.+)$",
    re.I,
)
# RB04BTP1000 — BTP sub-series, same ohm code as RM
_RE_RB = re.compile(
    r"^RB(02|04|06|10|12|20|25)BTP([0-9A-Z.]+?)(?:-.*)?$",
    re.I,
)
_SIZE = {
    "02": "0201",
    "04": "0402",
    "06": "0603",
    "10": "0805",
    "12": "1210",
    "20": "2010",
    "25": "2512",
}
_TOL = {"F": "1%", "G": "2%", "J": "5%"}


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "RES":
        return None
    pn2 = re.sub(r"\s+", "", pn).strip().upper()
    m = _RE_RM.match(pn2)
    if m:
        size, tol_ch, rest = m.group(1), m.group(2).upper(), m.group(3)
        rest = rest.strip()
        if rest.startswith("-"):
            rest = rest[1:]
        rest = rest.split("-", 1)[0].strip()
        if size not in _SIZE:
            return None
        tol = _TOL.get(tol_ch, "")
        ohm = decode_ohms_suffix(rest)
        if ohm is None:
            return None
        parts: list[str] = [_SIZE[size], ohm]
        if tol:
            parts.append(tol)
        return "_".join(parts)
    b = _RE_RB.match(pn2)
    if b:
        size, rest = b.group(1), b.group(2)
        rest = rest.split("-", 1)[0].strip()
        if size not in _SIZE:
            return None
        ohm = decode_ohms_suffix(rest)
        if ohm is None:
            return None
        return "_".join([_SIZE[size], ohm, "5%"])
    return None

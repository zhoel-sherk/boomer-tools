"""
Walsin multilayer ceramic (``0402N…`` / package-led MLCC) — subset used in real BOMs.

Walsin Tech MLCC: package + ``N`` + value/dielectric + rating + taping.
https://www.passivecomponent.com/
"""

from __future__ import annotations

import re

from ._cap_decode import pf_eia_3_to_str, walsin_vol_code_to_v

VENDOR_NAME = "Walsin_MLCC"
COMPONENT_TYPES = ["CAP"]
PARSER_PRIORITY = 65

_SIZE = {
    "0201": "0201",
    "0402": "0402",
    "0603": "0603",
    "0805": "0805",
    "1206": "1206",
    "1210": "1210",
}

# N100 J 500: 3-digit pF, tolerance J, 500 → 50V; N5R0 C 500: 5.0pF, C0G, 50V
_RE_N3 = re.compile(
    r"^(\d{4})N([0-9]{3})([FJ])([0-9]{2,3})([A-Z]{1,3})$",
    re.I,
)
_RE_N5R = re.compile(
    r"^(\d{4})N(5R[0-9])(.)([0-9]{2,3})([A-Z]{1,3})$",
    re.I,
)
# 0402B102K500CT — B line, 102 EIA, K tol, 500 = 50V
_RE_BCT = re.compile(
    r"^(\d{4})B(\d{3})([A-Z])(\d{3,4})CT$", re.I
)
# 0805X475M6R3CT — 475 EIA, 6R3 = 6.3V; leading M = 20% (optional)
_RE_X6R3 = re.compile(
    r"^(\d{4})X(\d{3,4})([A-Z]?)(\d)R(\d)CT$", re.I
)
# 1206X106K250CT — 106 value, K tol, 250 = 25V
_RE_XKV = re.compile(
    r"^(\d{4})X(\d{3,4})([A-Z])(\d{3,4})CT$", re.I
)
_TOL = {"F": "1%", "G": "2%", "J": "5%", "K": "10%", "M": "20%"}


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "CAP":
        return None
    pn0 = re.sub(r"\s*<[gG]>\s*$", "", str(pn).strip())
    pn2 = re.sub(r"\s+", "", pn0).strip().upper()

    mb = _RE_BCT.match(pn2)
    if mb:
        pz, c3, tch, vraw = mb.groups()
        if pz not in _SIZE:
            return None
        cap = pf_eia_3_to_str(c3) if len(c3) == 3 and c3.isdigit() else None
        if not cap:
            return None
        vol = walsin_vol_code_to_v(vraw)
        tol = _TOL.get(tch.upper(), "")
        parts2 = [_SIZE[pz], cap]
        if vol:
            parts2.append(vol)
        if tol:
            parts2.append(tol)
        return "_".join(parts2)

    m6r = _RE_X6R3.match(pn2)
    if m6r:
        pz, cblock, tch, _a, _b = m6r.groups()
        if pz not in _SIZE:
            return None
        c3 = cblock if len(cblock) == 3 else cblock[-3:]
        cap = (
            pf_eia_3_to_str(c3) if len(c3) == 3 and c3.isdigit() else None
        )
        if not cap:
            return None
        tol = _TOL.get(tch.upper(), "") if tch else ""
        return "_".join(p for p in (_SIZE[pz], cap, "6.3V", tol) if p)

    mxk = _RE_XKV.match(pn2)
    if mxk and not re.search(r"[0-9]R[0-9]CT$", pn2, re.I):
        pz, cblock, tch, vraw = mxk.groups()
        if pz not in _SIZE:
            return None
        c3 = cblock if len(cblock) == 3 and cblock.isdigit() else cblock[-3:]
        cap = pf_eia_3_to_str(c3) if len(c3) == 3 and c3.isdigit() else None
        if not cap:
            return None
        vol = walsin_vol_code_to_v(vraw)
        tol = _TOL.get(tch.upper(), "")
        parts3 = [_SIZE[pz], cap]
        if vol:
            parts3.append(vol)
        if tol:
            parts3.append(tol)
        return "_".join(parts3)

    m5 = _RE_N5R.match(pn2)
    if m5:
        psize, pval, diel, vcode, _pack = m5.groups()
        if psize not in _SIZE:
            return None
        mr = re.match(r"^5R([0-9])$", pval, re.I)
        if not mr:
            return None
        cap_s = f"5.{mr.group(1)}pF"
        vol = walsin_vol_code_to_v(vcode)
        d = "C0G" if diel.upper() == "C" else diel
        segs = [_SIZE[psize], cap_s, d]
        if vol:
            segs.append(vol)
        return "_".join(segs)

    m = _RE_N3.match(pn2)
    if not m:
        return None
    psize, cap3, _tol, vcode, _pack = m.groups()
    if psize not in _SIZE:
        return None
    cap = pf_eia_3_to_str(cap3)
    if not cap:
        return None
    vol = walsin_vol_code_to_v(vcode)
    parts = [_SIZE[psize], cap]
    if vol:
        parts.append(vol)
    return "_".join(parts)

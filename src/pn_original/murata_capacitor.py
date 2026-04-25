"""
Murata GRM MLCC: common BOM patterns (R71 Cxxx, 21x R6x+value, 1555 C0G 5R0).
"""

from __future__ import annotations

import re

from ._cap_decode import pf_eia_3_to_str

VENDOR_NAME = "Murata"
COMPONENT_TYPES = ["CAP"]
PARSER_PRIORITY = 100

# GRM155R71C104KA: cap code third digit (104) also encodes V in some columns — use 4th? keep R71C table
_R71_C_VOL = {
    "1": "10V", "2": "16V", "3": "25V", "4": "4V", "5": "6.3V", "6": "6.3V", "0": "16V",
}
_R6X_FOLLOW_VOL = {
    "A": "10V", "B": "6.3V", "C": "6.3V", "D": "6.3V", "E": "16V",
    "F": "25V", "G": "4V", "H": "50V", "J": "6.3V", "K": "25V",
    "L": "16V", "M": "4V", "N": "4V", "O": "16V", "P": "10V",
}
_TOL = {"J": "5%", "K": "10%", "M": "20%", "Z": "+80/-20%"}
_SIZE = {
    "155": "0402",
    "188": "0603",
    "21A": "0805",
    "21B": "0805",
    "216": "0805",
    "31M": "1206",
    "32E": "1210",
}
_VOLT = {
    "C": "6.3V",
    "D": "10V",
    "E": "16V",
    "F": "25V",
    "G": "35V",
    "H": "50V",
    "J": "100V",
}

_RE_R71C = re.compile(
    r"^GRM(155|188)R(71|72)C(10[0-9]|[0-1][0-9]{2})([A-Z0-9]+)$", re.I
)
_RE_R7V = re.compile(
    r"^GRM(155|188|21A|21B|216|31M|32E)R(71|72)([CDEFGHJ])([0-9]{3})(J|K|M|Z)([A-Z0-9]+)$",
    re.I,
)
_RE_61E = re.compile(
    r"R61([A-Z])(\d{3})M[0-9A-Z]", re.I
)  # R61E226ME39L
_RE_R6V = re.compile(
    r"^GRM(155|188|21A|21B|216|31M|32E)R6([01])([A-Z])([0-9]{3})(J|K|M|Z)([A-Z0-9]*)$",
    re.I,
)
_RE_60J = re.compile(
    r"R60J(\d{3})M[0-9A-Z]", re.I
)


def _strip_pn(pn: str) -> str:
    s = re.sub(r"\s*<[gG]>\s*$", "", str(pn).strip())
    s = re.sub(r"\s+", "", s)
    return s.strip().upper()


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "CAP":
        return None
    pn0 = _strip_pn(pn)
    if not pn0.startswith("GRM"):
        return None

    m6v = _RE_R6V.match(pn0)
    if m6v:
        sc, _dnum, vcode, c3, tcode, _tail = m6v.groups()
        size = _SIZE.get(sc.upper(), "")
        cap = pf_eia_3_to_str(c3) or ""
        if not size or not cap:
            return None
        vol = _VOLT.get(vcode.upper(), _R6X_FOLLOW_VOL.get(vcode.upper(), ""))
        tol = _TOL.get(tcode.upper(), "")
        return "_".join(p for p in (size, cap, vol, "X5R", tol) if p)

    m7v = _RE_R7V.match(pn0)
    if m7v:
        sc, dcode, vcode, c3, tcode, _tail = m7v.groups()
        size = _SIZE.get(sc.upper(), "")
        cap = pf_eia_3_to_str(c3) or ""
        if not size or not cap:
            return None
        diel = "X7R" if dcode == "71" else "X5R"
        vol = _VOLT.get(vcode.upper(), "")
        tol = _TOL.get(tcode.upper(), "")
        return "_".join(p for p in (size, cap, vol, diel, tol) if p)

    m = _RE_R71C.match(pn0)
    if m:
        scc, dcode, c3, tail = m.groups()
        size = "0402" if scc == "155" else "0603"
        diel = "X7R" if dcode == "71" else "X5R"
        cap3 = c3
        vnum = cap3[2] if len(cap3) == 3 and cap3.isdigit() else "0"
        cap = pf_eia_3_to_str(cap3) or ""
        vol = _R71_C_VOL.get(vnum, "16V")
        tol = _TOL.get(tail[0] if tail else "K", "")
        if not cap:
            return None
        return "_".join(p for p in (size, cap, vol, diel, tol) if p)

    if re.search(r"^GRM21", pn0) or re.search(r"GRM21B", pn0):
        m61 = _RE_61E.search(pn0)
        if m61 and len(m61.group(2)) == 3:
            vletter, c3 = m61.group(1), m61.group(2)
            cap = pf_eia_3_to_str(c3) or ""
            vol = _R6X_FOLLOW_VOL.get(vletter.upper(), "6.3V")
            diel = "X5R"
            tol = "20%"
            if cap:
                return "_".join(p for p in ("0805", cap, vol, diel, tol) if p)
        m60 = _RE_60J.search(pn0)
        if m60:
            c3 = m60.group(1)
            cap = pf_eia_3_to_str(c3) or ""
            if cap:
                return "_".join(p for p in ("0805", cap, "6.3V", "X5R", "20%") if p)

    mj = re.search(r"J(\d{3})M[0-9A-Z]", pn0)
    if "GRM21" in pn0 and mj and not _RE_61E.search(pn0) and not _RE_60J.search(pn0):
        cap = pf_eia_3_to_str(mj.group(1)) or ""
        if cap:
            return "_".join(p for p in ("0805", cap, "6.3V", "X5R", "20%") if p)

    if "1555" in pn0[:8] or pn0[3:6] == "155":
        mr0 = re.search(r"([0-9])R([0-9])(?:C|A|D|L)", pn0, re.I)
        if mr0 and ("C0" in pn0 or "C1H" in pn0 or "5R0" in pn0):
            cap = f"{mr0.group(1)}.{mr0.group(2)}pF"
            tol = "5%" if re.search(r"J[A0-9]*D|JA", pn0) else "5%"
            return "_".join(p for p in ("0402", cap, "50V", "C0G", tol) if p)

    # GRM1555C1H270JA01D, GRM1885C1H104KA… — C0G/NP0, C1H 50V, J=5% / K=10% in PN
    m1h = re.match(
        r"^GRM(1555|1885|2160|1632)C1H([0-9]{3})(J|K)([A-Z0-9]+)$", pn0, re.I
    )
    if m1h:
        skey, c3, tj, _tail = m1h.group(1), m1h.group(2), m1h.group(3), m1h.group(4)
        size = {"1555": "0402", "1885": "0603", "2160": "0805", "1632": "1210"}.get(
            skey, "0402"
        )
        cap = pf_eia_3_to_str(c3) or ""
        if not cap:
            return None
        tol = "5%" if tj.upper() == "J" else _TOL.get(tj.upper(), "10%")
        return "_".join(p for p in (size, cap, "50V", "C0G", tol) if p)

    return None

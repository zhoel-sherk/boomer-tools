"""
Taiyo Yuden MLCC: ``UMK*``, ``EMK*``, ``JMK*`` (subset; verify against ordering guide).
https://www.yuden.co.jp/ — EIA value codes, size codes 105/107/212/…
"""

from __future__ import annotations

import re

from ._cap_decode import pf_eia_3_to_str

VENDOR_NAME = "TaiyoYuden_MLCC"
COMPONENT_TYPES = ["CAP"]
PARSER_PRIORITY = 65

_SIZE_UMK = {
    "105": "0402",
    "107": "0603",
    "212": "0805",
    "315": "1206",
    "316": "1206",
    "325": "1210",
    "327": "2012",
    "336": "2012",
}

# UMK105CH120JV — value 120, tol J, optional voltage letter V
_RE_UMK = re.compile(
    r"^UMK(105|107|212|315|316|325|327|336)(.)(.)(\d{3})(J|K|F|M|Z)(V)?$",
    re.I,
)
_VOL_UMK = {
    "A": "250V",
    "B": "100V",
    "C": "6.3V",
    "D": "10V",
    "E": "16V",
    "F": "25V",
    "G": "50V",
    "H": "50V",
    "J": "6.3V",
    "K": "25V",
    "L": "16V",
    "M": "100V",
    "P": "10V",
    "Q": "6.3V",
}
_DIEL_UMK = {
    "C": "C0G",
    "A": "X5R",
    "B": "X7R",
    "D": "X5R",
    "E": "X6S",
    "F": "X6S",
}

# EMK105BJ105K — BJ + value; EMK105B7223K — B + 4-digit (last 3 = EIA)
_RE_EMK_BJ = re.compile(
    r"^EMK(105|107|212|316|325)BJ(\d{3,4})(K|J|M|G|Z).*$",
    re.I,
)
_RE_EMK_Bx = re.compile(
    r"^EMK(105|107|212|316|325)B(\d{3,4})(K|J|M|G|Z).*$",
    re.I,
)

_SIZE_EMK = {
    "105": "0402",
    "107": "0603",
    "212": "0805",
    "316": "1206",
    "325": "1210",
}

# JMK/TMK212BJ226MG (BJ + EIA, X5R family)
_RE_JMK_BJ = re.compile(
    r"^[JT]MK(105|107|212|315|316|325)BJ(\d{3})(J|K|M)?", re.I
)
_SIZE_JMK = {
    "105": "0402", "107": "0603", "212": "0805",
    "315": "1206", "316": "1206", "325": "1210",
}


def parse(pn: str, component_type: str) -> str | None:
    if component_type != "CAP":
        return None
    pn0 = re.sub(r"\s*<[gG]>\s*$", "", str(pn).strip())
    pn0 = re.sub(r"\s+", "", pn0).strip().upper()
    pni = re.sub(r"[-].*$", "", pn0)

    mj = _RE_JMK_BJ.match(pni)
    if mj:
        sc, c3, tol_ch = mj.groups()
        sz = _SIZE_JMK.get(sc, "")
        if not sz or len(c3) != 3:
            return None
        cap = pf_eia_3_to_str(c3) or ""
        tol = {"J": "5%", "K": "10%", "M": "20%"}.get((tol_ch or "").upper(), "")
        if cap:
            return "_".join(p for p in (sz, cap, "6.3V", "X5R", tol) if p)

    m = _RE_UMK.match(pni)
    if m:
        sc, t1, t2, c3, _tol, _v = m.groups()
        sz = _SIZE_UMK.get(sc, "")
        if not sz:
            return None
        cap = pf_eia_3_to_str(c3)
        if not cap:
            return None
        vol = _VOL_UMK.get(t2.upper(), "")
        diel = _DIEL_UMK.get(t1.upper(), t1)
        segs: list[str] = [sz, cap]
        if diel and len(diel) > 1:
            segs.append(diel)
        if vol:
            segs.append(vol)
        return "_".join(segs)

    m_bj = _RE_EMK_BJ.match(pni)
    if m_bj:
        sc, val_block, _t = m_bj.groups()
        sz = _SIZE_EMK.get(sc, "")
        if not sz:
            return None
        if len(val_block) == 3 and pf_eia_3_to_str(val_block):
            return f"{sz}_{pf_eia_3_to_str(val_block)}"
        return None

    m_b = _RE_EMK_Bx.match(pni)
    if m_b:
        sc, vblock, _t = m_b.groups()
        sz = _SIZE_EMK.get(sc, "")
        if not sz or len(vblock) < 3:
            return None
        eia3 = vblock[-3:]
        cap = pf_eia_3_to_str(eia3)
        if not cap:
            return None
        return f"{sz}_{cap}_X5R"
    return None

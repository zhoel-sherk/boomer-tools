"""parse_pn coverage against example6 abmq601 + golden MPNs."""

from __future__ import annotations

import os
import re
import sys

import pytest

tests_path = os.path.dirname(os.path.realpath(__file__))
_boomer_root = os.path.dirname(tests_path)
sys.path.insert(0, os.path.join(_boomer_root, "src"))

import clean_component
import pn_original


def _classify_mpn(mpn: str) -> str:
    u = mpn.upper()
    if u.startswith("RM0") and "TN" in u:
        return "RES"
    if re.match(r"^WR(02|04|06|08|10|12|20|25)", u):
        return "RES"
    if re.match(r"^0?402N|0?603N|12(06|10)N", u, re.I):
        return "CAP"
    if u.startswith(("EMK", "UMK", "JMK", "TMK", "LMK", "JDK")):
        return "CAP"
    if u.startswith("YAGEO/RC") or u.startswith("RC0"):
        return "RES"
    if u.startswith("YAGEO/CC") or (u.startswith("CC") and "NPO" in u or "X" in u):
        return "CAP"
    return "SKIP"


def test_golden_tai_walsin_taiyo_parsing():
    pn_original.CONVERTERS.clear()
    cfg = clean_component.CleanConfig()
    for raw, expect_sub, ct in (
        ("TA-I/RM04JTN100", "10R", "RES"),
        ("TA-I/ RM04JTN100", "10R", "RES"),
        ("TA-I/RB04BTP1000", "100R", "RES"),
        ("YAGEO/RC0402FR-07499RL", "49.9R", "RES"),
        ("RC0603FR-07680RL", "68R", "RES"),
        ("WR04X1001FTL", "1K", "RES"),
        ("WR08X000PTL", "0R", "RES"),
        ("WR25X1001FTL", "1K", "RES"),
        ("WALSIN/0402N100J500CT", "10pF", "CAP"),
        ("WALSIN/CC0402KRX7R9BB103", "10nF", "CAP"),
        ("TAIYO/EMK105B7223KV-F", "22nF", "CAP"),
        ("TAIYO/UMK105CH120JV-F", "12pF", "CAP"),
    ):
        out = pn_original.parse_pn(raw, ct, cfg)
        assert out, f"parse failed for {raw!r}"
        if expect_sub:
            assert expect_sub in out, f"{out!r} missing {expect_sub!r}"


@pytest.mark.skipif(
    not os.path.isfile(
        os.path.join(_boomer_root, "examples", "example6", "original_gen3_bom.xlsx")
    ),
    reason="example6 xlsx not in tree",
)
def test_example6_parse_rate_rm_wr_emk_umk():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    path = os.path.join(_boomer_root, "examples", "example6", "original_gen3_bom.xlsx")
    df = pd.read_excel(path, sheet_name="abmq601", header=None, engine="openpyxl")
    pn_original.CONVERTERS.clear()
    cfg = clean_component.CleanConfig()
    n_ok, n_tried = 0, 0
    seen: set[str] = set()
    for i in range(len(df)):
        for j in range(df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and str(v) == "nan"):
                continue
            s = str(v).strip()
            if "/" not in s or len(s) < 6:
                continue
            mpn = s.split("/")[-1]
            mpn = re.sub(r"<[gG]>\s*$", "", mpn)
            mpn2 = re.sub(r"\s+", "", mpn)
            if mpn2 in seen:
                continue
            seen.add(mpn2)
            ct = _classify_mpn(mpn2)
            if ct == "SKIP":
                continue
            n_tried += 1
            r = pn_original.parse_pn(mpn2, ct, cfg)
            if r:
                n_ok += 1
    assert n_tried > 200
    assert n_ok / n_tried >= 0.7, f"parse rate {n_ok}/{n_tried} below 0.7"


def test_yageo_resistor_and_cap_both_load():
    """Both Yageo_RES and Yageo_CAP must register (regression: duplicate VENDOR_NAME)."""
    pn_original.CONVERTERS.clear()
    pn_original.load_converters()
    assert "Yageo_RES" in pn_original.CONVERTERS
    assert "Yageo_CAP" in pn_original.CONVERTERS

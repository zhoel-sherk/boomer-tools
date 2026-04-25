"""Tests for clean_component CleanConfig and clean_preview."""
from __future__ import annotations

import os
import re
import sys

import pytest

tests_path = os.path.dirname(os.path.realpath(__file__))
_boomer_root = os.path.dirname(tests_path)
sys.path.append(os.path.join(_boomer_root, "src"))

import clean_component


def _example6_xlsx_paths() -> tuple[str, str]:
    d = os.path.join(_boomer_root, "examples", "example6")
    return (os.path.join(d, "original_gen3_bom.xlsx"), os.path.join(d, "bom_final.xlsx"))


def _load_example6_abmq601_comment_map():
    """
    Build def (插件位置) -> Comment string as col2+col3 joined by '+' from abmq601.
    Data rows start at index 4 (0-based) after the Chinese header block.
    """
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    orig_path, _ = _example6_xlsx_paths()
    orig = pd.read_excel(orig_path, sheet_name="abmq601", header=None, engine="openpyxl")
    dmap: dict[str, str] = {}
    for i in range(4, len(orig)):
        row = orig.iloc[i]
        de = row[8]
        if de is None or (isinstance(de, float) and str(de) == "nan"):
            continue
        sdef = str(de).strip()
        if not sdef:
            continue
        c2, c3 = row[2], row[3]
        parts: list[str] = []
        for x in (c2, c3):
            if x is not None and not (isinstance(x, float) and str(x) == "nan"):
                t = str(x).strip()
                if t:
                    parts.append(t)
        dmap[sdef] = "+".join(parts)
    return dmap


def _dip_part_anchor_in_comment(part: str, cmt: str) -> bool:
    """
    Heuristic: bom_final 'part' values with a ``DIP_`` prefix are a shop-floor / hand
    label for THT (through-hole) or off-SMD-line assembly—the same idea as marking
    rows «THT» or «DIP» in docs; it is *not* limited to an IC in a DIP package.

    The vendor Comment line may spell MPNs differently; this helper only finds anchors.
    """
    c = re.sub(r"\s+", "", str(cmt))
    body = str(part)[4:].replace(" ", "")
    if body in c or body.replace("_", "") in c.replace("_", ""):
        return True
    for tok in body.split("_"):
        if len(tok) >= 4 and tok in c:
            return True
    if "M2*6" in cmt and "SCREW" in str(part).upper():
        return True
    if "1900-070" in c and "RJ45" in part:
        return True
    return False


def test_resistor_drops_package_when_config():
    cfg = clean_component.CleanConfig(resistor_include_package=False)
    out = clean_component.parse_resistor("100R+1/16W+0402", cfg)
    assert "0402" not in out
    assert "100" in out or "100R" in out


def test_cap_drops_voltage_when_config():
    cfg = clean_component.CleanConfig(cap_include_voltage=False, cap_include_package=False)
    out = clean_component.parse_capacitor("22PF+50V+0402+±5%(J)+X7R", cfg)
    assert "50V" not in out
    assert "X7R" in out or "22" in out.upper()


def test_clean_preview_five_tuples():
    r = clean_component.clean_preview(["100R+0402", ""], None)
    assert len(r) == 2
    assert len(r[0]) == 5
    assert r[1][2] == ""  # empty comment


def test_classify_murata_like_cap():
    t = clean_component.classify_component_type("10UF+16V+X5R+0603")
    assert t == "CAP"


def test_parse_resistor_space_separated_bom_comment():
    """BOM «Comment» often uses spaces, not '+'; package may appear as (0402) inside a token."""
    cfg = clean_component.CleanConfig()
    out = clean_component.parse_resistor(
        "RES 1K OHM 1/16W(0402)1%", cfg
    )
    assert out == "0402_1K_1%"
    assert out != "RES 1K OHM 1/16W(0402)1%"


def test_resistor_template_orders_nom_pack_watt_tolerance():
    cfg = clean_component.CleanConfig(
        output_separator="-",
        resistor_template=("nom", "pack", "watt", "%"),
    )
    out = clean_component.parse_resistor("100R+1/16W+0402+5%", cfg)
    assert out == "100R-0402-1/16W-5%"


def test_cap_template_orders_nom_pack_film_tolerance_voltage():
    cfg = clean_component.CleanConfig(
        output_separator="-",
        cap_template=("nom", "pack", "film", "%", "W"),
    )
    out = clean_component.parse_capacitor("0.1UF+16V+0402+X5R+20%", cfg)
    assert out == "0.1UF-0402-X5R-20%-16V"


def test_component_prefix_can_use_or_skip_global_separator():
    with_sep = clean_component.CleanConfig(
        output_separator="-",
        cap_prefix="C",
        resistor_prefix="R",
        inductor_prefix="L",
        prefix_use_separator=True,
    )
    assert clean_component.parse_capacitor("12PF+0402", with_sep) == "C-0402-12PF"
    assert clean_component.parse_resistor("100R+0402", with_sep) == "R-0402-100R"
    assert clean_component.parse_inductor("2.2UH+3015", with_sep) == "L-3015-2.2UH"

    no_sep = clean_component.CleanConfig(
        output_separator="-",
        cap_prefix="C",
        prefix_use_separator=False,
    )
    assert clean_component.parse_capacitor("12PF+0402", no_sep) == "C0402-12PF"


def test_inferit_res_cap_ind_regex_presets():
    cfg = clean_component.CleanConfig()

    res = clean_component.clean_one("RES 0201 10K OHM +/-1% LEAD-FREE - Y01", cfg)
    assert res[2] == "RES"
    assert res[0] == "0201_10K_1%"

    res_zero = clean_component.clean_one("RES 0201 0 OHM +/-5% LEAD-FREE - Y01", cfg)
    assert res_zero[0] == "0201_0R_5%"

    cap = clean_component.clean_one("CAP 0402 10pF/50V +/-5% NPO LEAD-FREE - Y01", cfg)
    assert cap[2] == "CAP"
    assert cap[0] == "0402_10pF_50V_NPO_5%"

    ind = clean_component.clean_one(
        "SMD-INDUCTOR 4.45*4.05*1.2mm 1.0uH ±20% 47mΩMax 4.5A SMD LEAD-FREE - 092",
        cfg,
    )
    assert ind[2] == "IND"
    assert ind[0] == "1.0uH_4.5A_20%"

    bead = clean_component.clean_one(
        "FERRITE-BEAD 0402 120 OHM@100MHz ±25% 700mA LEAD-FREE - 309",
        cfg,
    )
    assert bead[2] == "IND"
    assert bead[0] == "0402_120R@100MHZ_700MA_25%"


def test_inferit_other_regex_presets_extract_mpn():
    assert clean_component.clean_one("POWER-IC RT8120AZSP ONE-PHASE SOP-8 LEAD-FREE")[0] == "RT8120AZSP"
    assert clean_component.clean_one("TYPEC IC IT8851FN-128/HX V0.2.8 USB Type-C")[0] == "IT8851FN-128/HX"
    assert clean_component.clean_one("MOSFET N-CHANNEL MDU1514URH 30V DFN-56 RoHS")[0] == "MDU1514URH"
    assert clean_component.clean_one("SMD-RECTIFIER-DIODES 1N4148WS 75V 200mA SOD323")[0] == "1N4148WS"
    assert clean_component.clean_one("CRYSTAL 25.000MHz 12pF ±10PPM ESR<50 OHM")[0] == "25.000MHZ"


def test_vendor_pn_uses_component_template_order():
    cfg = clean_component.CleanConfig(
        output_separator="-",
        cap_template=("nom", "pack", "film", "%", "W"),
    )
    row = clean_component.clean_one("YAGEO/CC0402KRX7R9BB102", cfg)
    assert row[3] == "pn"
    assert row[0] == "1nF-0402-X7R-10%-50V"


def test_example6_bom_golden_def_bijection():
    """
    example6: supplier BOM (abmq601) and hand-export bom_final list the same designator
    groups (def); Comment is reconstructed as 品名規格+规格 (col2+col3) with '+'.
    """
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    orig_path, final_path = _example6_xlsx_paths()
    if not (os.path.isfile(orig_path) and os.path.isfile(final_path)):
        pytest.skip("example6 xlsx not in tree (expected under examples/example6/)")

    dmap = _load_example6_abmq601_comment_map()
    gf = pd.read_excel(final_path, engine="openpyxl")
    assert "def" in gf.columns and "part" in gf.columns
    defs_golden = {str(x).strip() for x in gf["def"].tolist() if str(x).strip()}
    defs_orig = set(dmap.keys())
    assert len(defs_golden) == len(gf), "unique def per row in bom_final"
    assert defs_golden == defs_orig
    for d, cmt in dmap.items():
        assert cmt, f"non-empty comment for {d!r}"


def test_example6_bom_dip_mpn_anchors_in_vendor_comment():
    """
    Where bom_final 'part' uses a ``DIP_`` prefix, at least one stable token from the
    part string appears in the vendor Comment line (join key: ``def`` in abmq601).

    ``DIP_`` here means THT / not pick-and-place line, not «must be a DIP package»;
    the test checks substring anchors only, not package type.
    """
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    orig_path, final_path = _example6_xlsx_paths()
    if not (os.path.isfile(orig_path) and os.path.isfile(final_path)):
        pytest.skip("example6 xlsx not in tree (expected under examples/example6/)")

    dmap = _load_example6_abmq601_comment_map()
    gf = pd.read_excel(final_path, engine="openpyxl")
    for _, row in gf.iterrows():
        part = str(row["part"])
        sdef = str(row["def"]).strip()
        cmt = dmap[sdef]
        if not part.startswith("DIP_"):
            continue
        assert _dip_part_anchor_in_comment(
            part, cmt
        ), f"no anchor for {part!r} in comment for {sdef!r}:\n{cmt!r}"


def test_mlcc_one_line_various_spacing():
    cfg = clean_component.CleanConfig()
    for raw in (
        "MLCC 15PF/50V (0402) NPO 5%",
        "MLCC 47PF/50V(0402)NPO 5%",
        "MLCC 0.1UF/16V(0402)X7R 10%",
    ):
        out = clean_component.parse_capacitor(raw, cfg)
        assert out != raw
        assert "0402" in out
        assert "50V" in out or "16V" in out


def test_normalize_for_regex_keeps_cap_voltage_slash():
    assert clean_component._normalize_for_regex_parsing("MLCC 15PF/50V (0402) NPO 5%") == (
        "MLCC 15PF/50V (0402) NPO 5%"
    )
    assert clean_component._normalize_for_regex_parsing("MFR/RC0603JR-1KL") == "RC0603JR-1KL"


def test_normalize_for_regex_keeps_fractional_wattage():
    assert clean_component._normalize_for_regex_parsing("100R+1/16W+0402") == "100R+1/16W+0402"


def test_classify_tai_mpn_strips_space_after_slash():
    assert clean_component.classify_component_type("TA-I/RM04JTN100") == "RESISTOR"
    assert clean_component.classify_component_type("TA-I/ RM04JTN100") == "RESISTOR"


def test_classify_bare_cl_and_yageo_rc():
    assert clean_component.classify_component_type("CL05B102KB5NNNC") == "CAP"
    assert clean_component.classify_component_type("RC0402JR-0710RL") == "RESISTOR"


def test_yageo_cc_includes_voltage_tolerance():
    import pn_original

    pn_original.CONVERTERS.clear()
    pn_original.load_converters()
    cfg = clean_component.CleanConfig()
    out = pn_original.parse_pn("CC0402KRX7R9BB102", "CAP", cfg)
    assert out
    assert "50V" in out
    assert "10%" in out
    assert "X7R" in out


def test_murata_grm1555_c1h_uses_vendor_pn():
    import pn_original

    pn_original.CONVERTERS.clear()
    pn_original.load_converters()
    cfg = clean_component.CleanConfig()
    row = clean_component.clean_one("MURATA/GRM1555C1H270JA01D <G>", cfg)
    assert row[3] in ("pn", "vendor")
    assert "27pF" in row[0] or "27" in row[0]
    assert "C0G" in row[0] or "5%" in row[0]
    assert row[2] == "CAP"


def test_new_vendor_pn_regressions():
    import pn_original

    pn_original.CONVERTERS.clear()
    pn_original.load_converters()
    cfg = clean_component.CleanConfig()

    murata = clean_component.clean_one("MURATA/GRM155R71H681KA01D", cfg)
    assert murata[2] == "CAP" and murata[3] == "pn"
    assert "680pF" in murata[0] and "50V" in murata[0] and "X7R" in murata[0]

    yageo = clean_component.clean_one("YAGEO/RC0402FR-0749K9L", cfg)
    assert yageo[2] == "RES" and yageo[3] == "pn"
    assert "49.9K" in yageo[0] and "0402" in yageo[0]

    walsin = clean_component.clean_one("WALSIN/WW25RR001FTL", cfg)
    assert walsin[2] == "RES" and walsin[3] == "pn"
    assert "2512" in walsin[0] and "0.001R" in walsin[0]


def test_vendor_pn_list_does_not_fall_back_to_regex():
    import pn_original

    pn_original.CONVERTERS.clear()
    pn_original.load_converters()
    cfg = clean_component.CleanConfig()
    cases = {
        "RC0402-JR-07510RL": ("RES", "51R"),
        "WR04W2R20FTL": ("RES", "2.20R"),
        "RC0402FR-076K49L (PC335)": ("RES", "6.49K"),
        "RC0402-JR-0775RL": ("RES", "75R"),
        "RM06JTN-2R2": ("RES", "2.2R"),
        "GRM155R61E104K": ("CAP", "100nF"),
        "GRM155R61A104KA01D": ("CAP", "100nF"),
        "GRM155R61C105KA12D": ("CAP", "1uF"),
        "0402X105K6R3CT": ("CAP", "1uF"),
        "GRM155R60J105KE19D": ("CAP", "1uF"),
        "TAIYO/TMK107BJ105KA-T": ("CAP", "1uF"),
    }
    for raw, (part_code, expected) in cases.items():
        cleaned, _typ, code, source = clean_component.clean_one(raw, cfg)
        assert code == part_code, raw
        assert source == "pn", raw
        assert expected in cleaned, raw


def test_component_library_plain_and_structured(tmp_path, monkeypatch):
    import component_library

    lib = tmp_path / "components.txt"
    lib.write_text("SN74LVC2G17DCKR\n", encoding="utf-8")
    monkeypatch.setenv("BOOMER_COMPONENTS_TXT", str(lib))

    row = clean_component.clean_one("MFR/SN74LVC2G17DCKR", clean_component.CleanConfig())
    assert row == ("SN74LVC2G17DCKR", "OTHER", "OTHER", "library")

    disabled = clean_component.clean_one(
        "MFR/SN74LVC2G17DCKR",
        clean_component.CleanConfig(use_component_library=False),
    )
    assert disabled[3] != "library"

    ok = component_library.append_component(
        "Vendor/FANCY-IC-1 <G>", "FANCY-IC-1", "OTHER", "SOT-23", lib
    )
    assert ok
    assert not component_library.append_component(
        "FANCY-IC-1", "FANCY-IC-1", "OTHER", "", lib
    )
    got = component_library.lookup_component("FANCY-IC-1", lib)
    assert got is not None
    assert got.cleaned == "FANCY-IC-1"
    assert got.footprint == "SOT-23"


def test_parse_capacitors_false_returns_unchanged():
    cfg = clean_component.CleanConfig(parse_capacitors=False)
    raw = "MLCC 15PF/50V (0402) NPO 5%"
    assert clean_component.parse_capacitor(raw, cfg) == raw


def test_clean_one_respects_master_switches():
    c_off = clean_component.CleanConfig(parse_capacitors=False)
    t = clean_component.clean_one("MLCC 10PF/50V(0402)NPO 5%", c_off)
    assert t[0] == "MLCC 10PF/50V(0402)NPO 5%" and t[3] == "off"

    c_on = clean_component.CleanConfig(parse_capacitors=True, use_vendor_pn=False)
    t2 = clean_component.clean_one("MFR/RM10K", c_on)
    assert t2[1] == "RESISTOR" and t2[3] == "regex"

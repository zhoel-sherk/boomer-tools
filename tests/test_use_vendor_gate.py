"""use_pn_codecs runs pn_original; use_vendor_pn only changes Source label (vendor vs pn)."""

from __future__ import annotations

import os
import sys

tests_path = os.path.dirname(os.path.realpath(__file__))
_boomer_root = os.path.dirname(tests_path)
sys.path.insert(0, os.path.join(_boomer_root, "src"))

import clean_component
import pn_original


def test_no_vendor_source_when_use_vendor_off():
    pn_original.CONVERTERS.clear()
    cfg = clean_component.CleanConfig(
        use_pn_codecs=True,
        use_vendor_pn=False,
        parse_resistors=True,
        parse_capacitors=True,
    )
    cleaned, _typ, _code, vnote = clean_component.clean_one("TA-I/RM04JTN100", cfg)
    assert vnote == "pn"
    assert "10R" in cleaned


def test_vendor_source_when_enabled():
    pn_original.CONVERTERS.clear()
    cfg = clean_component.CleanConfig(
        use_pn_codecs=True,
        use_vendor_pn=True,
        parse_resistors=True,
        parse_capacitors=True,
    )
    t = clean_component.clean_one("TA-I/RM04JTN100", cfg)
    assert t[3] == "vendor"
    assert "10R" in t[0] or "R" in t[0]


def test_use_pn_codecs_off_falls_back_to_regex():
    pn_original.CONVERTERS.clear()
    cfg = clean_component.CleanConfig(
        use_pn_codecs=False,
        use_vendor_pn=True,
        parse_resistors=True,
    )
    t = clean_component.clean_one("TA-I/RM04JTN100", cfg)
    assert t[3] == "regex"

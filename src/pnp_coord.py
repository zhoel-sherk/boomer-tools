"""
PnP coordinate helpers for GUI actions (clean cells, explicit mm↔mil conversion).

Core merge/cross-check paths preserve numeric magnitude except stripping trailing unit tokens.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_TRAILING_UNITS = re.compile(
    r"(?:\s*|\b)(?:mil|mils|thou|ths?|mm|millimeters?|in|inch|inches)\s*$",
    re.IGNORECASE,
)

MIL_TO_MM = Decimal("0.0254")
MM_TO_MIL = Decimal("1") / MIL_TO_MM


def strip_trailing_coord_units(s: str) -> str:
    """Remove trailing mil/mm/inch tokens only (no other digit stripping)."""
    t = str(s).strip()
    while True:
        nxt = _TRAILING_UNITS.sub("", t).rstrip()
        if nxt == t:
            break
        t = nxt
    return t


def clean_numeric_cell_keep_separators(raw: object) -> str:
    """
    Keep digits and decimal separators (. , -) only — preserves e.g. 40.3456.
    If both '.' and ',' occur, the rightmost acts as the decimal separator.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    s = strip_trailing_coord_units(s)
    neg = False
    if s.startswith("-"):
        neg = True
        s = s[1:].strip()
    kept = "".join(c for c in s if c.isdigit() or c in "., ")
    kept = kept.replace(" ", "")
    if not kept:
        return ""
    last_dot = kept.rfind(".")
    last_comma = kept.rfind(",")
    dec_pos = max(last_dot, last_comma)
    if dec_pos == -1:
        num = kept.replace(".", "").replace(",", "")
    else:
        int_part = kept[:dec_pos].replace(".", "").replace(",", "")
        frac_part = kept[dec_pos + 1 :].replace(".", "").replace(",", "")
        num = f"{int_part}.{frac_part}" if frac_part else int_part
    if not num or num in ".-":
        return ""
    if neg:
        num = "-" + num.lstrip("-")
    return num


def parse_decimal_loose(raw: object) -> Decimal | None:
    s = clean_numeric_cell_keep_separators(raw)
    if not s or s in "-":
        return None
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


def format_four_fractional_digits(value: Decimal | float | str) -> str:
    """Exactly four digits after the decimal point (explicit mm↔mil conversion)."""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        try:
            d = Decimal(str(float(value)))
        except (InvalidOperation, ValueError):
            return ""
    q = d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    neg = q < 0
    q = abs(q)
    s = format(q, "f")
    if "." in s:
        a, b = s.split(".", 1)
        b = (b + "0000")[:4]
    else:
        a, b = s, "0000"
    return ("-" if neg else "") + f"{a}.{b}"


def convert_xy_mm_to_mil_row(x_raw: object, y_raw: object) -> tuple[str, str]:
    xd = parse_decimal_loose(x_raw)
    yd = parse_decimal_loose(y_raw)
    if xd is None or yd is None:
        return "", ""
    return format_four_fractional_digits(xd * MM_TO_MIL), format_four_fractional_digits(yd * MM_TO_MIL)


def convert_xy_mil_to_mm_row(x_raw: object, y_raw: object) -> tuple[str, str]:
    xd = parse_decimal_loose(x_raw)
    yd = parse_decimal_loose(y_raw)
    if xd is None or yd is None:
        return "", ""
    return format_four_fractional_digits(xd * MIL_TO_MM), format_four_fractional_digits(yd * MIL_TO_MM)

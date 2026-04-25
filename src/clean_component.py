from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Set

import logger

if TYPE_CHECKING:
    import pandas as pd

# Extended package list for all component types
PACKAGES = ['01005', '0201', '0402', '0603', '0805', '1206', '1210', '1812', '2010', '2512', '2220', '2225', '3015', '3020', '3030', '0630', '0730', '1030', '1239', '1340', '1350', '1913', '2135', '2312', '2550', '2759', '3921', '5650', '5850', '5950', '7060', '7640', '1540', '4516', '3812', '3813', '5012', '5013', '5015', '5020', '5025', '5030', '5035', '5040', '5050', '5060', '5125', '5130', '5140', '5155', '5820', '5840', '5850', '6108', '6115', '6120', '6135', '6150', '6155', '6165', '6265', '6330', '7012', '7035', '7040', '7055', '7345', '7355', '8050', '8060', '8250', '8450', '8850']
PACKAGE_PATTERN = '|'.join(PACKAGES)

CAP_UNITS = {
    'F': '', 'UF': 'u', 'NF': 'n', 'PF': 'p',
    'F0': '', 'UF0': 'u', 'NF0': 'n', 'PF0': 'p',
}

RES_UNITS = {
    'R': '', 'KR': 'K', 'MR': 'M', 'MRM': 'm',
    'OHM': '', 'KOHM': 'K', 'MOHM': 'M', 'M': 'M', 'K': 'K',
}

INDUCTOR_UNITS = {
    'UH': 'uH', 'NH': 'nH', 'MH': 'mH', 'H': 'H',
}

class CleanSettings:
    """Deprecated: use CleanConfig. Kept for any legacy references."""

    resistor_include_tolerance = True
    resistor_include_package = True
    resistor_custom_regex = ""
    cap_include_voltage = True
    cap_include_dielectric = True
    cap_custom_regex = ""
    other_custom_regex = ""


@dataclass
class CleanConfig:
    """
    Per-run settings for Clean BOM. Mirrors classic app checkboxes and adds vendor PN.
    When a field is False, that segment is dropped from the normalized string (underscore-joined).
    """

    resistor_include_package: bool = True
    resistor_include_tolerance: bool = True
    # Capacitor
    cap_include_package: bool = True
    cap_include_voltage: bool = True
    cap_include_dielectric: bool = True
    cap_include_tolerance: bool = True
    cap_convert_nf_to_uf: bool = False
    # Inductor
    inductor_include_package: bool = True
    inductor_include_current: bool = True
    inductor_include_tolerance: bool = True
    # MPN decoders in pn_original (Yageo/Murata/TAI_RM/…); independent of the «vendor» source label
    use_pn_codecs: bool = True
    # When True, clean_one Source is «vendor»; when False but use_pn_codecs, Source is «pn»
    use_vendor_pn: bool = False
    # Master switches: when False, that family leaves the comment unchanged (after vendor pass)
    parse_resistors: bool = True
    parse_capacitors: bool = True
    parse_inductors: bool = True
    # Join character for segments (default matches historical underscore style)
    output_separator: str = "_"
    # Ordered output slots. UI labels: nom, pack, watt, %, film, W.
    resistor_template: Tuple[str, ...] = ("pack", "nom", "%")
    cap_template: Tuple[str, ...] = ("pack", "nom", "W", "film", "%")
    # Optional machine/user prefixes. Empty prefix means "off".
    resistor_prefix: str = ""
    cap_prefix: str = ""
    inductor_prefix: str = ""
    prefix_use_separator: bool = True
    # User-maintained OTHER/component overrides from components.txt.
    use_component_library: bool = True


def _default_config(config: Optional[CleanConfig]) -> CleanConfig:
    return config if config is not None else CleanConfig()


_RES_TEMPLATE_FIELDS = {"nom", "pack", "watt", "%"}
_CAP_TEMPLATE_FIELDS = {"nom", "pack", "film", "%", "W"}


def _template_fields(
    template: Tuple[str, ...] | list[str] | None,
    allowed: set[str],
    default: Tuple[str, ...],
) -> Tuple[str, ...]:
    if not template:
        return default
    out: list[str] = []
    seen: set[str] = set()
    for raw in template:
        key = str(raw).strip()
        if not key or key.lower() == "none":
            continue
        if key not in allowed or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return tuple(out) if out else default


def _format_component_fields(
    fields: dict[str, str],
    template: Tuple[str, ...] | list[str] | None,
    allowed: set[str],
    default: Tuple[str, ...],
    sep: str,
) -> str:
    parts: list[str] = []
    for key in _template_fields(template, allowed, default):
        val = fields.get(key, "")
        if val:
            parts.append(val)
    return sep.join(parts)


def _apply_prefix(text: str, prefix: str, cfg: CleanConfig) -> str:
    body = str(text).strip()
    pre = str(prefix or "").strip()
    if not body or not pre:
        return body
    joined = f"{pre}{cfg.output_separator}{body}" if cfg.prefix_use_separator else f"{pre}{body}"
    # Avoid duplicate prefixes when the user re-cleans already-prefixed values.
    if body == pre or (
        cfg.prefix_use_separator and cfg.output_separator and body.startswith(f"{pre}{cfg.output_separator}")
    ):
        return body
    return joined


def _format_resistor_fields(fields: dict[str, str], cfg: CleanConfig) -> str:
    f = dict(fields)
    if not cfg.resistor_include_package:
        f.pop("pack", None)
    if not cfg.resistor_include_tolerance:
        f.pop("%", None)
    out = _format_component_fields(
        f,
        cfg.resistor_template,
        _RES_TEMPLATE_FIELDS,
        ("pack", "nom", "%"),
        cfg.output_separator,
    )
    return _apply_prefix(out, cfg.resistor_prefix, cfg)


def _format_cap_fields(fields: dict[str, str], cfg: CleanConfig) -> str:
    f = dict(fields)
    if not cfg.cap_include_package:
        f.pop("pack", None)
    if not cfg.cap_include_voltage:
        f.pop("W", None)
    if not cfg.cap_include_dielectric:
        f.pop("film", None)
    if not cfg.cap_include_tolerance:
        f.pop("%", None)
    out = _format_component_fields(
        f,
        cfg.cap_template,
        _CAP_TEMPLATE_FIELDS,
        ("pack", "nom", "W", "film", "%"),
        cfg.output_separator,
    )
    return _apply_prefix(out, cfg.cap_prefix, cfg)


def _format_inductor_fields(fields: dict[str, str], cfg: CleanConfig) -> str:
    result: list[str] = []
    if cfg.inductor_include_package and fields.get("pack"):
        result.append(fields["pack"])
    if fields.get("nom"):
        result.append(fields["nom"])
    if cfg.inductor_include_current and fields.get("current"):
        result.append(fields["current"])
    if cfg.inductor_include_tolerance and fields.get("%"):
        result.append(fields["%"])
    return _apply_prefix(cfg.output_separator.join(result), cfg.inductor_prefix, cfg)


def _normalize_value_unit(text: str) -> str:
    s = re.sub(r"\s+", "", str(text)).strip()
    m = re.match(r"^([0-9.]+)(PF|NF|UF|F|UH|NH|MH|H)$", s, re.I)
    if not m:
        return s.upper()
    num, unit = m.groups()
    unit_map = {
        "PF": "pF",
        "NF": "nF",
        "UF": "uF",
        "F": "F",
        "UH": "uH",
        "NH": "nH",
        "MH": "mH",
        "H": "H",
    }
    return f"{num}{unit_map[unit.upper()]}"


def _normalize_res_ohm_value(text: str) -> str:
    s = re.sub(r"\s+", "", str(text)).upper()
    if not s:
        return ""
    if s.endswith(("K", "M", "R")):
        return s
    return f"{s}R"


def _parse_inferit_resistor(spec: str, cfg: CleanConfig) -> Optional[str]:
    s = str(spec)
    if "FERRITE-BEAD" in s.upper():
        return None
    m = re.search(
        rf"\bRES(?:ISTOR)?\s+(?P<pack>{PACKAGE_PATTERN})\s+"
        r"(?P<value>[0-9]+(?:\.[0-9]+)?\s*[KMR]?)\s*(?:OHM|Ω)\b"
        r".*?(?:\+/-|±)\s*(?P<tol>[0-9]+(?:\.[0-9]+)?)\s*%",
        s,
        re.I,
    )
    if not m:
        return None
    watt = ""
    wm = re.search(r"\b(\d+/\d+W|\d+(?:\.\d+)?W)\b", s, re.I)
    if wm:
        watt = wm.group(1).upper()
    return _format_resistor_fields(
        {
            "pack": m.group("pack"),
            "nom": _normalize_res_ohm_value(m.group("value")),
            "watt": watt,
            "%": f"{m.group('tol')}%",
        },
        cfg,
    )


def _parse_inferit_capacitor(spec: str, cfg: CleanConfig) -> Optional[str]:
    s = str(spec)
    m = re.search(
        rf"\bCAP\s+(?P<pack>{PACKAGE_PATTERN})\s+"
        r"(?P<value>[0-9]+(?:\.[0-9]+)?\s*(?:PF|NF|UF|F))\s*/\s*"
        r"(?P<voltage>[0-9]+(?:\.[0-9]+)?V)"
        r".*?(?:\+/-|±)\s*(?P<tol>[0-9]+(?:\.[0-9]+)?)\s*%"
        r"(?:\s+(?P<film>NPO|NP0|C0G|COG|X7R|X5R|X6S|X8R|Y5V|Z5U))?",
        s,
        re.I,
    )
    if not m:
        return None
    film = (m.group("film") or "").upper()
    if film == "COG":
        film = "C0G"
    return _format_cap_fields(
        {
            "pack": m.group("pack"),
            "nom": _normalize_value_unit(m.group("value")),
            "W": m.group("voltage").upper(),
            "film": film,
            "%": f"{m.group('tol')}%",
        },
        cfg,
    )


def _parse_inferit_inductor(spec: str, cfg: CleanConfig) -> Optional[str]:
    s = str(spec)
    up = s.upper()
    if "FERRITE-BEAD" in up:
        m = re.search(
            rf"\bFERRITE-BEAD\s+(?P<pack>{PACKAGE_PATTERN})\s+"
            r"(?P<ohm>[0-9]+(?:\.[0-9]+)?)\s*OHM\s*@?\s*(?P<freq>[0-9]+(?:\.[0-9]+)?\s*(?:MHZ|KHZ))?"
            r".*?(?:±|\+/-)\s*(?P<tol>[0-9]+(?:\.[0-9]+)?)\s*%"
            r".*?(?P<cur>[0-9]+(?:\.[0-9]+)?\s*(?:MA|A))",
            s,
            re.I,
        )
        if not m:
            return None
        freq = re.sub(r"\s+", "", m.group("freq") or "")
        nom = f"{m.group('ohm')}R"
        if freq:
            nom = f"{nom}@{freq.upper()}"
        return _format_inductor_fields(
            {
                "pack": m.group("pack"),
                "nom": nom,
                "current": re.sub(r"\s+", "", m.group("cur")).upper(),
                "%": f"{m.group('tol')}%",
            },
            cfg,
        )
    if "INDUCT" not in up:
        return None
    vm = re.search(r"(?P<value>[0-9]+(?:\.[0-9]+)?\s*(?:UH|NH|MH|H))", s, re.I)
    if not vm:
        return None
    tm = re.search(r"(?:±|\+/-)\s*(?P<tol>[0-9]+(?:\.[0-9]+)?)\s*%", s, re.I)
    cm = re.search(r"(?P<cur>[0-9]+(?:\.[0-9]+)?\s*A)\b", s, re.I)
    return _format_inductor_fields(
        {
            "pack": "",
            "nom": _normalize_value_unit(vm.group("value")),
            "current": re.sub(r"\s+", "", cm.group("cur")).upper() if cm else "",
            "%": f"{tm.group('tol')}%" if tm else "",
        },
        cfg,
    )


def _split_cleaned_segments(cleaned: str, cfg: CleanConfig) -> list[str]:
    text = str(cleaned).strip()
    if not text:
        return []
    if "_" in text:
        return [x for x in text.split("_") if x]
    sep = cfg.output_separator
    if sep and sep != "_" and sep in text:
        return [x for x in text.split(sep) if x]
    return [text]


def _reformat_cleaned_pn(cleaned: str, classify_type: str, cfg: CleanConfig) -> str:
    """
    Vendor parsers return normalized strings but historically with fixed order.
    Re-map recognizable segments to the user-selected template.
    """
    segs = _split_cleaned_segments(cleaned, cfg)
    if not segs:
        return cleaned
    if classify_type == "RESISTOR":
        fields = {"nom": "", "pack": "", "watt": "", "%": ""}
        for seg in segs:
            up = seg.upper()
            if re.match(rf"^({PACKAGE_PATTERN})$", seg, re.I):
                fields["pack"] = seg
            elif re.match(r"^\d+/\d+W$|^\d+(?:\.\d+)?W$", up):
                fields["watt"] = up
            elif "%" in seg:
                fields["%"] = seg
            elif re.match(r"^[0-9.]+(?:R[0-9.]*)?[KM]?$|^[0-9.]+[KM]$", up):
                fields["nom"] = seg
        out = _format_resistor_fields(fields, cfg)
        return out or cleaned
    if classify_type == "CAP":
        fields = {"nom": "", "pack": "", "film": "", "%": "", "W": ""}
        for seg in segs:
            up = seg.upper()
            if re.match(rf"^({PACKAGE_PATTERN})$", seg, re.I):
                fields["pack"] = seg
            elif re.match(r"^[0-9.]+V$", up):
                fields["W"] = up
            elif up in _MLCC_DIELECTRIC or up in ("NP0", "C0G", "COG"):
                fields["film"] = "C0G" if up == "COG" else up
            elif "%" in seg:
                fields["%"] = seg
            elif re.match(r"^[0-9.]+(?:UF|NF|PF|F)$", up):
                fields["nom"] = seg
        out = _format_cap_fields(fields, cfg)
        return out or cleaned
    return cleaned


def _tokenize_bom_spec(spec: str) -> list[str]:
    """
    PnP/CSV often uses '+' between fields; BOM exports from tools may use spaces instead
    (e.g. "RES 1K OHM 1/16W(0402)1%"). If there is no '+', split on whitespace so
    parse_* loops can see separate tokens.
    """
    s = spec.strip()
    if not s:
        return []
    if "+" in s:
        return [p.strip() for p in s.split("+") if p.strip()]
    if re.search(r"\s", s):
        return [p.strip() for p in re.split(r"\s+", s) if p.strip()]
    return [s]


def _normalize_for_regex_parsing(spec: str) -> str:
    """
    Reduce 'MFR/MPN' to bare MPN for token-based regex (mirrors vendor normalization).
    Keeps the full string when the slash is value/voltage (e.g. 15PF/50V) so MLCC lines stay valid.
    """
    s = str(spec).strip()
    s = re.sub(r"<[gG]>\s*$", "", s).strip()
    if "/" not in s:
        return s
    if re.search(
        r"[\d.]+\s*(?:PF|NF|UF|F)\s*/\s*[\d.]+\s*V", s, re.I
    ):
        return s
    # e.g. 1/16W, 1/8W — not "VENDOR/MPN"
    if re.search(r"\b\d+/\d+W\b", s, re.I):
        return s
    return s.split("/")[-1].strip()


_MLCC_DIELECTRIC: Set[str] = {
    "NPO",
    "C0G",
    "COG",
    "X7R",
    "X5R",
    "X6S",
    "X8R",
    "Y5V",
    "Z5U",
}


def _try_parse_mlcc_bom_line(spec: str, cfg: CleanConfig) -> Optional[str]:
    """
    One-line BOM text like: MLCC 15PF/50V (0402) NPO 5% or MLCC 0.1UF/16V(0402)X7R 10%
    (spacing around parens and dielectric may vary).
    """
    s = spec.strip()
    if not re.search(r"\bMLCC\b", s, re.I):
        return None
    vm = re.search(r"([\d.]+)\s*(PF|NF|UF|F)\s*/\s*([\d.]+)\s*V", s, re.I)
    if not vm:
        return None
    value = f"{vm.group(1)}{vm.group(2).upper()}"
    voltage = f"{vm.group(3)}V"
    package = ""
    pm = re.search(r"\((\d{4})\)", s)
    if pm and re.match(rf"^({PACKAGE_PATTERN})$", pm.group(1), re.I):
        package = pm.group(1)
    dielectric = ""
    diel_alts = sorted(_MLCC_DIELECTRIC | {"COG"}, key=len, reverse=True)
    m_stuck = re.search(
        r"\(\d{4}\)\s*(" + "|".join(re.escape(x) for x in diel_alts) + r")\b",
        s,
        re.I,
    )
    if m_stuck:
        cand = m_stuck.group(1).upper()
        dielectric = "C0G" if cand == "COG" else cand
    if not dielectric:
        m_word = re.search(
            r"\b(" + "|".join(sorted(_MLCC_DIELECTRIC, key=len, reverse=True)) + r")\b",
            s,
            re.I,
        )
        if m_word:
            d = m_word.group(1).upper()
            dielectric = "C0G" if d == "COG" else d
    tolerance = ""
    tpf = re.search(r"(0\.\d+)\s*PF\b", s, re.I)
    if tpf:
        tolerance = f"{tpf.group(1)}PF".upper()
    else:
        pcts = re.findall(r"(\d+\.?\d*)\s*%", s)
        if pcts:
            tolerance = f"{pcts[-1]}%"

    result = _format_cap_fields(
        {
            "pack": package,
            "nom": value,
            "W": voltage,
            "film": dielectric,
            "%": tolerance,
        },
        cfg,
    )
    return result if result else None


def parse_capacitor(spec: str, config: Optional[CleanConfig] = None) -> str:
    """Parse capacitor specifications like '22PF+50V+±5%(J)+0402' or '10UF+16V+±10%(K)+0402+X5R'
    
    Format: PACKAGE_VALUE[_VOLTAGE][_DIELECTRIC][_TOLERANCE]
    Example: 0402_1UF_16V_X5R_10%(K)
    """
    cfg = _default_config(config)
    if not cfg.parse_capacitors:
        return str(spec).strip()
    spec = _normalize_for_regex_parsing(str(spec).strip())
    inferit = _parse_inferit_capacitor(spec, cfg)
    if inferit:
        return inferit
    spec = spec.replace("\\", "/").replace("CHIP MLCC CAP.", "").strip()
    mlcc = _try_parse_mlcc_bom_line(spec, cfg)
    if mlcc is not None:
        return mlcc
    parts = _tokenize_bom_spec(spec)
    
    package = ''
    value = ''
    voltage = ''
    dielectric = ''
    tolerance = ''
    
    for part in parts:
        if not part:
            continue
        # Check for package (sizes like 0402, 0603, 0805, etc.)
        if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
            package = part
            continue
        # Check for voltage (digits followed by V, like 16V, 25V, 6.3V)
        if re.match(r'^[\d\.]+V$', part, re.IGNORECASE):
            voltage = part.upper()
            continue
        # Check for dielectric type
        if part.upper() in ['X5R', 'X7R', 'X6S', 'X8R', 'C0G', 'NP0', 'COG', 'Y5V', 'Z5U']:
            dielectric = part.upper()
            continue
        # Check for tolerance with letter code
        if '%' in part and '(' in part:
            tol_match = re.match(r'^[±]?(\d+)%\((\w)\)$', part)
            if tol_match:
                tol, letter = tol_match.groups()
                tolerance = f"{tol}%({letter})"
            continue
        if '%' in part:
            tol = part.replace('%', '').replace('±', '')
            if re.match(r'^[\d\.]+$', tol):
                if tol:
                    tolerance = f"{tol}%"
            continue
        # Check for capacitor value (micro, nano, pico Farad)
        # Must have F at the end or followed by F
        if re.match(r'^[\d\.]+(UF|NF|PF|F)$', part, re.IGNORECASE):
            value = part.upper()
            continue
    
    # Also try to extract from combined values like "16V" or numeric values
    # Looking for patterns like 100UF, 22PF, etc in parts
    if not value:
        for part in parts:
            # Match patterns like 10UF, 22PF, 0.1UF
            match = re.match(r'^([\d\.]+)(UF|NF|PF|F)$', part, re.IGNORECASE)
            if match:
                num, unit = match.groups()
                value = f"{num}{unit.upper()}"
                break
    
    if not package:
        for part in parts:
            if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
                package = part
                break
    
    if cfg.cap_convert_nf_to_uf and value and value.upper().endswith("NF") and "UF" not in value.upper():
        try:
            m = re.match(r"^([\d.]+)NF$", value, re.IGNORECASE)
            if m:
                n = float(m.group(1))
                if n >= 1000 and n % 1000 == 0:
                    value = f"{int(n // 1000)}UF"
                elif n >= 1:
                    value = f"{n / 1000.0}UF".replace(".0UF", "UF")
        except (ValueError, TypeError):
            pass

    result = _format_cap_fields(
        {
            "pack": package,
            "nom": value,
            "W": voltage,
            "film": dielectric,
            "%": tolerance,
        },
        cfg,
    )
    return result if result else spec


def parse_resistor(spec: str, config: Optional[CleanConfig] = None) -> str:
    """Parse resistor specifications like '100R+1/16W+±5%+0402' or '100K+1/16W+±1%+0402'
    
    Format: PACKAGE_VALUE[_TOLERANCE]
    Example: 0402_100_1%
    """
    cfg = _default_config(config)
    if not cfg.parse_resistors:
        return str(spec).strip()
    spec = _normalize_for_regex_parsing(str(spec).strip())
    inferit = _parse_inferit_resistor(spec, cfg)
    if inferit:
        return inferit
    spec = spec.replace("\\", "/").replace("CHIP RES.(THICK FILM)", "").strip()
    parts = _tokenize_bom_spec(spec)

    package = ""
    value = ""
    watt = ""
    tolerance = ""

    for part in parts:
        if not part:
            continue
        # Check for package (sizes like 0402, 0603, 0805, etc.)
        if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
            package = part
            continue
        wm = re.search(r"\b(\d+/\d+W|\d+(?:\.\d+)?W)\b", part, re.IGNORECASE)
        if wm:
            watt = wm.group(1).upper()
        # Check for tolerance with letter code
        if '%' in part and '(' in part:
            tol_match = re.match(r'^[±]?(\d+)%\((\w)\)$', part)
            if tol_match:
                tol, letter = tol_match.groups()
                tolerance = f"{tol}%({letter})"
            continue
        if '%' in part:
            tol = part.replace('%', '').replace('±', '')
            if re.match(r'^[\d\.]+$', tol):
                if tol:
                    tolerance = f"{tol}%"
            continue
        # Check for resistor value patterns (100R, 10K, 1M, etc.)
        if re.match(r'^[\d\.]+[RKM]?$', part, re.IGNORECASE):
            value = part.upper()
            continue
        
        # Also check for part like "33R", "47K", "4.7K" etc.
        if re.match(r'^[\d.]+[RKM]$', part, re.IGNORECASE):
            value = part.upper()
            continue
    
    # Try additional patterns for resistor values
    if not value:
        for part in parts:
            match = re.match(r'^([0-9.]+)(R|KR|MR|M|K|OHM|KOHM|MOHM)$', part, re.IGNORECASE)
            if match:
                num, unit = match.groups()
                unit = unit.upper()
                if unit == 'R':
                    unit = ''
                elif unit == 'KR':
                    unit = 'K'
                elif unit in ['MR', 'MOHM', 'M']:
                    unit = 'M'
                value = f"{num}{unit}" if unit else num
                break
    
    if not package:
        for part in parts:
            if re.match(rf"^({PACKAGE_PATTERN})$", part, re.IGNORECASE):
                package = part
                break
    if not watt:
        for part in parts:
            wm = re.search(r"\b(\d+/\d+W|\d+(?:\.\d+)?W)\b", part, re.IGNORECASE)
            if wm:
                watt = wm.group(1).upper()
                break
    # "1/16W(0402)1%" has package inside parentheses, not a standalone token
    if not package:
        for part in parts:
            m = re.search(r"\((\d{4})\)", part)
            if m and re.match(
                rf"^({PACKAGE_PATTERN})$", m.group(1), re.IGNORECASE
            ):
                package = m.group(1)
                break

    # Trailing e.g. "...1%" on the same token as wattage + (0402)
    if not tolerance:
        for part in parts:
            m = re.search(r"(\d+)%\s*$", part)
            if m:
                tolerance = f"{m.group(1)}%"
                break

    result = _format_resistor_fields(
        {"pack": package, "nom": value, "watt": watt, "%": tolerance},
        cfg,
    )
    return result if result else spec


PACKAGE_PREFIXES = ['SOT', 'TSSOP', 'DFN', 'QFN', 'BGA', 'LGA', 'QFP', 'SOP', 'SOIC', 'DIP', 'TO-', 'SC', 'SMA', 'SMB', 'SMC', 'DO', '2PAD', 'MLP', 'WDFN', 'UDFN']

def clean_other(spec: str) -> str:
    """Clean other component types - extract main part number"""
    spec = spec.strip()
    
    if not spec:
        return ''
    preset_patterns = [
        r"\bPOWER-IC\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bTYPEC\s+IC\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bPCIE\s+[\d.]+\s+QUICK\s+SWITCH\s+IC\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bIC\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bMOSFET(?:\s+(?:N-CHANNEL|P-CHANNEL|SINGLE\s+P-CHANNEL))?\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\b(?:SMD-)?(?:RECTIFIER-|SCHOTTKY-)?DIODE[S]?\s+(?:SCHOTTKY\s+BARRIER\s+DIODE\s+)?(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bESD\s+PROTECTION\s+DIODES?\s+(?P<mpn>[A-Z0-9][A-Z0-9#./_-]{2,})",
        r"\bCRYSTAL\s+(?P<mpn>[0-9]+(?:\.[0-9]+)?\s*(?:MHZ|KHZ))",
        r"\((?P<mpn>[A-Z0-9][A-Z0-9#./_-]{3,})\)",
    ]
    for pat in preset_patterns:
        m = re.search(pat, spec, re.I)
        if m:
            return re.sub(r"\s+", "", m.group("mpn")).upper()
    
    parts = [p.strip() for p in re.split(r'[+]', spec)]
    parts = [p for p in parts if p]
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        is_pkg = any(part.upper().startswith(pkg) or part.upper() in [p.upper() for p in PACKAGE_PREFIXES] for pkg in PACKAGE_PREFIXES)
        if is_pkg:
            continue
        if re.match(r'^[A-Z][A-Z0-9]{2,}[A-Z0-9-]*[A-Z0-9]$', part):
            return part
        if re.match(r'^[A-Z]+[0-9]+[A-Z]*', part) and len(part) > 4:
            return part
    
    if parts:
        for part in reversed(parts):
            part = part.strip()
            if not part:
                continue
            is_pkg = any(part.upper().startswith(pkg) for pkg in PACKAGE_PREFIXES)
            if not is_pkg and len(part) > 2 and re.match(r'^[A-Z0-9]', part):
                return part
    
    return parts[-1] if parts else spec


def parse_inductor(spec: str, config: Optional[CleanConfig] = None) -> str:
    """Parse inductor specifications like '2.2uH+±30%+1.6+3015+FENGHUA+WIRE-WOUND INDUCTOR'"""
    cfg = _default_config(config)
    if not cfg.parse_inductors:
        return str(spec).strip()
    spec = _normalize_for_regex_parsing(str(spec).strip())
    inferit = _parse_inferit_inductor(spec, cfg)
    if inferit:
        return inferit
    spec = spec.replace('\\', '/').strip()
    parts = [p.strip() for p in re.split(r'[+]', spec)]
    
    package = ''
    value = ''
    current = ''
    tolerance = ''
    
    for part in parts:
        if not part:
            continue
        if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
            package = part
        elif 'V' in part.upper() and any(c.isdigit() for c in part) and 'A' not in part.upper():
            continue  # Skip voltage, not current for inductors
        elif 'A' in part.upper() and any(c.isdigit() for c in part):
            current = part.upper().replace(' ', '')
        elif '%' in part:
            tol = part.replace('%', '').replace('±', '')
            if tol and tol != '30':
                tolerance = f"{tol}%"
        elif re.match(r'^[\d\.]+(U|N|P)?H$', part, re.IGNORECASE):
            value = part.upper().replace(' ', '')
    
    if not value:
        for part in parts:
            match = re.match(r'^([\d\.]+)(UH|NH|MH|H)$', part, re.IGNORECASE)
            if match:
                num, unit = match.groups()
                value = f"{num}{unit.upper()}"
                break
    
    if not package:
        for part in parts:
            if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
                package = part
                break
    
    result = _format_inductor_fields(
        {"pack": package, "nom": value, "current": current, "%": tolerance},
        cfg,
    )
    return result if result else spec


def clean_component(
    part_type: str, spec: str, config: Optional[CleanConfig] = None
) -> str:
    """Main cleaning function"""
    if not spec:
        return ''
    
    spec = str(spec).strip()
    
    cfg = _default_config(config)
    if not part_type:
        return clean_other(spec)
    
    part_type = part_type.upper()

    if "RES" in part_type and not cfg.parse_resistors:
        return spec
    if ("CAP" in part_type or "CAPACITOR" in part_type) and not cfg.parse_capacitors:
        return spec
    if ("IND" in part_type or "INDUCTOR" in part_type) and not cfg.parse_inductors:
        return spec

    if "RES" in part_type:
        return parse_resistor(spec, cfg)
    if "CAP" in part_type or "CAPACITOR" in part_type:
        return parse_capacitor(spec, cfg)
    if "IND" in part_type or "INDUCTOR" in part_type:
        return parse_inductor(spec, cfg)
    return clean_other(spec)


def classify_component_type(orig: str) -> str:
    """
    Heuristic part family: INDUCTOR, RESISTOR, CAP, OTHER (same order as clean_preview).
    """
    if not orig:
        return "OTHER"
    t = str(orig).strip()
    t = re.sub(r"\s*<[gG]>\s*$", "", t).strip()
    t = re.sub(r"/\s+", "/", t)
    t = t.upper()
    if re.search(r"\b(CRYSTAL|POWER-IC|TYPEC\s+IC|QUICK\s+SWITCH\s+IC|MOSFET|DIODE|CONNECTOR)\b", t):
        return "OTHER"
    if any(m in t for m in ['UH', 'NH', 'WIRE-WOUND', 'INDUCTOR', 'FERRITE-BEAD']):
        return "INDUCTOR"
    # MPN-shaped capacitors before generic resistor-value heuristics (GRM...104K, etc.)
    if re.search(r"(?:/|^)CL[0-9]{2}[A-Z0-9]", t, re.I) or re.match(
        r"^CL[0-9]{2}[A-Z0-9]", t, re.I
    ):
        return "CAP"
    if re.search(r"(?:/|^)GRM[0-9A-Z]+", t, re.I):
        return "CAP"
    if re.search(r"(?:/|^)(E|J|T|U)MK[0-9]", t, re.I):
        return "CAP"
    if re.search(
        r"(?:/|^)(0201|0402|0603|0805|1206|1210|2010|2512)(B|N|X).",
        t, re.I,
    ):
        return "CAP"
    if "MLCC" not in t and re.search(
        r"/(RC[0-9]{2,4}[A-Z0-9-]*|RT[0-9]{2,4}[A-Z0-9-]*|RM|WR|RB)(?=[A-Z0-9-]|<| |$)", t, re.I
    ):
        return "RESISTOR"
    if "MLCC" not in t and re.match(
        r"^(WR|RM|RB)[0-9]{2}[A-Z0-9-]*", t, re.I
    ):
        return "RESISTOR"
    if "MLCC" not in t and re.match(
        r"^R[CT](0201|0402|0603|0805|1206|1210|2010|2512)(?:[A-Z]{1,2})?-",
        t,
    ):
        return "RESISTOR"
    if "MLCC" not in t and re.search(
        r"[-/][0-9]+(?:\.[0-9]+)?R[0-9](?:<|[A-Z]|[LJ]|$)", t, re.I
    ):
        return "RESISTOR"
    has_wattage = bool(re.search(r'1/\d+W', t))
    has_resistor_value = bool(re.search(r'\d+[RKM](?!\w)', t)) and 'X5R' not in t and 'X7R' not in t
    has_ohm = 'OHM' in t
    if has_wattage or has_resistor_value or has_ohm:
        return "RESISTOR"
    if any(m in t for m in ['UF', 'NF', 'PF', 'X7R', 'X5R', 'COG', 'NPO', 'C0G']) or re.search(
        r"\bMLCC\b", t, re.I
    ):
        return "CAP"
    return "OTHER"


def _type_tag_for_classify(ctype: str) -> str:
    if ctype == "RESISTOR":
        return "RESISTOR"
    if ctype == "CAP":
        return "CAP"
    if ctype == "INDUCTOR":
        return "INDUCTOR"
    return "OTHER"


def _map_classify_to_part_code(ctype: str) -> str:
    if ctype == "INDUCTOR":
        return "IND"
    if ctype == "RESISTOR":
        return "RES"
    if ctype == "CAP":
        return "CAP"
    return "OTHER"


def _ensure_src_on_path() -> None:
    import os
    import sys

    d = os.path.dirname(os.path.abspath(__file__))
    if d not in sys.path:
        sys.path.insert(0, d)


def _try_parse_vendor_pn(
    orig: str, classify_type: str, config: CleanConfig
) -> Optional[str]:
    """
    Run pn_original.parse_pn on the raw line (it normalizes MPN internally).
    Gated by use_pn_codecs (UI: «Part numbers» group), not by use_vendor_pn.
    """
    if not config.use_pn_codecs or classify_type not in ("RESISTOR", "CAP"):
        return None
    if classify_type == "RESISTOR" and not config.parse_resistors:
        return None
    if classify_type == "CAP" and not config.parse_capacitors:
        return None
    ct = "RES" if classify_type == "RESISTOR" else "CAP"
    try:
        _ensure_src_on_path()
        from pn_original import parse_pn

        return parse_pn(orig.strip(), ct, config)
    except Exception as e:
        logger.debug(f"parse_pn failed: {e}")
        return None


def _try_parse_vendor_pn_res_cap_any(
    orig: str, config: CleanConfig, hint: str
) -> Optional[Tuple[str, str]]:
    """
    Run vendor parse_pn: try classifier hint first, then the other, or CAP+RES if OTHER.
    Returns (cleaned, classify_type) or None.
    """
    if not config.use_pn_codecs:
        return None
    if hint in ("RESISTOR", "CAP"):
        order = [hint, "CAP" if hint == "RESISTOR" else "RESISTOR"]
    else:
        order = ["CAP", "RESISTOR"]
    for cls in order:
        out = _try_parse_vendor_pn(orig, cls, config)
        if out:
            return (out, cls)
    return None


def clean_one(
    orig: str, config: Optional[CleanConfig] = None
) -> Tuple[str, str, str, str]:
    """
    One BOM comment → cleaned string, display type, part code, source note.

    Source: '' | 'vendor' | 'pn' | 'library' | 'regex' | 'other' | 'off'
    """
    cfg = _default_config(config)
    if not str(orig).strip():
        return "", "OTHER", "OTHER", ""
    s = str(orig).strip()
    ctype = classify_component_type(s)
    preset_cleaned = None
    if ctype == "RESISTOR" and cfg.parse_resistors:
        preset_cleaned = _parse_inferit_resistor(s, cfg)
    elif ctype == "CAP" and cfg.parse_capacitors:
        preset_cleaned = _parse_inferit_capacitor(s, cfg)
    elif ctype == "INDUCTOR" and cfg.parse_inductors:
        preset_cleaned = _parse_inferit_inductor(s, cfg)
    if preset_cleaned:
        return (
            preset_cleaned,
            _type_tag_for_classify(ctype),
            _map_classify_to_part_code(ctype),
            "regex",
        )
    # Vendor MPN (try classifier hint, then the other for RES/CAP, or CAP+RES for OTHER)
    pnr: Optional[Tuple[str, str]] = None
    if ctype in ("RESISTOR", "CAP", "OTHER"):
        pnr = _try_parse_vendor_pn_res_cap_any(s, cfg, ctype)
    if pnr:
        pnv, eff = pnr[0], pnr[1]
        pnv = _reformat_cleaned_pn(pnv, eff, cfg)
        src = "vendor" if cfg.use_vendor_pn else "pn"
        return pnv, _type_tag_for_classify(eff), _map_classify_to_part_code(eff), src
    lib_entry = None
    if cfg.use_component_library:
        try:
            from component_library import lookup_component

            lib_entry = lookup_component(s)
        except Exception as e:
            logger.debug(f"component library lookup failed: {e}")
    if lib_entry:
        eff = str(lib_entry.type or "OTHER").upper()
        c_eff = (
            "CAP"
            if eff in ("CAP", "CAPACITOR")
            else "RESISTOR"
            if eff in ("RES", "RESISTOR")
            else "INDUCTOR"
            if eff in ("IND", "INDUCTOR")
            else eff
        )
        if c_eff not in ("RESISTOR", "CAP", "INDUCTOR", "OTHER"):
            c_eff = "OTHER"
        cleaned = str(lib_entry.cleaned)
        if c_eff == "RESISTOR":
            cleaned = _apply_prefix(cleaned, cfg.resistor_prefix, cfg)
        elif c_eff == "CAP":
            cleaned = _apply_prefix(cleaned, cfg.cap_prefix, cfg)
        elif c_eff == "INDUCTOR":
            cleaned = _apply_prefix(cleaned, cfg.inductor_prefix, cfg)
        return (
            cleaned,
            _type_tag_for_classify(c_eff),
            _map_classify_to_part_code(c_eff),
            "library",
        )
    if ctype == "RESISTOR" and not cfg.parse_resistors:
        return s, "RESISTOR", "RES", "off"
    if ctype == "CAP" and not cfg.parse_capacitors:
        return s, "CAP", "CAP", "off"
    if ctype == "INDUCTOR" and not cfg.parse_inductors:
        return s, "INDUCTOR", "IND", "off"
    part_code = _map_classify_to_part_code(ctype)
    note = "regex" if ctype in ("RESISTOR", "CAP", "INDUCTOR") else "other"
    return clean_component(part_code, s, cfg), _type_tag_for_classify(ctype), part_code, note


def clean_bom_column(
    comments: list[str], config: Optional[CleanConfig] = None
) -> List[Tuple[str, str, str, str]]:
    """List of (cleaned, type_tag, part_code, vendor_note) per row."""
    return [clean_one(c, config) for c in comments]


def clean_preview(comments: list[str], config: Optional[CleanConfig] = None) -> list[tuple]:
    """
    One row = (#, original, cleaned, type_tag[, vendor]).

    Smart classification with priority markers (see classify_component_type):
    1. IND, 2. RES, 3. CAP, 4. OTHER. MPN decoders (pn_original) when config.use_pn_codecs.
    """
    results = []
    for i, comment in enumerate(comments):
        orig = str(comment) if comment is not None else ""
        if not (orig and str(orig).strip()):
            results.append((i + 1, orig, "", "OTHER", ""))
            continue
        cleaned, type_tag, _pc, vnote = clean_one(orig, config)
        results.append((i + 1, str(orig).strip(), cleaned, type_tag, vnote))
    return results


def clean_bom_dataframe(
    df: "pd.DataFrame", comment_col: str, config: Optional[CleanConfig] = None
) -> "pd.DataFrame":
    """
    Add columns: Comment_cleaned (or {comment_col}_cleaned), clean_type, clean_part_code, clean_vendor.
    """
    import pandas as pd

    if comment_col not in df.columns:
        raise ValueError(f"Column {comment_col!r} not in DataFrame")
    series = [clean_one(x, config) for x in df[comment_col].astype(str).tolist()]
    out = df.copy()
    out[f"{comment_col}_cleaned"] = [r[0] for r in series]
    out["clean_type"] = [r[1] for r in series]
    out["clean_part_code"] = [r[2] for r in series]
    out["clean_vendor"] = [r[3] for r in series]
    return out

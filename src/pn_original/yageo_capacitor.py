"""
Yageo Capacitor PN Parser

Yageo Multi-layer Ceramic Capacitor Series:
CC/CH [Size] [Temp] [Voltage] [Value] [Tolerance]

Examples:
- CC0402KRX7R9BB102 → CAP_0402_1nF_50V_X7R_10%
- CC0603ZRY5V7BB105 → CAP_0603_1uF_16V_Y5V_20%
- CC0805KRX7R7BB104 → CAP_0805_100nF_50V_X7R_10%

Size codes:
0201=0201, 0402=0402, 0603=0603, 0805=0805, 1206=1206

Temp codes:
X7R=X7R, X5R=X5R, X7U=X7U, Y5V=Y5V, Y5U=Y5U, COG=COG

Voltage codes:
R=4V, Q=6.3V, P=10V, L=16V, J=25V, H=50V, E=100V, G=250V

Tolerance:
F=±1%, G=±2%, J=±5%, K=±10%, M=±20%
"""

import re

from ._cap_decode import pf_eia_3_to_str

VENDOR_NAME = "Yageo_CAP"
COMPONENT_TYPES = ["CAP"]
PARSER_PRIORITY = 100


def parse(pn: str, component_type: str) -> str | None:
    """Parse Yageo capacitor PN"""
    if component_type != "CAP":
        return None
        
    pn = re.sub(r"\s*<[gG]>\s*$", "", str(pn).strip())
    pn = re.sub(r"\s+", "", pn).strip().upper()
    
    if not pn.startswith('CC') and not pn.startswith('CH'):
        return None
    
    size_map = {
        '0201': '0201', '0402': '0402', '0603': '0603',
        '0805': '0805', '1206': '1206', '1210': '1210'
    }
    
    temp_map = {
        'X7R': 'X7R', 'X5R': 'X5R', 'X7U': 'X7U',
        'Y5V': 'Y5V', 'Y5U': 'Y5U', 'COG': 'COG', 'NPO': 'NP0'
    }
    
    # Yageo CC/CH: letter codes (and digits before BB) for rated voltage
    voltage_letter = {
        "R": "4V", "Q": "6.3V", "P": "10V", "L": "16V",
        "J": "25V", "H": "50V", "E": "100V", "G": "250V", "A": "250V",
    }
    # Char immediately before "BB" (e.g. ...X7R9BB102, ...X5R5BB226)
    voltage_before_bb = {
        "0": "2.5V", "1": "4V", "2": "5V", "3": "6.3V", "4": "4V",
        "5": "6.3V", "6": "10V", "7": "16V", "8": "25V", "9": "50V",
    }
    
    tol_map = {
        'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%'
    }
    
    try:
        size = size_map.get(pn[2:6], '')
        if not size:
            return None
        
        temp_match = re.search(r'(X[57][RU]|Y[5U]|COG|NPO|X5R|X6S)', pn)
        temp = temp_map.get(temp_match.group(1), '') if temp_match else ''
        if not temp and "X5R" in pn:
            temp = "X5R"

        bbm = re.search(r'([0-9A-Z])BB([0-9]{2,4})', pn, re.I)
        voltage = ""
        if bbm:
            vcode = bbm.group(1).upper()
            voltage = (
                voltage_before_bb.get(vcode, "")
                or voltage_letter.get(vcode, "")
            )
        
        value_match = re.search(r'BB(\d+)', pn)
        value_str = ''
        if value_match:
            raw = value_match.group(1)
            if len(raw) == 3 and raw.isdigit():
                value_str = pf_eia_3_to_str(raw) or ""
            else:
                value = int(raw)
                if value >= 1000:
                    value_str = f"{value // 1000}uF"
                else:
                    value_str = f"{value}pF"
        
        # Tolerance: first spec letter after size (CC + 4-char package) → index 6
        tol = tol_map.get(pn[6], "") if len(pn) > 6 else ""
        if not tol:
            tlm = re.search(r'([FGJKM])(?:[0-9A-Z]*)$', pn, re.I)
            tol = tol_map.get(tlm.group(1), "") if tlm else ""
        
        parts = []
        if size:
            parts.append(size)
        if value_str:
            parts.append(value_str)
        if voltage:
            parts.append(voltage)
        if temp:
            parts.append(temp)
        if tol:
            parts.append(tol)
        
        return '_'.join(parts) if parts else None
        
    except Exception:
        return None


def format_example(pn: str) -> str:
    """Format example of conversion"""
    result = parse(pn, "CAP")
    return f"{pn} → CAP_{result}" if result else f"{pn} → (not recognized)"
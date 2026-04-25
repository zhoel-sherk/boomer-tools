"""
Uniohm Resistor PN Parser

Uniohm Thick Film Chip Resistor Series:
[Size][Wattage][Tolerance][Resistance][TCR][Packaging]

Examples:
- 0603WAF3001T5E → 0603_3K_1%_1/10W
- 0402WGF4701TCE → 0402_4.7K_1%_1/16W
- 0805W8F1001T5E → 0805_1K_1%_1/8W

Note: Same format as Royal Ohm - using same parsing logic.
"""

import re

VENDOR_NAME = "Uniohm"
COMPONENT_TYPES = ["RES"]
PARSER_PRIORITY = 25


def parse_resistance(code: str) -> str:
    """Decode resistance value
    
    3-digit: XXY = XX × 10^Y ohms
    4-digit: XXXY = XXX × 10^Y ohms (E96)
    """
    code = code.upper().strip()
    
    if not code.isdigit():
        return code
    
    if len(code) == 4:
        mantissa = int(code[:3])
        exponent = int(code[3])
    elif len(code) == 3:
        mantissa = int(code[:2])
        exponent = int(code[2])
    else:
        return code
    
    value = mantissa * (10 ** exponent)
    
    if value >= 1000000:
        return f"{value // 1000000}M"
    elif value >= 1000:
        return f"{value // 1000}K"
    else:
        return f"{value}R"


def parse(pn: str, component_type: str) -> str | None:
    """Parse Uniohm resistor PN"""
    if component_type not in COMPONENT_TYPES:
        return None
    
    pn = pn.strip().upper().replace(' ', '')
    
    if not re.match(r'^\d{4}', pn):
        return None
    
    try:
        size = pn[:4]
        remaining = pn[4:]
        
        wattage_map = {
            'WGF': '1/16W', 'WAF': '1/10W', 'W8F': '1/8W',
            'W4F': '1/4W', 'W2F': '1/2W', 'WG': '1/16W',
            'WA': '1/10W', 'W8': '1/8W', 'W4': '1/4W'
        }
        
        wattage = ''
        res_start = 0
        for code, label in wattage_map.items():
            if remaining.startswith(code):
                wattage = label
                res_start = len(code)
                break
        
        if res_start == 0:
            return None
        
        remaining2 = remaining[res_start:]
        
        tol_map = {'F': '1%', 'J': '5%'}
        
        # Check if 3-digit format (resistance + tol at position 3)
        tolerance = ''
        res_code = ''
        
        if len(remaining2) >= 4:
            if remaining2[3] in tol_map:
                tol_char = remaining2[3]
                tolerance = tol_map.get(tol_char, '')
                res_code = remaining2[:3]
        
        # If not 3-digit, check if 4-digit (E96 series, default ±1%)
        if not res_code:
            if len(remaining2) >= 4 and remaining2[:4].isdigit():
                res_code = remaining2[:4]
                tolerance = '1%'
            elif len(remaining2) >= 3:
                res_code = remaining2[:3]
        
        resistance = parse_resistance(res_code) if res_code.isdigit() else ''
        
        parts = []
        if size:
            parts.append(size)
        if resistance:
            parts.append(resistance)
        if tolerance:
            parts.append(tolerance)
        if wattage:
            parts.append(wattage)
        
        return '_'.join(parts) if parts else None
        
    except Exception:
        return None


def format_example(pn: str) -> str:
    result = parse(pn, "RES")
    return f"{pn} → {result}" if result else f"{pn} → (not recognized)"
import re
import logger

# Extended package list for all component types
PACKAGES = ['01005', '0201', '0402', '0603', '0805', '1206', '1210', '1812', '2010', '2220', '2225', '3015', '3020', '3030', '0630', '0730', '1030', '1239', '1340', '1350', '1913', '2135', '2312', '2550', '2759', '3921', '5650', '5850', '5950', '7060', '7640', '1540', '4516', '3812', '3813', '5012', '5013', '5015', '5020', '5025', '5030', '5035', '5040', '5050', '5060', '5125', '5130', '5140', '5155', '5820', '5840', '5850', '6108', '6115', '6120', '6135', '6150', '6155', '6165', '6265', '6330', '7012', '7035', '7040', '7055', '7345', '7355', '8050', '8060', '8250', '8450', '8850']
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
    """Global settings for component cleaning"""
    resistor_include_tolerance = True
    resistor_include_package = True
    resistor_custom_regex = ""
    cap_include_voltage = True
    cap_include_dielectric = True
    cap_custom_regex = ""
    other_custom_regex = ""


def parse_capacitor(spec: str) -> str:
    """Parse capacitor specifications like '22PF+50V+±5%(J)+0402' or '10UF+16V+±10%(K)+0402+X5R'
    
    Format: PACKAGE_VALUE[_VOLTAGE][_DIELECTRIC][_TOLERANCE]
    Example: 0402_1UF_16V_X5R_10%(K)
    """
    spec = spec.replace('\\', '/').replace('CHIP MLCC CAP.', '').strip()
    parts = [p.strip() for p in re.split(r'[+]', spec)]
    
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
                if tol != '5':
                    tolerance = f"{tol}%({letter})"
            continue
        if '%' in part:
            tol = part.replace('%', '').replace('±', '')
            if re.match(r'^[\d\.]+$', tol):
                if tol and tol != '5':
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
    
    result = []
    if package:
        result.append(package)
    if value:
        result.append(value)
    if voltage:
        result.append(voltage)
    if dielectric:
        result.append(dielectric)
    if tolerance:
        result.append(tolerance)
    
    return '_'.join(result) if result else spec


def parse_resistor(spec: str) -> str:
    """Parse resistor specifications like '100R+1/16W+±5%+0402' or '100K+1/16W+±1%+0402'
    
    Format: PACKAGE_VALUE[_TOLERANCE]
    Example: 0402_100_1%
    """
    spec = spec.replace('\\', '/').replace('CHIP RES.(THICK FILM)', '').strip()
    parts = [p.strip() for p in re.split(r'[+]', spec)]
    
    package = ''
    value = ''
    tolerance = ''
    
    for part in parts:
        if not part:
            continue
        # Check for package (sizes like 0402, 0603, 0805, etc.)
        if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
            package = part
            continue
        # Check for tolerance with letter code
        if '%' in part and '(' in part:
            tol_match = re.match(r'^[±]?(\d+)%\((\w)\)$', part)
            if tol_match:
                tol, letter = tol_match.groups()
                if tol != '5':
                    tolerance = f"{tol}%({letter})"
            continue
        if '%' in part:
            tol = part.replace('%', '').replace('±', '')
            if re.match(r'^[\d\.]+$', tol):
                if tol and tol != '5':
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
            if re.match(rf'^({PACKAGE_PATTERN})$', part, re.IGNORECASE):
                package = part
                break
    
    result = []
    if package:
        result.append(package)
    if value:
        result.append(value)
    if tolerance:
        result.append(tolerance)
    
    return '_'.join(result) if result else spec


PACKAGE_PREFIXES = ['SOT', 'TSSOP', 'DFN', 'QFN', 'BGA', 'LGA', 'QFP', 'SOP', 'SOIC', 'DIP', 'TO-', 'SC', 'SMA', 'SMB', 'SMC', 'DO', '2PAD', 'MLP', 'WDFN', 'UDFN']

def clean_other(spec: str) -> str:
    """Clean other component types - extract main part number"""
    spec = spec.strip()
    
    if not spec:
        return ''
    
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


def parse_inductor(spec: str) -> str:
    """Parse inductor specifications like '2.2uH+±30%+1.6+3015+FENGHUA+WIRE-WOUND INDUCTOR'"""
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
    
    result = []
    if package:
        result.append(package)
    if value:
        result.append(value)
    if current:
        result.append(current)
    if tolerance:
        result.append(tolerance)
    
    return '_'.join(result) if result else spec


def clean_component(part_type: str, spec: str) -> str:
    """Main cleaning function"""
    if not spec:
        return ''
    
    spec = str(spec).strip()
    
    if not part_type:
        return clean_other(spec)
    
    part_type = part_type.upper()
    
    if 'RES' in part_type:
        return parse_resistor(spec)
    elif 'CAP' in part_type or 'CAPACITOR' in part_type:
        return parse_capacitor(spec)
    elif 'IND' in part_type or 'INDUCTOR' in part_type:
        return parse_inductor(spec)
    else:
        return clean_other(spec)


def clean_preview(comments: list[str]) -> list[tuple]:
    """
    Smart classification with priority markers:
    1. IND: uH, nH, WIRE-WOUND, INDUCTOR
    2. RES: W (wattage), R/K/M in value (100R, 33K, 1M), OHM  
    3. CAP: uF, nF, pF, X7R, X5R, V (voltage)
    """
    results = []
    for i, comment in enumerate(comments):
        if not comment:
            results.append((i+1, str(comment), "", "OTHER"))
            continue
        
        orig = str(comment).strip()
        t = orig.upper()
        
        # 1. INDUCTOR priority - most specific markers
        if any(m in t for m in ['UH', 'NH', 'WIRE-WOUND', 'INDUCTOR']):
            cleaned = clean_component("IND", orig)
            results.append((i+1, orig, cleaned, "INDUCTOR"))
            continue
        
        # 2. RESISTOR priority:
        # - wattage: 1/16W, 1/10W
        # - value with letter suffix: 100R, 33K, 47K, 4.7K, 1M (NOT part of X5R/X7R)
        has_wattage = bool(re.search(r'1/\d+W', t))
        # matches digit followed by R, K, or M but NOT in X5R, X7R
        has_resistor_value = bool(re.search(r'\d+[RKM](?!\w)', t)) and 'X5R' not in t and 'X7R' not in t
        has_ohm = 'OHM' in t
        
        if has_wattage or has_resistor_value or has_ohm:
            cleaned = clean_component("RES", orig)
            results.append((i+1, orig, cleaned, "RESISTOR"))
            continue
        
        # 3. CAPACITOR markers - uF/nF/pF or dielectric types
        if any(m in t for m in ['UF', 'NF', 'PF', 'X7R', 'X5R', 'COG', 'NPO', 'C0G']):
            cleaned = clean_component("CAP", orig)
            results.append((i+1, orig, cleaned, "CAP"))
            continue
        
        # Fallback to other
        cleaned = clean_component("OTHER", orig)
        results.append((i+1, orig, cleaned, "OTHER"))
    
    return results

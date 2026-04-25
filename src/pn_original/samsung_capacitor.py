"""
Samsung Capacitor PN Parser

Samsung MLCC Part Number Format:
CL[Size][Temp][Voltage][Tolerance][Series][Packaging]

Examples:
- CL05A105MQ5NNNC → CAP_0402_1uF_6.3V_X5R_20%
- CL21B225KOFNNNE → CAP_0805_2.2uF_16V_X7R_10%
- CL31A106KAHNNNE → CAP_1206_10uF_25V_X5R_10%

Size codes:
02=0201, 04=0402, 06=0603, 08=0805, 12=1206, 18=1210

Temp codes:
A=X5R, B=X7R, C=X6S, D=X8R, E=COG(C0G), F=Y5V, G=Y5U, L=X7R(Automotive), R=NP0

Voltage codes:
R=4V, Q=6.3V, P=10V, L=16V, J=25V, H=50V, E=100V, A=250V

Tolerance:
F=±1%, G=±2%, J=±5%, K=±10%, M=±20%
"""

import re

from ._cap_decode import pf_eia_3_to_str

VENDOR_NAME = "Samsung"
COMPONENT_TYPES = ["CAP"]
PARSER_PRIORITY = 95


def parse(pn: str, component_type: str) -> str | None:
    """
    Parse Samsung capacitor PN
    
    Format: CL + Size(2) + Temp(1) + Value(3) + Voltage(1) + Thickness(1) + Tolerance(1) + Series(2) + Packaging(2)
    Example: CL05A105MQ5NNNC
      CL = Multi-layer Ceramic Capacitor
      05 = Size code: 05 -> 0402
      A = Temp code: A -> X5R
      105 = Capacitance: 105 = 1uF (10^5 pF)
      M = Voltage code: M -> 6.3V
      Q = Thickness/Plating
      5 = Tolerance: 5 -> ±20%
      NN = Control code
      NC = Packaging
    
    Value codes (3 digits in pF): 104 = 100nF, 105 = 1uF, 225 = 2.2uF, 106 = 10uF
    """
    if component_type != "CAP":
        return None
        
    pn = re.sub(r"\s*<[gG]>\s*$", "", str(pn).strip())
    pn = re.sub(r"\s+", "", pn).strip().upper()
    
    if not pn.startswith('CL'):
        return None
    
    size_map = {
        '02': '0201', '04': '0402', '05': '0402', '06': '0603', 
        '08': '0805', '10': '0603', '12': '1206', '18': '1210', 
        '21': '0805', '31': '1206', '32': '1210'
    }
    
    temp_map = {
        'A': 'X5R', 'B': 'X7R', 'C': 'X6S', 'D': 'X8R',
        'E': 'COG', 'F': 'Y5V', 'G': 'Y5U', 'L': 'X7R', 'R': 'NP0'
    }
    
    voltage_map = {
        "R": "4V", "Q": "6.3V", "P": "10V", "L": "16V",
        "J": "6.3V", "H": "50V", "E": "100V", "A": "250V",
        "B": "500V", "C": "630V", "M": "6.3V", "K": "10V", "N": "4V", "O": "16V",
    }
    
    tol_map = {
        "F": "1%", "G": "2%", "J": "5%", "K": "10%", "M": "20%",
        "5": "5%", "1": "1%", "2": "2%", "0": "20%",
    }
    
    try:
        if len(pn) < 10:
            return None
        
        # Size: positions 2-3 (CL05 -> 05 = 0402)
        size_code = pn[2:4]
        size = size_map.get(size_code, '')
        
        # Temp: position 4
        temp = temp_map.get(pn[4], '')
        
        # Value: positions 5-7 (EIA 3 digits, pF base)
        value_code = pn[5:8]
        value_str = ""
        if value_code.isdigit() and len(value_code) == 3:
            value_str = pf_eia_3_to_str(value_code) or ""
        
        # Voltage: position 8 (M in CL05A105M...)
        voltage_char = pn[8] if len(pn) > 8 else ''
        voltage = voltage_map.get(voltage_char, '')
        
        # Thickness/Plating: position 9 (not used)
        
        # Tolerance: position 10 (e.g. …KB5: "5" → 5%)
        tol_char = pn[10] if len(pn) > 10 else ""
        tol = tol_map.get(tol_char, "")
        
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
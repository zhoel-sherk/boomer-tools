"""MLCC 3-digit capacitance in pF (EIA) → human-readable string."""


def pf_eia_3_to_str(abc: str) -> str | None:
    """
    3 characters XY Z: value = XY * 10^Z pF.
    e.g. 105 → 1µF, 104 → 100nF, 100 → 10pF.
    """
    if len(abc) != 3 or not abc.isdigit():
        return None
    xy, z = int(abc[0:2]), int(abc[2])
    pf = xy * (10**z)
    if pf < 0:
        return None
    if pf >= 1_000_000_000:  # 1 F+
        u = pf / 1_000_000_000.0
        t = f"{u:.3f}".rstrip("0").rstrip(".")
        return f"{t}F"
    if pf >= 1_000_000:  # µF
        u = pf / 1_000_000.0
        t = f"{u:.3f}".rstrip("0").rstrip(".")
        return f"{t}uF"
    if pf >= 1000:  # nF
        u = pf / 1000.0
        t = f"{u:.3f}".rstrip("0").rstrip(".")
        return f"{t}nF"
    if pf < 0.1:
        return f"{pf}pF"
    return f"{int(pf)}pF" if float(pf) == int(pf) else f"{pf}pF"


def walsin_vol_code_to_v(v: str) -> str:
    """
    Walsin MLCC: 3 digits often encode 50V as 500, 10V as 100 (÷10).
    """
    if not v.isdigit() or not v:
        return ""
    n = int(v)
    if 100 <= n <= 9990 and n % 10 == 0:
        return f"{n // 10}V"
    if 1 <= n <= 500:
        return f"{n}V"
    return f"{n}V"

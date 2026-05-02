"""
Human-readable column titles aligned with Hanwha T-OLP GUI (Part list, Unified Part Editor).

Internal DataFrame column names stay as in MDB / merge rules (e.g. Table__column).
"""

from __future__ import annotations

from typing import Iterable

# PART_Det + enriched profile fields (exact keys).
_KNOWN: dict[str, tuple[str, str]] = {
    "PARTNAME": ("Part Name", "T-OLP «Part» list — unique component id (PART_Det.PARTNAME)."),
    "PROFILENAME": (
        "Profile",
        "Handling/vision profile linked to the part (PART_Det.PROFILENAME → PROFILE_Det).",
    ),
    "PARTDESC": ("Part Description", "Description text (PART_Det.PARTDESC); often version tags like [STDVER.xx]."),
    "CONFIDENCE_LEVEL": ("Confidence / ST", "Numeric flag on part (PART_Det.CONFIDENCE_LEVEL); relates to verification in T-OLP."),
    "USED_MACHINE_SET": ("Machine support", "Bitmask / set of supported machine families (PART_Det.USED_MACHINE_SET)."),
    "VENDORID": ("Vendor ID", "Manufacturer / vendor code (PART_Det.VENDORID)."),
    "PARENTPROFILE": (
        "BASE profile (parent)",
        "Parent/base profile template (PROFILE_Det.PARENTPROFILE) — «Bulk BASE» in editor.",
    ),
    "UPDPARTGROUPID": (
        "Part Group",
        "Component group id (PROFILE_Det.UPDPARTGROUPID) — matches «Part Group» in Unified Part Editor.",
    ),
    "FEEDINGSPEEDLEVEL": (
        "Feeding speed level",
        "Tape feeding speed level (PROFILECOMDATA_Det) — «Feeding Speed» / feeder tuning.",
    ),
    "OVERALL_SPEED_LEVEL": (
        "Overall (Q) speed level",
        "Overall motion speed level (Q_HANDDATA_Det) — Handling speeds family.",
    ),
}

# Common suffixes after Table__ for merged wide columns (substring match on rest).
_SUFFIX_HINTS: tuple[tuple[str, str, str], ...] = (
    ("FEEDINGSPEED", "Feeding speed", "Feeder / tape feeding speed parameter."),
    ("SPEED", "Speed", "Motion or process speed parameter."),
    ("LIGHT", "Lighting", "Vision light / camera illumination."),
    ("VISION", "Vision", "Machine vision / optical parameter."),
    ("HAND", "Handling", "Pick/place / handling timing or motion."),
    ("PICKUP", "Pickup", "Pickup offset or pickup-related."),
    ("PLACE", "Place", "Placement offset or place-related."),
    ("NOZZLE", "Nozzle", "Nozzle type / compatibility."),
    ("POLAR", "Polarity", "Polarity / direction mark."),
    ("DIR_MARK", "Direction mark", "Direction mark for vision."),
    ("THRESHOLD", "Threshold", "Vision threshold."),
    ("DELAY", "Delay", "Time delay (often ms)."),
)


def _merged_parts(name: str) -> tuple[str | None, str | None]:
    if "__" not in name:
        return None, None
    table, col = name.split("__", 1)
    return table, col


def label_and_tooltip_for_column(column_name: str) -> tuple[str, str]:
    """Return (header_label, tooltip_with_technical_name)."""
    if column_name in _KNOWN:
        title, desc = _KNOWN[column_name]
        return title, f"{desc}\n\nMDB column: {column_name}"

    table, rest = _merged_parts(column_name)
    if table is None:
        return column_name, f"MDB column: {column_name}"

    rest_u = rest.upper()
    hint_title = None
    hint_body = None
    for key, title, body in _SUFFIX_HINTS:
        if key in rest_u:
            hint_title = title
            hint_body = body
            break

    if hint_title:
        short_table = table.replace("_Det", "").replace("_", " ")
        label = f"{short_table}: {hint_title}"
        tip = f"{hint_body} Merged from table «{table}», column «{rest}».\n\nMDB column: {column_name}"
        return label, tip

    label = f"{table.replace('_Det', '')}: {rest}"
    tip = f"Merged from table «{table}», column «{rest}».\n\nMDB column: {column_name}"
    return label, tip


def build_column_header_metadata(columns: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Build display name and tooltip maps for all columns."""
    display: dict[str, str] = {}
    tooltips: dict[str, str] = {}
    for c in columns:
        d, t = label_and_tooltip_for_column(str(c))
        display[str(c)] = d
        tooltips[str(c)] = t
    return display, tooltips


def format_column_for_checklist(column_name: str) -> str:
    """Config window: «GUI label — PARTNAME»."""
    label, _ = label_and_tooltip_for_column(column_name)
    if label == column_name:
        return column_name
    return f"{label} — {column_name}"

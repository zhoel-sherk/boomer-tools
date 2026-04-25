"""
PN Original - Vendor-specific part number parsers.

This package contains converters for different manufacturers' part numbers.
Each module should define:
- VENDOR_NAME: str - unique registry key (two modules must not share the same name)
- COMPONENT_TYPES: list[str] - supported types (CAP, RES, IND, etc.)
- parse(pn: str, component_type: str) -> str | None - parse PN to standard format
- PARSER_PRIORITY: int (optional, default 0) - higher runs first in parse_pn
"""

import os
import re
import sys
import importlib

# Add src to path for logger
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

try:
    import logger
except Exception:
    # Fallback if logger not available
    class MockLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
    logger = MockLogger()

CONVERTERS = {}


def load_converters():
    """Load all converter modules from this package"""
    global CONVERTERS

    CONVERTERS.clear()
    converters_dir = os.path.dirname(__file__)
    for filename in sorted(os.listdir(converters_dir)):
        if filename.startswith('_') or not filename.endswith('.py'):
            continue
        if filename == '__init__.py':
            continue
            
        module_name = filename[:-3]
        try:
            module = importlib.import_module(f'pn_original.{module_name}')
            vendor = getattr(module, 'VENDOR_NAME', module_name.upper())
            types = getattr(module, 'COMPONENT_TYPES', [])
            
            CONVERTERS[vendor] = {
                'module': module,
                'types': types
            }
            logger.info("Loaded PN converter: %s %s", vendor, types)
        except Exception as e:
            logger.warning(f"Failed to load converter {module_name}: {e}")


def _normalize_part_number_for_vendors(pn: str) -> str:
    """
    BOM fields are often 'VENDOR/MPN' or 'MFR/RC0603...'; converters expect the bare MPN.
    Strips tags like <G> from the end.
    """
    s = str(pn).strip()
    s = re.sub(r"\s*<[gG]>\s*$", "", s).strip()
    # e.g. TA-I/ RM04… → last segment is parseable (same as "TA-I/RM04…" after this)
    s = re.sub(r"/\s+", "/", s)
    if "/" in s:
        s = s.split("/")[-1].strip()
    return s


def normalize_mpn_bare(pn: str) -> str:
    """Public: bare MPN from «VENDOR/MPN <G>» for web lookup."""
    return _normalize_part_number_for_vendors(pn)


def parse_pn(pn: str, component_type: str, config) -> str | None:
    """
    Parse original PN using vendor-specific converters.
    
    Args:
        pn: Original part number
        component_type: Expected component type (CAP, RES, IND)
        config: CleanConfig instance
    
    Returns:
        Parsed component in standard format, or None if no converter matched
    """
    if not CONVERTERS:
        load_converters()

    s = _normalize_part_number_for_vendors(pn)

    ordered = sorted(
        (
            (vendor, converter)
            for vendor, converter in CONVERTERS.items()
            if component_type in converter["types"]
        ),
        key=lambda vc: -getattr(vc[1]["module"], "PARSER_PRIORITY", 0),
    )

    for vendor, converter in ordered:
        module = converter["module"]
        parse_func = getattr(module, "parse", None)
        if parse_func:
            try:
                result = parse_func(s, component_type)
                if result:
                    logger.debug("Parsed %r -> %r (%s)", pn, result, vendor)
                    return result
            except Exception as e:
                logger.warning(f"Error parsing {pn} with {vendor}: {e}")

    return None


def get_supported_vendors() -> list[str]:
    """Return list of supported vendor names"""
    if not CONVERTERS:
        load_converters()
    return list(CONVERTERS.keys())
"""Bulk edit helpers for enriched part DataFrames."""

from __future__ import annotations

import pandas as pd


def bulk_update_paren_profile(df: pd.DataFrame, old_paren: str, new_paren: str) -> pd.DataFrame:
    """Set ``PARENTPROFILE`` to ``new_paren`` where it currently equals ``old_paren``."""
    out = df.copy()
    if "PARENTPROFILE" not in out.columns:
        return out
    m = out["PARENTPROFILE"].astype(str) == str(old_paren)
    out.loc[m, "PARENTPROFILE"] = new_paren
    return out


def bulk_update_speed_feed(df: pd.DataFrame, profilename: str, new_level: int) -> pd.DataFrame:
    """Set ``FEEDINGSPEEDLEVEL`` for all rows using ``PROFILENAME``."""
    out = df.copy()
    if "FEEDINGSPEEDLEVEL" not in out.columns or "PROFILENAME" not in out.columns:
        return out
    m = out["PROFILENAME"].astype(str) == str(profilename)
    out.loc[m, "FEEDINGSPEEDLEVEL"] = int(new_level)
    return out


def bulk_update_speed_overall(df: pd.DataFrame, profilename: str, new_level: int) -> pd.DataFrame:
    """Set ``OVERALL_SPEED_LEVEL`` for all rows using ``PROFILENAME``."""
    out = df.copy()
    if "OVERALL_SPEED_LEVEL" not in out.columns or "PROFILENAME" not in out.columns:
        return out
    m = out["PROFILENAME"].astype(str) == str(profilename)
    out.loc[m, "OVERALL_SPEED_LEVEL"] = int(new_level)
    return out


def bulk_update_speed_feed_all_matching_paren(df: pd.DataFrame, paren: str, new_level: int) -> pd.DataFrame:
    """Set feeding speed for every row whose ``PARENTPROFILE`` equals ``paren``."""
    out = df.copy()
    if not all(c in out.columns for c in ("PARENTPROFILE", "FEEDINGSPEEDLEVEL")):
        return out
    m = out["PARENTPROFILE"].astype(str) == str(paren)
    out.loc[m, "FEEDINGSPEEDLEVEL"] = int(new_level)
    return out


def bulk_update_speed_overall_all_matching_paren(df: pd.DataFrame, paren: str, new_level: int) -> pd.DataFrame:
    """Set overall Q speed for every row whose ``PARENTPROFILE`` equals ``paren``."""
    out = df.copy()
    if not all(c in out.columns for c in ("PARENTPROFILE", "OVERALL_SPEED_LEVEL")):
        return out
    m = out["PARENTPROFILE"].astype(str) == str(paren)
    out.loc[m, "OVERALL_SPEED_LEVEL"] = int(new_level)
    return out

"""
HTML report from cross-check DataFrame (smt_processor output).

(c) 2023-2026 Mariusz Midor
"""

from __future__ import annotations

import html as html_mod
import time
from pathlib import Path

import pandas as pd

SEVERITY_COLORS: dict[str, str] = {
    "critical": "#c62828",
    "warning": "#f57c00",
    "info": "#1976d2",
}


def result_dataframe_to_html(
    df: pd.DataFrame,
    bom_path: str = "",
    pnp_path: str = "",
) -> str:
    """Build a self-contained HTML fragment (no html/body) for clipboard and viewers."""
    bom_name = Path(bom_path).name if bom_path else "(no BOM file)"
    pnp_name = Path(pnp_path).name if pnp_path else "(no PnP file)"
    out: list[str] = [
        "<h2>Cross-check report</h2>",
        "<p>",
        f"BOM: <b>{html_mod.escape(bom_name)}</b><br/>",
        f"PnP: <b>{html_mod.escape(pnp_name)}</b><br/>",
        f"Generated: <b>{time.strftime('%Y-%m-%d %H:%M:%S')}</b>",
        "</p>",
        (
            "<style>"
            "table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:4px 8px}"
            "th{background:#e8e8e8}"
            "</style>"
        ),
    ]
    if df is None or df.empty:
        out.append("<p><i>Empty result</i></p>")
        return "\n".join(out)

    cols = [str(c) for c in df.columns]
    out.append("<table><thead><tr>")
    for c in cols:
        out.append(f"<th>{html_mod.escape(c)}</th>")
    out.append("</tr></thead><tbody>")

    sev_key = "Severity" if "Severity" in df.columns else None
    for _, row in df.iterrows():
        sev = (str(row[sev_key]).lower() if sev_key is not None else "")
        color = SEVERITY_COLORS.get(sev, "")
        row_style = f' style="background-color:{color}18"' if color else ""
        out.append(f"<tr{row_style}>")
        for c in df.columns:
            v = row[c]
            if isinstance(v, float) and pd.isna(v):
                cell = ""
            else:
                cell = "" if (v is None or (isinstance(v, str) and v.lower() == "nan")) else str(v)
            out.append(f"<td>{html_mod.escape(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def result_dataframe_plain_text(df: pd.DataFrame) -> str:
    """Plain text fallback for clipboard."""
    if df is None or df.empty:
        return ""
    return df.to_string(index=False)

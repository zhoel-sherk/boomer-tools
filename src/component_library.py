"""User component library backed by components.txt.

Backward compatible:
- plain line: MPN_OR_NAME
- structured line: BOOMER_COMPONENT\t{"raw": "...", "cleaned": "...", ...}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Iterable

PREFIX = "BOOMER_COMPONENT\t"


@dataclass(frozen=True)
class ComponentEntry:
    raw: str
    cleaned: str
    type: str = "OTHER"
    footprint: str = ""
    source: str = "components.txt"
    approved_at: str = ""


def default_components_path() -> Path:
    env = os.environ.get("BOOMER_COMPONENTS_TXT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "components.txt"


def normalize_key(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"\s*<[gG]>\s*$", "", s).strip()
    if "/" in s:
        s = s.split("/")[-1].strip()
    s = re.sub(r"\s+", "", s)
    return s.upper()


def _parse_line(line: str) -> ComponentEntry | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith(PREFIX):
        try:
            obj = json.loads(s[len(PREFIX) :])
        except json.JSONDecodeError:
            return None
        raw = str(obj.get("raw") or obj.get("cleaned") or "").strip()
        cleaned = str(obj.get("cleaned") or raw).strip()
        if not raw and not cleaned:
            return None
        return ComponentEntry(
            raw=raw or cleaned,
            cleaned=cleaned or raw,
            type=str(obj.get("type") or "OTHER").upper(),
            footprint=str(obj.get("footprint") or ""),
            source=str(obj.get("source") or "userdb"),
            approved_at=str(obj.get("approved_at") or ""),
        )
    return ComponentEntry(raw=s, cleaned=s, type="OTHER", source="components.txt")


def load_components(path: str | os.PathLike[str] | None = None) -> list[ComponentEntry]:
    p = Path(path) if path is not None else default_components_path()
    if not p.exists():
        return []
    entries: list[ComponentEntry] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = _parse_line(line)
        if entry:
            entries.append(entry)
    return entries


def lookup_component(
    raw: str, path: str | os.PathLike[str] | None = None
) -> ComponentEntry | None:
    key = normalize_key(raw)
    if not key:
        return None
    for entry in load_components(path):
        if key in {normalize_key(entry.raw), normalize_key(entry.cleaned)}:
            return entry
    return None


def append_component(
    raw: str,
    cleaned: str,
    type: str = "OTHER",
    footprint: str = "",
    path: str | os.PathLike[str] | None = None,
) -> bool:
    """Append approved entry. Returns False if an equivalent key already exists."""
    p = Path(path) if path is not None else default_components_path()
    key_candidates = {normalize_key(raw), normalize_key(cleaned)}
    key_candidates.discard("")
    existing = {
        normalize_key(e.raw)
        for e in load_components(p)
    } | {normalize_key(e.cleaned) for e in load_components(p)}
    if key_candidates & existing:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "raw": str(raw).strip(),
        "cleaned": str(cleaned).strip(),
        "type": str(type or "OTHER").upper(),
        "footprint": str(footprint or "").strip(),
        "source": "userdb",
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with p.open("a", encoding="utf-8") as f:
        if p.exists() and p.stat().st_size > 0:
            f.write("\n")
        f.write(PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return True


def entries_to_keys(entries: Iterable[ComponentEntry]) -> set[str]:
    keys: set[str] = set()
    for entry in entries:
        keys.add(normalize_key(entry.raw))
        keys.add(normalize_key(entry.cleaned))
    keys.discard("")
    return keys

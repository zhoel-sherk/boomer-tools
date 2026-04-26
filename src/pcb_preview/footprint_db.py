"""SQLite-backed footprint cache + key normalization (no Qt/pandas)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from pcb_preview.footprint_heuristic import heuristic_footprint_outline
from pcb_preview.kicad_footprint import outline_from_kicad_mod
from pcb_preview.types import BBoxMM, FootprintOutlineMM, PadRectMM, StrokeCircleMM, StrokeLineMM


def default_data_dir(base: Optional[Path] = None) -> Path:
    root = base if base is not None else Path.home() / ".local" / "share" / "Boomer" / "pcb_preview_data"
    (root / "footprints").mkdir(parents=True, exist_ok=True)
    return root


def normalize_footprint_key(name: str) -> str:
    s = (name or "").strip()
    s = s.replace("\\", "/")
    s = re.sub(r"\s+", " ", s)
    return s.lower()


class FootprintStore:
    """
    Stores imported .kicad_mod copies and serialized outlines for fast lookup.

    Resolution order: exact key → normalized key → user aliases (from_key → to_key).
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._root = default_data_dir(data_dir)
        self._db_path = self._root / "footprints.sqlite3"
        self._aliases_path = self._root / "aliases.txt"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS footprints (
                key TEXT PRIMARY KEY,
                norm_key TEXT,
                source_path TEXT,
                sha256 TEXT,
                outline_json TEXT,
                min_x REAL, min_y REAL, max_x REAL, max_y REAL
            )"""
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_norm ON footprints(norm_key)")

    def close(self) -> None:
        self._conn.close()

    def _aliases(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self._aliases_path.is_file():
            return out
        for line in self._aliases_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" in line:
                a, b = line.split("=>", 1)
            elif "\t" in line:
                a, b = line.split("\t", 1)
            else:
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                a, b = parts
            out[normalize_footprint_key(a.strip())] = b.strip()
        return out

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _outline_to_dict(o: FootprintOutlineMM) -> dict[str, Any]:
        return {
            "source": o.source,
            "lines": [l.__dict__ for l in o.lines],
            "circles": [c.__dict__ for c in o.circles],
            "pads": [p.__dict__ for p in o.pads],
            "bbox": o.bbox.__dict__,
        }

    @staticmethod
    def _outline_from_dict(d: dict[str, Any]) -> FootprintOutlineMM:
        lines = tuple(StrokeLineMM(**x) for x in d.get("lines", []))
        circles = tuple(StrokeCircleMM(**x) for x in d.get("circles", []))
        pads = tuple(PadRectMM(**x) for x in d.get("pads", []))
        bb = d.get("bbox", {})
        bbox = BBoxMM(float(bb["min_x"]), float(bb["min_y"]), float(bb["max_x"]), float(bb["max_y"]))
        return FootprintOutlineMM(
            lines=lines,
            circles=circles,
            pads=pads,
            bbox=bbox,
            source=d.get("source", "none"),  # type: ignore[arg-type]
        )

    def import_kicad_mod(self, footprint_key: str, file_path: str) -> tuple[str, ...]:
        """Copy module into cache and store outline. Returns error messages (empty if ok)."""
        src = Path(file_path)
        if not src.is_file():
            return (f"Missing file: {file_path}",)
        key = footprint_key.strip()
        norm = normalize_footprint_key(key)
        sha = self._hash_file(src)
        dest_dir = self._root / "footprints"
        dest = dest_dir / f"{sha[:16]}_{src.name}"
        try:
            dest.write_bytes(src.read_bytes())
        except OSError as e:
            return (f"Copy failed: {e}",)
        outline, errs = outline_from_kicad_mod(str(dest))
        if outline.source == "none" and errs:
            return errs
        blob = json.dumps(self._outline_to_dict(outline))
        bb = outline.bbox
        self._conn.execute(
            """INSERT OR REPLACE INTO footprints
            (key, norm_key, source_path, sha256, outline_json, min_x, min_y, max_x, max_y)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, norm, str(dest), sha, blob, bb.min_x, bb.min_y, bb.max_x, bb.max_y),
        )
        self._conn.commit()
        return errs

    def _row_to_outline(self, row: tuple[Any, ...]) -> FootprintOutlineMM:
        d = json.loads(str(row[0]))
        return self._outline_from_dict(d)

    def lookup_outline(self, footprint_name: str) -> FootprintOutlineMM:
        """Resolve outline: DB → Tier B file on disk heuristic path → Tier A heuristic."""
        raw = (footprint_name or "").strip()
        if not raw:
            return FootprintOutlineMM(source="none")
        aliases = self._aliases()
        chain = [raw]
        nk = normalize_footprint_key(raw)
        if nk in aliases:
            chain.append(aliases[nk])

        for key in chain:
            cur = self._conn.execute(
                "SELECT outline_json FROM footprints WHERE key = ? OR norm_key = ?",
                (key, normalize_footprint_key(key)),
            ).fetchone()
            if cur:
                return self._row_to_outline(cur)

        h = heuristic_footprint_outline(raw)
        if h is not None:
            return h
        return FootprintOutlineMM(source="none")

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Snapshot:
    meta: dict[str, Any]
    dataframe: pd.DataFrame


def source_fingerprint(path: str | os.PathLike[str]) -> dict[str, Any]:
    p = Path(path).expanduser()
    try:
        st = p.stat()
        size = int(st.st_size)
        mtime_ns = int(st.st_mtime_ns)
    except OSError:
        size = -1
        mtime_ns = -1
    return {
        "path": str(p.resolve() if p.exists() else p.absolute()),
        "name": p.name,
        "size": size,
        "mtime_ns": mtime_ns,
    }


def snapshot_key(path: str | os.PathLike[str], kind: str) -> str:
    fp = source_fingerprint(path)
    raw = f"{kind}|{fp['path']}|{fp['size']}|{fp['mtime_ns']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot_paths(
    base_dir: str | os.PathLike[str], path: str | os.PathLike[str], kind: str
) -> tuple[Path, Path]:
    key = snapshot_key(path, kind)
    base = Path(base_dir)
    return base / f"{key}.json", base / f"{key}.pkl"


def save_snapshot(
    dataframe: pd.DataFrame,
    source_path: str | os.PathLike[str],
    kind: str,
    base_dir: str | os.PathLike[str],
    *,
    dirty: bool = True,
    extra: dict[str, Any] | None = None,
) -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    meta_path, data_path = _snapshot_paths(base, source_path, kind)
    tmp_meta = meta_path.with_suffix(".json.tmp")
    tmp_data = data_path.with_suffix(".pkl.tmp")
    meta = {
        "kind": kind,
        "source": source_fingerprint(source_path),
        "dirty": bool(dirty),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "extra": extra or {},
    }
    dataframe.to_pickle(tmp_data)
    tmp_data.replace(data_path)
    tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_meta.replace(meta_path)
    return meta_path


def load_snapshot(meta_path: str | os.PathLike[str]) -> Snapshot:
    mp = Path(meta_path)
    meta = json.loads(mp.read_text(encoding="utf-8"))
    data_path = mp.with_suffix(".pkl")
    df = pd.read_pickle(data_path)
    return Snapshot(meta=meta, dataframe=df)


def find_snapshot(
    source_path: str | os.PathLike[str],
    kind: str,
    base_dir: str | os.PathLike[str],
) -> Snapshot | None:
    base = Path(base_dir)
    if not base.exists():
        return None
    exact_meta, exact_data = _snapshot_paths(base, source_path, kind)
    if exact_meta.exists() and exact_data.exists():
        return load_snapshot(exact_meta)

    fp = source_fingerprint(source_path)
    candidates: list[Path] = []
    for meta_path in base.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("kind") != kind:
            continue
        source = meta.get("source") or {}
        if source.get("path") == fp["path"] and meta_path.with_suffix(".pkl").exists():
            candidates.append(meta_path)
    if not candidates:
        return None
    candidates.sort(
        key=lambda p: json.loads(p.read_text(encoding="utf-8")).get("saved_at", ""),
        reverse=True,
    )
    return load_snapshot(candidates[0])

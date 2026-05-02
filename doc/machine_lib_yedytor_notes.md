# Machine library: Hanwha vs Yamaha — using **yedytor** locally

[yedytor](https://github.com/marmidr/yedytor) (MIT) is a reference desktop app for Yamaha-style libraries (`.Tou`, `DevLibEd*.Lib`). This fork prioritizes **Hanwha/Samsung `UPD.MDB`** (`PART_Det`, profiles, vision tables) via `src/machine_library/` and `src/hanwha_mdb_edit/`.

## Why vendor yedytor next to Boomer

- **Patterns:** UI flows for “pick a library row → edit fields → save” and naming heuristics can inspire the Hanwha editor and future Merge bridges.
- **Not a port:** We do not embed CustomTkinter; reuse ideas and file-format notes only.
- **Yamaha second:** Concrete Yamaha parsers belong in `machine_library/` after Hanwha CSV/ODBC paths are stable.

## Getting the tree

Network permitting:

```bash
cd boomer
git submodule add https://github.com/marmidr/yedytor yedytor
git submodule update --init --recursive
```

If submodules are unavailable, clone into `boomer/yedytor/` manually and keep it **gitignored** or as an unmanaged copy (respect yedytor `LICENSE`).

## Hanwha-specific stack (this repo)

- Read: `mdb-tables` / `mdb-export` (`hanwha_mdbtools.py`).
- Edit: enriched joins + wide merge + `save.py` (CSV sidecars; Windows ODBC optional).
- Recovery: dirty grid snapshots under `AppData/.../autosave/hanwha_mdb/` with the same “Recovered working copy” prompt as BOM/PnP.

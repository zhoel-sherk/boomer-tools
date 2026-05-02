# Boomer Tools — **ALPHA v0.1.0**

Boomer Tools is an active fork of the original Boomer BOM/PnP comparator.

- Fork: [zhoel-sherk/boomer-tools](https://github.com/zhoel-sherk/boomer-tools)
- Upstream: [marmidr/boomer](https://github.com/marmidr/boomer)

The current focus of this fork is a PySide6 desktop application for electronics production workflows: loading BOM and Pick-and-Place files, cleaning component names, cross-checking BOM/PnP consistency, and exporting machine-oriented placement data.

## Current Status

The primary application is now the PySide6 desktop UI:

```bash
python src/app_pyside6.py
```

Legacy desktop entrypoints and web prototypes were removed from this fork. Future web work should be rebuilt on top of shared core services after the desktop workflow is stable.

**ALPHA:** Expect rough edges. The main window shows a **Work in progress** strip; Hanwha MDB edit and PCB Preview are especially experimental. `QSettings` uses organization **`Boomer`** / application **`BoomerTools`** — settings saved under the old **`BoomerPySide6`** app name are **not** migrated.

**UI profiles:** On the Project tab you can pick a **profile** (`default` or cloned names). Checkboxes, combos, and tab options for BOM/PnP (except which file is open), Clean, Merge, Report, and PCB Preview **mirror/units/nudge** are saved into the active profile when you **close the app**. **Loaded BOM/PnP file paths are not restored** after restart (hash-keyed options still apply when you open the same path again). Use **Clear** on the BOM or PnP tab to unload a file from the workspace without changing saved profile defaults.

### PCB Preview (work in progress)

The PySide6 app includes a **PCB Preview** tab: Gerber layers via [gerbonara](https://pypi.org/project/gerbonara/), overlay of the current PnP table, zoom/pan, optional KiCad `.kicad_mod` outlines, placement labels, mirror X/Y, and a mm **nudge** control. This is **Gerber visualization only** — separate from machine-library work below.

### Machine libraries (planned)

Matching cleaned **Merge** output to real pick-and-place **machine component names** will live in a dedicated desktop area, backed by **Qt-free** parsers/services (same split as `src/pcb_preview/`: no business logic stuck in `app_pyside6.py`).

- **Hanwha / Samsung (current focus, WIP):** shop libraries are often **Microsoft Access `.mdb`**. The **Machine lib** tab lists tables and **`PART_Det`** (`PARTNAME`). Separate **Hanwha MDB editor** (`src/hanwha_mdb_edit/`) joins profiles and can autosave/recover edited grids like BOM/PnP. See `doc/hanwha_UPD_mdb_schema.md`, `doc/hanwha_mdb_editor.md`, and `doc/machine_lib_yedytor_notes.md`. Linux: **mdbtools**; Windows: optional **ODBC** / `pyodbc` for in-place updates.

- **Yamaha (second):** `.Tou` and `DevLibEd*.Lib`. Use [yedytor](https://github.com/marmidr/yedytor) (MIT) as a **reference for formats and UX patterns** — vendor a clone under [`yedytor/`](yedytor/README.md) when convenient. Phase 5 details: [TODO.md](TODO.md).

Both vendors should converge on the **same normalized machine-component model** (search, MRU, auto-match, export checks) described in [TODO.md](TODO.md) Phase 5.

The project is actively evolving. See:

- [CHANGELOG.md](CHANGELOG.md) for completed work.
- [TODO.md](TODO.md) for roadmap, known test status, and next tasks.
- [LICENSE](LICENSE) for license terms.

## Features

### BOM / PnP Loading

- Load BOM and PnP files into editable tables; **Clear** unloads the current file from the tab (empty table, mapping cleared).
- Supported formats:
  - `.xls`
  - `.xlsx`
  - `.csv`
  - `.ods`
  - `.txt`
  - `.tab`
- Configure column mappings from the GUI.
- Use `1st` / `Last` row ranges with row-number highlighting.
- Find and replace values directly in BOM/PnP tables.
- Autosave and recover edited working copies.

### Clean BOM

- Normalize component names for SMT workflows.
- Classify and clean:
  - resistors;
  - capacitors;
  - inductors;
  - OTHER parts.
- Decode vendor part numbers before regex fallback.
- Supported parser coverage includes Yageo, Walsin, Murata, TA-I, Taiyo Yuden, Samsung, and INFERIT-style BOM rows.
- Configure output templates for resistor and capacitor fields.
- Configure global separators and optional RES/CAP/IND prefixes.
- Apply cleaned values back to BOM:
  - replace the original source column;
  - or add/update cleaned metadata columns.
- Learn selected OTHER components into `components.txt`.
- Toggle `components.txt` lookup with `From DB`.

### Component Library

`components.txt` is intentionally kept in the repository as the editable user component database/example.

It supports:

- plain-line legacy entries;
- structured entries stored as `BOOMER_COMPONENT\t{json}`;
- duplicate prevention by normalized keys.

You can point the app to another component database with:

```bash
export BOOMER_COMPONENTS_TXT=/path/to/components.txt
```

### Cross-Check / Report

Cross-check BOM and PnP data for:

- BOM refs missing in PnP;
- PnP refs missing in BOM;
- value/comment mismatches;
- exact duplicate coordinates;
- optional placement-distance overlap checks.

### Merge / Machine Export

- Merge BOM values into PnP placement data.
- Delete DNP / missing-from-BOM placements.
- Replace the PnP table with the current Merge result.
- Export full Merge CSV/XLSX files.
- Export layer-specific machine files:
  - `Export Top`
  - `Export Bot`
- Detect layer values such as `None` / `m`, `T` / `B`, or `Top` / `Bottom`.
- Disable bottom export when only one side is detected.

### PCB Preview (WIP)

- Open Gerber files and toggle layer visibility; choose units and zoom to fit.
- Overlay placements from the **PnP** tab; optional footprint geometry from KiCad `.kicad_mod` files (see `requirements.txt` for **kiutils** and its license note).
- Nudge the overlay in millimeters and flip mirror axes when your data uses different conventions.

## Installation

Python 3.10+ is recommended. Use a virtual environment.

```bash
cd boomer
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd boomer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Running

From the repository root:

```bash
cd boomer
python src/app_pyside6.py
```

If you run from inside the `boomer` directory already:

```bash
python src/app_pyside6.py
```

## Typical Workflow

1. Open a BOM file on the BOM tab.
2. Open a PnP/XY file on the PnP tab.
3. Map columns for refs, comments, coordinates, rotation, layer, and footprint.
4. Use Clean BOM to normalize part names.
5. Apply cleaned values back to the BOM.
6. Run Cross-check on the Report tab.
7. Run Merge on the Merge tab.
8. Export full merge output or separate Top/Bot machine files.

## Tests

From the `boomer` directory, activate the venv and run pytest with `PYTHONPATH=src` so imports resolve (`csv_reader`, `cross_check`, …).

```bash
cd boomer
source .venv/bin/activate
export PYTHONPATH=src
python -m pip install -r requirements.txt
```

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` before any PySide6 import so the suite does not require a display (CI / SSH). You can set it explicitly if you run a single Qt test file outside pytest.

Targeted checks used during cleanup:

```bash
python -m pytest \
  tests/test_clean_component.py \
  tests/test_pn_example6.py \
  tests/test_use_vendor_gate.py \
  tests/test_working_copy.py \
  tests/test_smt_processor_formats.py \
  tests/test_duplicate/test_duplicate_coords.py \
  -q
```

Full suite:

```bash
python -m pytest tests -q
```

Last run in project `.venv`: **104 passed, 4 skipped** (counts drift if code/deps change).

### Why tests used to fail

1. **`cross_check.compare`** gained parameters `(min_distance, coord_unit_mils)`; `tests/test_cross_check.py` still called the old two-argument form → `TypeError`.
2. **Grid readers** (`csv` / `xlsx` / `xls` / `ods`) filter rows with `__check_row_valid` (need enough columns and non-empty leading cells). The **fixture files** under `tests/assets/` are small or evolved; expectations such as «12−3 rows» or «skip empty column A» no longer matched actual row counts — assertions were updated to match current files.
3. **example6** supplier BOM (`examples/example6/original_gen3_bom.xlsx`, sheet `abmq601`) was **reshaped** (fewer columns; designator groups live next to «插件位置» in column 5). Tests still read designators from column 8 → empty map and golden mismatch. Helper `_load_example6_abmq601_comment_map()` now follows the new layout.

After aligning tests with the API and fixtures, the full suite should be green in a proper venv (see command above).

Known gaps are listed in [TODO.md](TODO.md) if new failures appear after dependency upgrades.

## Repository Notes

- `requirements.txt` contains the current runtime and test dependencies.
- `.gitignore` excludes Python caches, pytest/coverage output, autosave/recovery snapshots, generated exports, and optional local **`LLM.md`** (AI context — not part of the distributed tree).
- `components.txt` is intentionally tracked.
- Web prototypes were removed; future web UI should be service-backed.

## Development Direction

The intended architecture is core-first:

```text
Files / BOM / PnP
      |
      v
Core services
  - file reading
  - column mapping
  - BOM cleaning
  - vendor PN parsing
  - component library lookup
  - cross-checking
  - merge/export
      |
      +--> PySide6 desktop UI
      +--> CLI / batch jobs
      +--> Future web UI
```

The PySide6 desktop UI remains the primary supported interface for now.

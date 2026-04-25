# Boomer Tools (WIP)

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

The project is actively evolving. See:

- [CHANGELOG.md](CHANGELOG.md) for completed work.
- [TODO.md](TODO.md) for roadmap, known test status, and next tasks.
- [LICENSE](LICENSE) for license terms.

## Features

### BOM / PnP Loading

- Load BOM and PnP files into editable tables.
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

Install dependencies first:

```bash
python -m pip install -r requirements.txt
```

Targeted working-path checks used during the current cleanup:

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

Recent targeted result:

```text
41 passed, 3 skipped, 2 failed
```

The two targeted failures are known `example6` fixture/shape checks. The supplier BOM fixture is currently read as 6 columns while those tests expect column index `8`.

Full suite:

```bash
python -m pytest tests -q
```

Current full-suite status:

```text
64 passed, 4 skipped, 9 failed
```

Known failures are tracked in [TODO.md](TODO.md). They are mostly legacy reader/test expectation mismatches and old `cross_check.compare()` signature assumptions.

## Repository Notes

- `requirements.txt` contains the current runtime and test dependencies.
- `.gitignore` excludes Python caches, pytest/coverage output, autosave/recovery snapshots, and generated exports.
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

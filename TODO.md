# Boomer Tools TODO

This document tracks the current product direction for this fork.

Fork: `zhoel-sherk/boomer-tools`  
Upstream: `marmidr/boomer`

## Product Direction

The main direction is **core-first + PySide6 desktop first**.

Boomer is currently a local production engineering tool. The primary workflow is still desktop-first because the app must:

- open BOM and PnP files from disk;
- display and edit large tables;
- support manual column mapping;
- normalize component names for SMT machines;
- cross-check BOM/PnP consistency;
- merge and export placement data;
- work without a server or internet connection.

The long-term architecture should keep business logic in GUI-independent Python modules, with PySide6, CLI, and any future web UI sharing the same core services.

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

## Current State

### PySide6 Desktop UI

- [x] Project, BOM, PnP, Clean BOM, Merge, and Report tabs exist.
- [x] BOM/PnP tables use pandas-backed Qt table models.
- [x] BOM/PnP tables are editable.
- [x] Column mapping dropdowns are aligned above table columns.
- [x] BOM/PnP `1st` / `Last` row ranges are highlighted in the row-number header.
- [x] BOM/PnP Find/Replace dialogs exist.
- [x] Recent file paths and key settings are stored in `QSettings`.
- [x] Cross-check runs in a background thread.
- [x] Theme toggle exists.

### Clean BOM

- [x] `clean_component.clean_one` integrates vendor PN parsers, regex cleanup, and user component library lookup.
- [x] Source labels distinguish `pn`, `vendor`, `regex`, `library`, `other`, and `off`.
- [x] RES/CAP output templates are configurable by dropdown slots.
- [x] Global separator supports `_`, `-`, space, and custom strings.
- [x] RES/CAP/IND prefixes are supported.
- [x] Prefix formatting can use or skip the global separator.
- [x] Prefixes are applied as the final formatting step.
- [x] `From DB` toggle enables/disables `components.txt` lookup.
- [x] Clean BOM can apply results back to the BOM:
  - replace the source column;
  - or add/update cleaned metadata columns.
- [x] Apply-to-BOM respects the active BOM `1st` / `Last` row range.
- [x] `Learn selected OTHER` can append approved components to `components.txt`.

### Component Library

- [x] `src/component_library.py` exists.
- [x] Plain-line `components.txt` entries remain supported.
- [x] Structured entries use `BOOMER_COMPONENT\t{json}`.
- [x] Learned entries store raw text, cleaned value, type, and footprint.
- [x] Duplicate entries are blocked by normalized keys.

### File Loading / Working Copies

- [x] `.xls`, `.xlsx`, `.csv`, `.ods`, `.txt`, and `.tab` are supported in file dialogs.
- [x] `.xls` uses `xlrd`; `.xlsx` uses `openpyxl`.
- [x] Misleading Excel extensions can fall back to text/CSV parsing.
- [x] Changing row range or separator no longer silently reloads and wipes edits.
- [x] Reload from original asks for confirmation when a working copy is dirty.
- [x] BOM/PnP working copies autosave to app data storage.
- [x] Dirty autosave snapshots can be recovered on startup/file open.
- [x] Recovery no longer crashes when the recovered object is a DataFrame.

### PnP / XY Parsing

- [x] Fixed-width XY lists with standalone mirror markers are parsed correctly.
- [x] Example: `180  m C0402` becomes `Layer=m`, `Footprint=C0402`.
- [x] Auto/fixed-width parsing recognizes simple XY files such as `WMH610M15R110-XY.txt`.

### Merge

- [x] Merge combines BOM values with PnP placement rows.
- [x] `Delete DNP components` removes placement rows whose ref is not present in BOM.
- [x] Ref matching in Merge is case-insensitive.
- [x] `Replace PNP` replaces the PnP tab data with the current Merge result.
- [x] Merge can export full CSV and Excel files.
- [x] Merge has layer-aware exports:
  - `Export Top` + layer dropdown;
  - `Export Bot` + layer dropdown.
- [x] Bot export is disabled for single-sided data or when no useful layer split exists.

### Parser Coverage

- [x] Yageo resistor variants are covered.
- [x] Walsin WR and WW resistor variants are covered.
- [x] TA-I RM dash-value variants are covered.
- [x] Yageo capacitor voltage/tolerance extraction is covered.
- [x] Murata GRM capacitor variants are covered.
- [x] Walsin MLCC variants are covered.
- [x] Taiyo Yuden MLCC variants are covered.
- [x] INFERIT-style RES/CAP/IND/FERRITE-BEAD regex presets are covered.
- [x] OTHER extractors exist for IC, POWER-IC, TYPEC IC, MOSFET, diode/ESD, crystal, and parenthesized MPNs.

### Tests

- [x] Clean BOM parser/template tests exist.
- [x] Vendor PN regression tests exist.
- [x] Component library tests exist.
- [x] Working-copy tests exist.
- [x] Fixed-width/XY parser tests exist.
- [x] Merge DNP behavior tests exist.
- [x] Duplicate-coordinate tests are now real pytest tests.

Recent targeted checks:

- `33 passed` for clean/parser/working-copy focused tests.
- `10 passed, 3 skipped` for duplicate and format-focused tests.
- Changed modules compiled with `py_compile`.
- Linter diagnostics were clean for edited files.

Current full-suite status:

- `python3 -m pytest boomer/tests -q`
- Result: `64 passed, 4 skipped, 9 failed`.

Known full-suite failures to classify/fix:

- `tests/test_clean_component.py`
  - `test_example6_bom_golden_def_bijection`
  - `test_example6_bom_dip_mpn_anchors_in_vendor_comment`
  - Current issue: the example6 supplier BOM fixture is read as 6 columns while these tests expect column index `8`.
- `tests/test_cross_check.py`
  - `test_no_bom`
  - `test_no_pnp`
  - Current issue: tests call old `cross_check.compare()` signature without `min_distance` / `coord_unit_mils`.
- `tests/test_csv_reader.py`
  - `test_csv_comma`
  - `test_csv_spaces`
  - Current issue: expected row counts no longer match current reader behavior.
- `tests/test_ods_reader.py`
  - `test_bom`
  - Current issue: expected column count no longer matches current ODS reader behavior.
- `tests/test_xls_reader.py`
  - `test_bom`
  - Current issue: expected row count no longer matches current XLS reader behavior.
- `tests/test_xlsx_reader.py`
  - `test_bom`
  - Current issue: expected row count no longer matches current XLSX reader behavior.

Full legacy test-suite cleanup is still pending; these failures are recorded separately from the targeted working-path checks.

## Immediate Next Priorities

### 1. GitHub Documentation Prep

- [ ] Rewrite `README.md` for this fork.
- [ ] Clearly explain the relationship:
  - upstream: `marmidr/boomer`;
  - fork: `zhoel-sherk/boomer-tools`.
- [ ] Document the PySide6 app as the primary current UI.
- [ ] Add screenshots or updated UI images for:
  - Project;
  - BOM/PnP mapping;
  - Clean BOM;
  - Merge;
  - Report.
- [ ] Document supported file formats:
  - `.xls`;
  - `.xlsx`;
  - `.csv`;
  - `.ods`;
  - `.txt`;
  - `.tab`.
- [ ] Document basic run commands:
  - create venv;
  - install dependencies;
  - run PySide6 app;
  - run tests.
- [ ] Add a short “Current status” section so users know this is an active fork under development.

### 2. Release Hygiene

- [x] Add dependency manifest:
  - `requirements.txt` for the PySide6 desktop app and tests.
- [x] Remove obsolete desktop UI entrypoints and backup files.
- [x] Remove web/Streamlit/NiceGUI prototypes until a service-backed web UI is needed.
- [x] Review `.gitignore` for generated files:
  - autosave data;
  - keep shared `components.txt` tracked;
  - cache folders;
  - exported reports.
- [ ] Run a full test suite and classify failures:
  - current-regression failures;
  - known legacy failures;
  - obsolete tests to rewrite or remove.

### 3. Real Workflow Validation

- [ ] Run the full desktop workflow on several real projects:
  - load BOM;
  - load PnP;
  - map columns;
  - clean BOM;
  - learn OTHER;
  - apply cleaned values;
  - cross-check;
  - merge;
  - export Top/Bot.
- [ ] Save sample expected outputs for representative projects.
- [ ] Collect remaining `regex` and `OTHER` fallback rows from real BOMs.
- [ ] Promote frequent stable fallbacks to focused parsers or presets.

## Roadmap

### Phase 1 - Stabilize Desktop Product

- [ ] Keep PySide6 as the primary supported interface.
- [ ] Save and restore more session state:
  - window geometry;
  - selected tab;
  - last folders;
  - active column mappings;
  - recent BOM/PnP pairs.
- [ ] Define what a “project” means:
  - recent file pair + settings only;
  - or a saved `.boomer-project.json`.
- [ ] Add a project save/load feature if it materially improves daily workflow.
- [ ] Improve error messages for failed file imports and invalid mappings.

### Phase 2 - Extract a Service Layer

- [ ] Move orchestration out of `src/app_pyside6.py` into GUI-independent services.
- [ ] Candidate modules:
  - `src/services/file_service.py`;
  - `src/services/clean_service.py`;
  - `src/services/check_service.py`;
  - `src/services/merge_service.py`;
  - `src/services/component_db_service.py`.
- [ ] Keep service inputs/outputs simple:
  - dataclasses;
  - pandas DataFrames;
  - plain result objects;
  - no Qt types.
- [ ] Add tests around services before deeply splitting the UI.

### Phase 3 - Clean BOM Coverage

- [ ] Add an unresolved-row export:
  - Original;
  - Cleaned;
  - Type;
  - Source;
  - normalized bare MPN.
- [ ] Add filters in Clean BOM preview:
  - Source;
  - Type;
  - only regex;
  - only OTHER.
- [ ] Continue Murata, Walsin, Yageo, Taiyo, and Samsung parser coverage from real BOM data.
- [ ] Add more conservative OTHER extractors only when backed by real examples.
- [ ] Add tests for every promoted parser/preset.

### Phase 4 - User Parts DB

- [ ] Add bulk import for a user/machine component database.
- [ ] Suggested fields:
  - MPN;
  - aliases;
  - value;
  - canonical name;
  - type;
  - footprint/package;
  - feeder;
  - nozzle;
  - notes.
- [ ] Add `Learn all selected OTHER`.
- [ ] Add a small management dialog:
  - search;
  - edit;
  - delete;
  - deduplicate;
  - export.
- [ ] Consider SQLite when `components.txt` becomes too large or needs safe editing.
- [ ] Keep `components.txt` as import/export format even if SQLite is added.

### Phase 5 - Merge / Machine Export

- [ ] Confirm the final machine-required column names for Top/Bot exports.
- [ ] Add export presets if different machines require different CSV layouts.
- [ ] Decide whether bottom-side mirror notes should be:
  - only UI/log guidance;
  - included in exported filename;
  - included in a sidecar note/report.
- [ ] Add optional coordinate transforms only after a real machine format requires them.

### Phase 6 - PySide6 UI Split

- [ ] Split `src/app_pyside6.py` into smaller UI modules:
  - `ui/main_window.py`;
  - `ui/project_tab.py`;
  - `ui/bom_tab.py`;
  - `ui/pnp_tab.py`;
  - `ui/clean_tab.py`;
  - `ui/merge_tab.py`;
  - `ui/report_tab.py`;
  - `ui/settings.py`.
- [ ] Keep Qt-specific code inside `ui/`.
- [ ] Keep data transformations in services and core modules.
- [ ] Add compact advanced-settings sections for Clean BOM.
- [ ] Add inline output examples for active templates.
- [ ] Add table workflow improvements:
  - copy selected rows;
  - export selected rows;
  - jump from Clean preview row to source BOM row.

### Phase 7 - CLI / Batch Mode

- [ ] Add a CLI entrypoint using the same service layer.
- [ ] Candidate commands:
  - `boomer clean BOM.xlsx --comment-col Comment --out cleaned.xlsx`;
  - `boomer check BOM.xlsx PNP.csv --profile profile.json`;
  - `boomer merge BOM.xlsx PNP.csv --out merge.csv`;
  - `boomer unresolved BOM.xlsx --out unresolved.csv`.
- [ ] Add JSON profile support:
  - file options;
  - separators;
  - first/last rows;
  - column mappings;
  - clean templates;
  - component DB path.
- [ ] Use CLI flows in end-to-end regression tests.

### Phase 8 - Web Later

- [x] Remove current web prototypes from the repository.
- [ ] Do not rebuild web UI until the service layer is stable.
- [ ] If web becomes necessary, build it on shared services.
- [ ] Candidate stack:
  - FastAPI backend;
  - thin frontend;
  - session/project storage;
  - upload/download storage.
- [ ] Required before multi-user web:
  - per-user settings;
  - shared component DB locking;
  - clear export/download flow.

### Phase 9 - Packaging / Distribution

- [ ] Decide supported targets:
  - Linux workstation;
  - Windows workstation;
  - portable bundle later if needed.
- [ ] Document install/run/test commands.
- [ ] Investigate packaging options:
  - PyInstaller;
  - Nuitka;
  - simple venv-based install.
- [ ] Add app icon, version, and About dialog later.

### Phase 10 - Test Suite Cleanup

- [ ] Run full pytest suite.
- [ ] Update obsolete tests that assume old reader behavior.
- [ ] Remove tests that only validate archived UI code.
- [ ] Add targeted tests for:
  - recovery prompt behavior where possible;
  - Merge Replace PNP behavior at service/UI-boundary level;
  - layer dropdown detection logic if extracted from UI;
  - README documented workflows.

## Vocabulary For UI And Docs

Use these names consistently:

- Component Library
- User Parts DB
- Canonical name
- Internal Part Number
- Footprint / Package
- Feeder Library
- Machine Component Library
- Pick-and-Place
- Top side
- Bottom side
- Mirror side

## Status

Boomer Tools is currently an active PySide6 desktop fork focused on real BOM/PnP normalization and SMT machine preparation.

Next priority: update `README.md`, clean up release metadata, validate the full desktop workflow on real projects, and start extracting reusable services from the large PySide6 window module.

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

**Core vs GUI rule:** modules that implement parsing, cleaning, merge, cross-check, file I/O, and machine-library **must not import PySide6** (same spirit as `src/smt_processor.py`, `src/pcb_preview/`, `src/machine_library/`). The main window may orchestrate threads, `QSettings`, and dialogs, but **new business behavior** belongs in core or in thin **GUI-free services** (see Phase 2 and Phase 7), not only in `app_pyside6.py`.

## Current State

### PySide6 Desktop UI

- [x] Project, BOM, PnP, Clean BOM, Merge, and Report tabs exist.
- [x] BOM/PnP tables use pandas-backed Qt table models.
- [x] BOM/PnP tables are editable.
- [x] Column mapping dropdowns are aligned above table columns.
- [x] BOM/PnP `1st` / `Last` row ranges are highlighted in the row-number header.
- [x] BOM/PnP Find/Replace dialogs exist.
- [x] **ALPHA v0.1.0:** `QSettings` uses org **`Boomer`** / application **`BoomerTools`** (new keys; legacy **`BoomerPySide6`** not migrated).
- [x] **ALPHA v0.1.0:** BOM/PnP **separator**, **Has headers**, **1st/Last** rows, and **column mapping** dropdowns persist **per loaded file path** (hash-keyed).
- [x] **Named UI profiles** (`default` + Clone/Delete): theme, language, colorful logs, BOM/PnP load controls + mapping combo values, Merge/Report/Clean/PCB Preview (widget prefs only) stored as JSON per profile; snapshot saved on app close for the **active** profile.
- [x] **Clear** on BOM/PnP tabs unloads workspace (table + mapping); does not delete profile data.
- [x] Theme, Clean BOM, merge/report overlap, PnP units, and related flat keys remain compatible with legacy fallback load where no profile JSON exists.
- [ ] **Last-opened BOM/PnP paths** are intentionally **not** persisted (`files/last_*` removed); optional future **project file** or persisted MRU for pairs (see Phase 1).
- [x] Main window shows an **ALPHA / WIP** banner; Hanwha MDB editor uses autosave + “Recovered working copy” like BOM/PnP (`hanwha_mdb` snapshots).
- [x] Cross-check runs in a background thread.
- [x] Theme toggle exists.

### PCB Preview (WIP)

- [x] **PCB Preview** tab in PySide6 (`src/pcb_preview_tab.py`, `src/pcb_preview/`, bridge from current PnP table).
- [x] Gerber stack: load layers, visibility, units (Auto/mm/inch scale), wheel zoom, Fit all, higher raster DPI (gerbonara → SVG).
- [x] PnP overlay on Gerber: centroids, optional `.kicad_mod` outlines (kiutils), ref labels, mirror X/Y, mm **nudge** in sidebar.
- [x] PCB Preview **widget** prefs (mirror X/Y, Gerber unit mode, nudge step) persist via **active UI profile** JSON (no Gerber file paths).
- [ ] Persist **last Gerber folder / open layer paths** in `QSettings` or defer explicitly.
- [ ] Revisit automated 2-point Gerber↔PnP alignment (currently commented in favor of manual nudge).
- [ ] Add focused tests and small Gerber/PnP fixtures for the Qt-free preview core.

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

Current full-suite status (see also `README.md`; re-run after dependency/code changes):

- `cd boomer && export PYTHONPATH=src && python -m pytest tests -q`
- Last documented run in project `.venv`: **`104 passed, 4 skipped`** (counts drift if fixtures/API change).

Earlier snapshot (before reader/test alignment): **`64 passed, 4 skipped, 9 failed`** — concentrated in example6 column expectations, `cross_check.compare` signature, and grid reader row/column counts. Re-run the suite after changes; if failures return, list failing nodes here again.

Full legacy test-suite cleanup remains an ongoing hygiene task.

### Yedytor / Yamaha (concrete integration steps)

Reference: [yedytor](https://github.com/marmidr/yedytor) (MIT) — parsers and matching ideas for Yamaha `.Tou`, `DevLibEd*.Lib`, and spreadsheet PnP import; **not** a port of its CustomTkinter UI. Full machine-library goals and row-status semantics remain in **Phase 5** below; this list is sequencing only.

- [ ] Add a **Qt-free** machine-library package or module (same separation style as `src/pcb_preview/`): load `.Tou` / `DevLibEd*.Lib`, normalized search records, no PySide6 imports in the parser core.
- [ ] Add minimal sanitized fixtures and unit tests for Tou/Lib parsing before wiring UI.
- [ ] Register a PySide6 **Machine library / Yamaha** tab or subpanel from `src/app_pyside6.py` (alongside PCB Preview), calling only the service layer.
- [ ] Bridge **Merge** / PnP `DataFrame` into that UI (line status, MRU, auto-match by footprint + comment — align with Phase 5 bullets).
- [ ] When exporting, reuse strict validation ideas from yedytor (warn/block on unresolved rows) once matching columns exist in Merge.

## Immediate Next Priorities

### 1. GitHub Documentation Prep

- [x] `README.md` describes this fork, upstream vs fork, PySide6 as primary UI, formats, install/run, tests, and current ALPHA status (iterate as features land).
- [ ] Add screenshots or updated UI images for:
  - Project (incl. profiles);
  - BOM/PnP mapping;
  - Clean BOM;
  - Merge;
  - Report.

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
- [ ] Collect real machine-library files for matching research:
  - Yamaha `.Tou` / `DevLibEd.Lib` examples from `marmidr/yedytor`;
  - Hanwha: **local production sample `UPD.MDB`** (keep outside Git; derive a tiny sanitized fixture or CSV exports for tests only).

## Performance (profiling-driven)

Do not optimize blindly: run a profiler on slow user paths (large XLSX open, merge, cross-check, autosave) and confirm bottlenecks. Prioritized ideas (low effort → high impact first):

1. **Pandas row iteration** — replace `DataFrame.iterrows()` with `itertuples()` or per-column numpy/Series iteration in hot paths (`src/smt_processor.py` merge/cross-check, `src/hanwha_mdb_edit/core/save.py`, `src/hanwha_mdb_edit/core/part_det_repository.py`, `src/report_html.py`). No new dependencies; high payoff on large PnP tables.
2. **Excel read** — optional **`python-calamine`** engine for `.xlsx`/`.xls` in `_read_excel` (`smt_processor.py`): much faster reads; requires regression tests (Chinese BOM `header=3` heuristic, misleading “Excel” files that fall back to CSV). ODS stays on `odf`; calamine is read-only.
3. **Excel write** — for very large merge exports, optional **`XlsxWriter`** path instead of `df.to_excel(..., engine="openpyxl")` (`export_excel`): faster writes; not a drop-in (explicit sheet write loop).
4. **Working-copy snapshots** — optional **Parquet (`pyarrow`)** alongside or instead of pickle in `src/working_copy.py` for large tables: smaller/faster I/O; watch `object` columns and migrate old `.pkl` keys on load.

Optional hygiene: **`orjson`** for snapshot JSON metadata if profiling shows significant time there.

## Roadmap

### Phase 1 - Stabilize Desktop Product

- [ ] Keep PySide6 as the primary supported interface.
- [ ] Save and restore more session state:
  - window geometry;
  - selected tab;
  - last folders (file dialogs / Gerber);
  - ~~active column mappings~~ — **partially done:** per-file hash prefs + profile JSON for BOM/PnP combo values;
  - recent BOM/PnP pairs (persisted project or explicit MRU — not only in-memory).
- [ ] Define what a “project” means:
  - recent file pair + settings only;
  - or a saved `.boomer-project.json`.
- [ ] Add a project save/load feature if it materially improves daily workflow.
- [ ] Improve error messages for failed file imports and invalid mappings.

### Phase 2 - Extract a Service Layer

- [ ] Move orchestration out of `src/app_pyside6.py` into GUI-independent services (a thin **facade** is enough at first: one module that builds `ColumnConfig` / `ProcessorConfig` / `SMTDataProcessor` from plain values and exposes `run_cross_check`, `run_merge`, etc., so `MainWindow` only reads widgets → calls facade → updates models).
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
- [ ] Optional later: CI guard (e.g. script or `grep`) that fails if `PySide6` appears in agreed core paths (`smt_processor.py`, `clean_component.py`, `pcb_preview/`, `machine_library/`, `services/`).
- [ ] Cross-reference **Performance (profiling-driven)** when services own Excel I/O and large table loops.

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

### Phase 5 - Machine Library Matching

Goal: turn Clean BOM + Merge output into machine-ready component names by matching cleaned component values and footprints against real pick-and-place machine libraries.

For implementation order (fixtures → service → tab → DataFrame bridge), see **Yedytor / Yamaha (concrete integration steps)** under *Current State* above.

Useful reference:

- `marmidr/yedytor` is a related Yamaha PnP editor by the upstream author.
- Its useful ideas are domain logic, not the old `customtkinter` UI:
  - Yamaha `.Tou` reader;
  - Yamaha `DevLibEd.Lib` / `DevLibEd2.Lib` reader;
  - component DB with aliases and hidden entries;
  - Most Recently Used selections per search filter;
  - auto-match by `footprint + comment`;
  - row status markers such as no-match, filtered, auto-selected, manually-selected, removed;
  - block or warn before export when unresolved rows remain.

Planned machine-library support:

- [ ] Add a GUI-independent machine library service.
- [ ] Define a normalized machine component record:
  - machine type/vendor;
  - source file path;
  - raw machine component name;
  - normalized canonical name;
  - aliases;
  - package/footprint;
  - value/comment tokens;
  - hidden/disabled flag;
  - optional feeder/nozzle fields when available.
- [ ] Add Yamaha import:
  - `.Tou`;
  - `DevLibEd.Lib`;
  - `DevLibEd2.Lib`.
- [x] Inspect sample `UPD.MDB`: schema notes in `doc/hanwha_UPD_mdb_schema.md`; **`PART_Det` → `PARTNAME`** is the machine library string; Qt-free reader `src/machine_library/hanwha_mdbtools.py` + **Machine lib** tab (WIP).
- [ ] Add Hanwha import backed by a **sanitized** fixture (never commit full proprietary `.mdb`).
- [ ] Research Hanwha `.mdb` access options:
  - `pyodbc` / Access ODBC on Windows;
  - `mdbtools` on Linux;
  - export-to-CSV fallback if direct DB access is unreliable.
- [ ] Add tests using small sanitized sample machine-library fixtures.
- [ ] Add auto-match candidates using:
  - cleaned BOM value;
  - PnP footprint/package;
  - raw BOM comment;
  - aliases;
  - recent manual selections.
- [ ] Add row status for machine matching:
  - no match;
  - candidate/filter match;
  - auto-selected;
  - manually-selected;
  - removed/DNP.
- [ ] Add MRU ranking so repeated manual choices appear first for the same filter.
- [ ] Add optional strict export validation:
  - warn or block export if unresolved machine component names remain.
- [ ] Decide where machine-selected names appear:
  - extra Merge columns;
  - replacement PnP component column;
  - separate machine export profile.

### Phase 6 - Merge / Machine Export

- [ ] Confirm the final machine-required column names for Top/Bot exports.
- [ ] Add export presets if different machines require different CSV layouts.
- [ ] Decide whether bottom-side mirror notes should be:
  - only UI/log guidance;
  - included in exported filename;
  - included in a sidecar note/report.
- [ ] Add optional coordinate transforms only after a real machine format requires them.
- [ ] Add machine export profiles once Yamaha and Hanwha component matching are stable.

### Phase 7 - PySide6 UI Split

- [ ] Split `src/app_pyside6.py` into smaller UI modules under `src/ui/` (or `src/gui/` — pick one name and keep imports consistent):
  - `ui/main_window.py`;
  - `ui/project_tab.py`;
  - `ui/bom_tab.py`;
  - `ui/pnp_tab.py`;
  - `ui/clean_tab.py`;
  - `ui/merge_tab.py`;
  - `ui/report_tab.py`;
  - `ui/settings.py`;
  - optional `ui/threads.py` for `QThread` workers (e.g. cross-check).
- [ ] Keep Qt-specific code inside `ui/` (or `gui/`).
- [ ] Keep data transformations in services and core modules.
- [ ] Add compact advanced-settings sections for Clean BOM.
- [ ] Add inline output examples for active templates.
- [ ] Add table workflow improvements:
  - copy selected rows;
  - export selected rows;
  - jump from Clean preview row to source BOM row.

### Phase 8 - CLI / Batch Mode

- [ ] Add a CLI entrypoint using the same service layer.
- [ ] Candidate commands:
  - `boomer clean BOM.xlsx --comment-col Comment --out cleaned.xlsx`;
  - `boomer check BOM.xlsx PNP.csv --profile profile.json`;
  - `boomer merge BOM.xlsx PNP.csv --out merge.csv`;
  - `boomer machine-match BOM.xlsx PNP.csv --machine-db machine.json --out merge.csv`;
  - `boomer unresolved BOM.xlsx --out unresolved.csv`.
- [ ] Add JSON profile support:
  - file options;
  - separators;
  - first/last rows;
  - column mappings;
  - clean templates;
  - component DB path.
- [ ] Add machine-library profile fields:
  - machine vendor;
  - machine DB path;
  - strict unresolved-row policy;
  - export profile.
- [ ] Use CLI flows in end-to-end regression tests.

### Phase 9 - Web Later

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

### Phase 10 - Packaging / Distribution

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

### Phase 11 - Test Suite Cleanup

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
- Machine Library Matching
- Machine Component Name
- Yamaha `.Tou`
- Yamaha `DevLibEd.Lib`
- Hanwha `.mdb`
- Pick-and-Place
- Top side
- Bottom side
- Mirror side

## Status

Boomer Tools is currently an active PySide6 desktop fork focused on real BOM/PnP normalization and SMT machine preparation.

Next priority: update `README.md`, clean up release metadata, validate the full desktop workflow on real projects, extract a **GUI-free service/facade layer** from `app_pyside6.py`, and apply **profiling-driven** performance work from **Performance (profiling-driven)** where real bottlenecks show up.

# Changelog

All notable changes for this fork are tracked here.

Fork: `zhoel-sherk/boomer-tools`  
Upstream: `marmidr/boomer`

## ALPHA v0.1.0 — 2026-05-01

### Branding and lifecycle

- Desktop app display name **Boomer Tools**; window title includes **ALPHA v0.1.0**.
- **QSettings** application key is now **`BoomerTools`** (organization **Boomer**). Earlier **`BoomerPySide6`** entries are not migrated — settings reset once for ALPHA testers.
- Yellow **Work in progress** banner on the main window; Hanwha MDB sub-windows tagged **(WIP)** in titles.

### BOM / PnP persistence

- Per **loaded file path** (stable hash), persist BOM/PnP tab: separator, **Has headers**, **1st** / **Last** row, and **per-column mapping** dropdown values (`bom/ui/<hash>/…`, `pnp/ui/<hash>/…`).
- Restored **before** reloading from disk when opening a known path (skipped when loading a recovered pickle snapshot).

### Recovery UX

- **`working_copy_ui.prompt_recover_snapshot`** centralizes the “Recovered working copy found” dialog (BOM/PnP unchanged behaviour).
- **Hanwha MDB editor:** debounced autosave of the enriched grid under `…/autosave/hanwha_mdb/` (`kind=hanwha_mdb`); same recovery prompt on open; **Reload** forces fresh read from `.mdb` (skips recovery prompt intent).

### Code hygiene

- Russian comments/docstrings in `src/**/*.py` translated to English (incl. `smt_processor.py`, `qt_models.py`, `pcb_preview_tab.py`, and other modules touched in that sweep).
- New helpers: [`src/settings_paths.py`](src/settings_paths.py), [`src/working_copy_ui.py`](src/working_copy_ui.py).
- Tests: [`tests/test_settings_paths.py`](tests/test_settings_paths.py), [`tests/test_qsettings_bom_pnp_persist.py`](tests/test_qsettings_bom_pnp_persist.py), [`tests/test_working_copy_ui.py`](tests/test_working_copy_ui.py).

### Reference vendoring

- **`yedytor/`** placeholder + [`doc/machine_lib_yedytor_notes.md`](doc/machine_lib_yedytor_notes.md): Hanwha-first machine_lib direction; Yamaha/yedytor patterns second. Submodule `git submodule add` when GitHub is reachable.

## Unreleased - 2026-04-25

### GUI profiles and workspace clearing (2026-04-26)

- **Named UI profiles** on the Project tab (`default` plus **Clone…** / **Delete**): each profile stores a JSON snapshot under `profiles/<name>/state_json` in `QSettings` — theme, language, colorful logs, BOM/PnP load controls and **column mapping combo values** (not loaded file paths), Merge **Delete DNP**, Report severity/overlap toggles, Clean BOM preferences, and PCB Preview UI prefs (mirror, Gerber unit mode, nudge step — still **no** persisted Gerber layer paths).
- **On quit**, the **active** profile is saved; legacy **`files/last_bom`** / **`files/last_pnp`** keys are cleared and no longer written when loading files — **last-opened paths are not restored** across sessions (per-path hash settings for BOM/PnP tabs still apply when you reopen the same file).
- **Clear** on the BOM and PnP tabs unloads the table and mapping widgets (workspace only).
- **i18n:** `boomer/lang/en.json` and `boomer/lang/ru.json` extended for profile dialogs and Clear actions.
- **Fix:** `_load_legacy_settings_flat` indentation bug that caused `IndentationError` at startup.

### Removed unused `src/` modules

- Deleted **`profile_settings.py`** and **`qt_header_mapper.py`** (no imports from the app or tests; BOM/PnP column mapping is handled in **`app_pyside6.py`**).
- **Audit:** `bom_clean.py`, **`project.py`** (boomer `src/`, distinct from **`yedytor/src/project.py`**), **`report_generator.py`**, and unused **`src/themes/`** were already absent from the tree and had no remaining code references — consolidated note here for clarity.
- **`README.md`** / **`TODO.md`:** no stale mentions. **`LLM.md`** updated to match the current report stack (**`report_html.py`** only).

### Documentation and roadmap (2026-05-02)

- **`TODO.md`:** Explicit **core vs GUI** rule (no `PySide6` in parsing/merge/check paths); new **Performance (profiling-driven)** backlog (pandas hot paths, optional calamine / XlsxWriter / Parquet, profile before optimizing); Phase 2 extended with a thin **facade** and optional CI guard on core imports; Phase 7 documents `src/ui/` vs `src/gui/` and optional `threads` module; Status footer points at service extraction and perf work.
- **`LLM.md`:** Expanded **Architecture Snapshot** (core vs presentation, what “fully separate” means, facade and UI file split, performance pointer to `TODO.md`); entrypoint note that `app_pyside6.py` should shrink to wiring; **Guidance For Future AI Work** updated (no Qt in listed core packages, optimization order).

### Machine library (Hanwha UPD .mdb, WIP)

- Qt-free reader **`src/machine_library/hanwha_mdbtools.py`**: lists tables, exports a table via `mdb-export`, parses **`PART_Det`** → `PARTNAME` / profile / description (requires **mdbtools** on `PATH`).
- New tab **Machine lib**: open `.mdb`, show table list summary and **PART_Det** in a read-only table (`machine_library_tab.py`).
- **Hanwha MDB editor** (`src/hanwha_mdb_edit/`): Join **PART_Det** with **PROFILE_Det** (PARENTPROFILE / BASE, UPDPARTGROUPID), **PROFILECOMDATA_Det** (FEEDINGSPEEDLEVEL), **Q_HANDDATA_Det** (OVERALL_SPEED_LEVEL); **PART_Det** includes **VENDORID**. Bulk dialogs for base profile and speed levels; save emits four CSV sidecars + optional Windows ODBC updates.
- Tests: `tests/test_hanwha_mdbtools.py` + fixture `tests/fixtures/hanwha_PART_Det_sample.csv`; optional integration tests when `UPD.MDB` sits next to the `boomer/` folder.
- Doc: `doc/hanwha_UPD_mdb_schema.md`, `doc/hanwha_mdb_editor.md`.

### Summary

This cycle turned the PySide6 version into the primary working desktop app for real BOM/PnP cleanup:

- Clean BOM now supports vendor PN decoding, configurable component naming, prefixes, learned user components, and direct apply-back workflows.
- BOM/PnP tables are editable working copies with autosave/recovery.
- Real INFERIT BOM and XY files are handled more reliably.
- Merge gained DNP filtering, PnP replacement, and layer-aware Top/Bot exports.
- Tests were expanded around the new parser, merge, file-reader, working-copy, and duplicate-coordinate behavior.

### PCB Preview (WIP)

- Added **PCB Preview** tab: Gerber layers via [gerbonara](https://pypi.org/project/gerbonara/) (SVG rasterized in-scene), PnP overlay from the current PnP table (`pcb_preview_bridge`, `src/pcb_preview/`).
- Gerber: multiple layers, visibility toggles, units hint (Auto / mm / optional inch→mm scale), higher raster DPI for sharper preview, smooth pixmap scaling.
- PnP: footprint outlines from optional `.kicad_mod` import ([kiutils](https://github.com/hvr/kicad-parser) — see `requirements.txt` GPL note), centroid + X-cross markers, larger ref labels, mirror X/Y, compact **nudge** control (mm step) in the left sidebar, wheel zoom, Fit all.
- Automated 2-point Gerber↔PnP alignment UI is temporarily disabled in favor of manual nudge; can be re-enabled from commented blocks in `pcb_preview_tab.py`.

### BOM / PnP table editing

- Fixed crashes when editing numeric cells in BOM/PnP (and Clean preview) tables: Qt commits **strings** from editors while pandas columns are `int64`/`float64`. `PandasTableModel.setData` now coerces values through `_coerce_edit_value_for_dataframe` in `src/qt_models.py`.

### Dependencies

- Declared `gerbonara` and `kiutils` in `requirements.txt` for PCB preview (Gerber + optional KiCad footprint import).

### Clean BOM

- Added template-based output formatting through `CleanConfig`.
- Added resistor template fields: `nom`, `pack`, `watt`, `%`.
- Added capacitor template fields: `nom`, `pack`, `film`, `%`, `W`.
- Kept global spacer support for `_`, `-`, space, and custom separators.
- Added optional prefixes for basic components:
  - resistor prefix;
  - capacitor prefix;
  - inductor prefix.
- Added `Use spacer after Prefix` so prefixes can be emitted as `C0402-12pF` or `C-0402-12pF`.
- Applied prefixes as the final formatting step so they do not interfere with parsing.
- Added `From DB` toggle to enable or disable `components.txt` lookup.
- Added `Replace source column` mode for applying Clean BOM output back into the original BOM column.
- Kept add-column mode for generating `*_cleaned`, `clean_type`, `clean_part_code`, and `clean_vendor`.
- Made Apply-to-BOM respect the active BOM `1st` / `Last` row range.
- Added editable BOM table cells for manual corrections.
- Added `Find / Replace...` dialogs for BOM and PnP tables.
- Added active row-number highlighting for the BOM/PnP `1st` / `Last` range.

### User Component Library

- Added `src/component_library.py`.
- Added backward-compatible `components.txt` support:
  - plain text lines are treated as OTHER components;
  - structured entries are stored as `BOOMER_COMPONENT\t{json}`.
- Added `Learn selected OTHER` workflow in Clean BOM.
- Added duplicate prevention based on normalized raw/cleaned keys.
- Added tests for plain and structured component library entries.

### Vendor Part Number Parsers

- Integrated `pn_original` decoders into `clean_component.clean_one`.
- Run PN decoders before regex fallback.
- Try alternate CAP/RES decoder order when classification is ambiguous.
- Preserve Source values: `pn`, `vendor`, `regex`, `library`, `other`, `off`.
- Reformat vendor PN outputs through the same user-selected templates as regex outputs.

#### Resistors

- Fixed Yageo RC/RT resistor value extraction so value comes from the MPN tail after `-`.
- Added Yageo cases:
  - `RC0402-JR-07510RL` -> `0402_51R_5%`;
  - `RC0402-JR-0775RL` -> `0402_75R_5%`;
  - `RC0402FR-0749K9L` -> `0402_49.9K_1%`;
  - `RC0402FR-076K49L (PC335)` -> `0402_6.49K_1%`.
- Expanded Walsin WR parsing:
  - `WR08X000PTL` -> `0805_0R_5%`;
  - `WR04W2R20FTL` -> `0402_2.20R_1%`.
- Added Walsin WW parser:
  - `WW25RR001FTL` -> `2512_0.001R_1%`.
- Fixed TA-I RM dash-value variants:
  - `RM06JTN-2R2` -> `0603_2.2R_5%`.

#### Capacitors / MLCC

- Fixed Yageo CC capacitance decoding for EIA 3-digit pF values.
- Added Yageo voltage and tolerance extraction.
- Expanded Murata GRM support:
  - `GRM1555C1H270JA01D` -> `0402_27pF_50V_C0G_5%`;
  - `GRM155R71H681KA01D` -> `0402_680pF_50V_X7R_10%`;
  - `GRM155R61E104K` -> `0402_100nF_16V_X5R_10%`;
  - `GRM155R61A104KA01D` -> `0402_100nF_10V_X5R_10%`;
  - `GRM155R61C105KA12D` -> `0402_1uF_6.3V_X5R_10%`;
  - `GRM155R60J105KE19D` -> `0402_1uF_100V_X5R_10%`.
- Expanded Walsin MLCC support:
  - `0402B102K500CT`;
  - `0402X105K6R3CT` -> `0402_1uF_6.3V_10%`;
  - `0805X475M6R3CT`;
  - `1206X106K250CT`.
- Expanded Taiyo Yuden support:
  - `JMK212BJ226MG-T`;
  - `TMK107BJ105KA-T` -> `0603_1uF_6.3V_X5R_10%`.
- Fixed classifier priority so capacitor-shaped MPNs are checked before generic resistor heuristics.

### INFERIT Regex Presets

- Added regex presets for INFERIT-style resistor rows such as:
  - `RES 0201 10K OHM +/-1% LEAD-FREE - Y01`.
- Added presets for INFERIT capacitor rows such as:
  - `CAP 0402 10pF/50V +/-5% NPO LEAD-FREE - Y01`.
- Added presets for inductor and ferrite-bead rows:
  - `SMD-INDUCTOR ... 1.0uH +/-20% ... 4.5A`;
  - `FERRITE-BEAD 0402 120 OHM@100MHz +/-25% 700mA`.
- Added OTHER extractors for common BOM descriptions:
  - `POWER-IC`;
  - `TYPEC IC`;
  - generic `IC`;
  - `MOSFET`;
  - diode / ESD protection rows;
  - `CRYSTAL`;
  - MPNs inside parentheses.

### File Loading / Table Editing

- Added `.txt` and `.tab` to supported file dialogs.
- Fixed old binary `.xls` loading by selecting `xlrd` for `.xls` and `openpyxl` for `.xlsx`.
- Added text/CSV fallback for misleading Excel extensions.
- Stopped row-range and separator edits from silently reloading and wiping table edits.
- Added editable BOM and PnP working tables.
- Added autosave snapshots for edited BOM/PnP working copies.
- Added recovery prompt for dirty working copies on startup/file open.
- Fixed startup crash after choosing `Recovered` by avoiding direct DataFrame/string comparison.

### PnP / XY Parsing

- Fixed fixed-width XY parsing for files where standalone `m` marks mirror/bottom side.
- Example output for `WMH610M15R110-XY.txt`:
  - columns: `Ref`, `X`, `Y`, `Rotation`, `Layer`, `Footprint`;
  - rows like `180  m C0402` now parse as `Layer=m`, `Footprint=C0402`.

### Merge

- Fixed `Delete DNP components` so Merge can remove PnP rows whose ref is not found in BOM.
- Made Merge ref matching case-insensitive.
- Added `Replace PNP` button to replace the PnP tab data with the current Merge result.
- Added layer-aware export controls:
  - `Export Top` + layer dropdown;
  - `Export Bot` + layer dropdown.
- Auto-detects layer values from the Merge `Layer` column:
  - examples: `None` / `m`, `T` / `B`, `Top` / `Bottom`.
- Disables `Export Bot` when the board appears single-sided or no usable layer split exists.

### Tests

- Added regression tests for vendor PN parser fixes.
- Added regression tests for template ordering and vendor PN reformatting.
- Added tests for user component library behavior.
- Added tests for working-copy autosave snapshots.
- Added tests for INFERIT regex presets.
- Added tests for fixed-width XY parsing with the standalone `m` marker.
- Added tests for Merge DNP deletion behavior.
- Converted `tests/test_duplicate/test_duplicate_coords.py` from a manual script into real pytest tests using local fixture CSV files.

### Repository Cleanup

- Kept `components.txt` as the editable user component database.
- Added `requirements.txt` for reproducible local setup.
- Expanded `.gitignore` for Python caches, pytest/coverage output, autosave snapshots, recovery data, and generated exports.
- Removed legacy desktop entrypoints and helper UI modules.
- Removed backup UI files.
- Removed Streamlit/NiceGUI/web prototypes; future web work should be rebuilt on top of shared services.
- Removed local pytest cache folders.

### Verification Notes

Targeted checks run during this cycle included:

- Clean/parser/working-copy tests: `33 passed`.
- Format/duplicate checks: `10 passed, 3 skipped`.
- Full suite after legacy/web cleanup: `64 passed, 4 skipped, 9 failed`.
- Targeted changed-module compilation via `py_compile`.
- Linter diagnostics for edited files showed no new issues.

The full legacy suite still needs a cleanup pass because some old tests encode assumptions from the earlier reader architecture. Current known failures are tracked in `TODO.md`.

## 2026-04-24

### PySide6 Desktop Migration

- Added the PySide6 desktop app alongside the older desktop UI.
- Added Project, BOM, PnP, Clean BOM, Merge, and Report tabs.
- Added table previews backed by pandas DataFrames and Qt table models.
- Added dropdown-based column mapping above BOM and PnP tables.
- Added QSettings-backed UI state for theme and selected options.
- Added background cross-check execution with `QThread`.
- Added console/log output in the Project tab.

### File Reader / Cross-Check Work

- Added tests for `smt_processor` and file formats.
- Improved fixed-width PnP parsing for Eagle/cmp-style files.
- Added support for optional column mappings via `_skip_`.
- Improved coordinate parsing with `mm` and `mil` suffix handling.
- Added auto-detection fallbacks for key columns when mappings are incomplete.

### Status at the End of 2026-04-24

The PySide6 app could load BOM/PnP data, map columns, and run cross-checks on real files. Clean BOM, Merge, and Report continued to evolve on 2026-04-25.

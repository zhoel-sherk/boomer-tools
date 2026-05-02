# Hanwha / Samsung UPD `.mdb` (sample `UPD.MDB`)

Observed with **mdbtools** (`mdb-tables`, `mdb-schema`, `mdb-export`) on a shop UPD library. Do not commit full proprietary `.mdb` files to git; keep CSV snippets or minimal fixtures under `tests/fixtures/` only.

## Component names (primary for Boomer matching)

| Table      | Role |
|-----------|------|
| **PART_Det** | One row per machine library part. **`PARTNAME`** is the string the placement software uses for the component. **`PROFILENAME`** links to vision/tuning profile (`PROFILE_Det`). **`PARTDESC`** is a longer text field (often blank in samples). **`CONFIDENCE_LEVEL`**, **`USED_MACHINE_SET`** are numeric flags. |

## Related tables (feeder / nozzle / vision / machine variants)

The same file contains many mapping and parameter tables, including machine-generation prefixes (`40`, `45`, `55`, `60`), e.g.:

- `FEEDERTYPE_Map`, `NOZZLETYPE_Map`, `PARTGROUP_Map`
- `PROFILE_Det`, `PROFILEHANDDATA_Det`, `PROFILECOMDATA_Det`
- `HM520_HANDDATA_Det`, `DECAN2_HANDDATA_Det`, `SM471_HANDDATA_Det`, …
- Large `VISION_*` detail tables for optical models

For **first integration**, exporting **`PART_Det`** is enough to populate a searchable list of machine part names. Feeder/nozzle linkage can be added later if job export requires it.

## Linux tooling

```bash
mdb-tables /path/to/UPD.MDB
mdb-schema /path/to/UPD.MDB
mdb-export /path/to/UPD.MDB PART_Det
```

Python entry points (no PySide6): `src/machine_library/hanwha_mdbtools.py`.

## Editing PART_Det

See [`doc/hanwha_mdb_editor.md`](hanwha_mdb_editor.md): separate `hanwha_mdb_edit` package (core vs GUI). On Linux, **in-place `.mdb` binary updates are not done** via `mdb-sql` (read-oriented SQL subset); Boomer writes **backup + CSV snapshot** (and uses **ODBC DELETE/INSERT on Windows** when drivers allow).

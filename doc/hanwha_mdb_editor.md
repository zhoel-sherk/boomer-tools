# Hanwha UPD `.mdb` editor (`hanwha_mdb_edit`)

## Purpose

Edit **PART_Det** together with linked profile fields loaded from the same `.mdb`:

| Source table | Columns shown |
|----------------|----------------|
| PART_Det | PARTNAME … VENDORID |
| PROFILE_Det | **PARENTPROFILE** (BASE / parent template), **UPDPARTGROUPID** |
| PROFILECOMDATA_Det | **FEEDINGSPEEDLEVEL** (feeding speed level) |
| Q_HANDDATA_Det | **OVERALL_SPEED_LEVEL** (Q-hand motion speed level) |

- **Qt-free core:** [`src/hanwha_mdb_edit/core/`](../src/hanwha_mdb_edit/core/) — joins in [`part_enriched.py`](../src/hanwha_mdb_edit/core/part_enriched.py) (`load_enriched_parts_dataframe`, **`load_wide_editor_dataframe`** for temporary “all joinable tables” mode), bulk helpers in [`part_bulk.py`](../src/hanwha_mdb_edit/core/part_bulk.py), save in [`save.py`](../src/hanwha_mdb_edit/core/save.py).
- **GUI:** [`editor_window.py`](../src/hanwha_mdb_edit/gui/editor_window.py) — **Bulk** buttons for BASE profile, feeding speed, and Q speed; **Config…** opens a separate tool window ([`column_settings_window.py`](../src/hanwha_mdb_edit/gui/column_settings_window.py)) to show/hide columns. Visibility is stored in **QSettings** (`Boomer` / `HanwhaMdbEdit`, keyed by the resolved `.mdb` path). The editor currently loads the **wide** dataframe so every table with `PARTNAME` or `PROFILENAME` appears as `Table__column`; save still exports only the four library tables above (extra view columns are not written as new sidecars).

## Bulk edit

- **Bulk BASE profile:** set **PARENTPROFILE** everywhere it currently equals a chosen value (parent/base template).
- **Bulk feeding speed:** set **FEEDINGSPEEDLEVEL** either for one **PROFILENAME** or for all rows sharing the same **PARENTPROFILE**.
- **Bulk Q speed:** same pattern for **OVERALL_SPEED_LEVEL**.

Changes apply to the in-memory table until you press **Save**.

## Saving

1. **Always:** backup `YourFile.mdb.bak-YYYYMMDDTHHMMSSZ` next to the library.

2. **Always (full save):** four CSV snapshots next to the `.mdb`:

   - `YourFile_PART_Det_saved.csv`
   - `YourFile_PROFILE_Det_saved.csv`
   - `YourFile_PROFILECOMDATA_saved.csv`
   - `YourFile_Q_HANDDATA_saved.csv`

   Content is the **full** exported table with merged edits applied on top (only the joined columns are overwritten from the editor state).

3. **Linux:** Jet is not updated in place via `mdb-sql`; use the CSV set for re-import on Windows / Access / shop tools.

4. **Windows:** `pyodbc` — `PART_Det` replace + `UPDATE` on **PROFILE_Det**, **PROFILECOMDATA_Det**, **Q_HANDDATA_Det** for edited profiles.

## Requirements

- `mdb-tables` / `mdb-export` on `PATH`.
- Optional Windows write: `pyodbc` + Microsoft Access ODBC driver.

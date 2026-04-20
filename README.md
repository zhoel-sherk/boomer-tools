# BOM and PnP verifier + tools (Readme WIP)

---
Boomer Tools - Enhanced BOM vs PnP Cross Checker
New Features Added
1. Clean BOM Tab
Smart component value cleaning with intelligent classification:
- Resistors: Extracts package, value, and tolerance (e.g., 100R+1/16W+±5%+0402 → 0402_100R)
- Capacitors: Extracts package, value, voltage, dielectric, tolerance (e.g., 10UF+16V+±10%(K)+0402+X5R → 0402_10UF_16V_X5R_10%(K))
- Inductors: Extracts package, value, current rating (e.g., 2.2uH+±30%+1.6+3015 → 3015_2.2UH)
- Smart detection via priority markers (wattage for resistors, uF/nF/pF for capacitors, uH/nH for inductors)
2. Merge Report Tab
Merges BOM and Pick-and-Place data with:
- Configurable column mapping from profile
- Support for coordinate units (mils/mm)
- Export to CSV and Excel formats
3. Theme Toggle
Switch between Dark and Light modes with a single button click.
4. Column Selector Fixes
- Rotation column now properly shows in PnP column selector
- Fixed column name-to-index resolution
- Improved coordinate parsing (supports "mil" and "mm" suffixes)
5. Console View
Logging output displayed on Project tab for debugging.
---
Installation
pip install customtkinter xlrd openpyxl odfpy natsort pillow
python src/app.py
Original Project
https://github.com/marmidr/boomer
---

The purpose of this project is to help an electronic manufacturer in preparation of the new [PCB](Printed Circuit Board) elements.

It reads the [BOM](Bill Of Materials) and the accompanying [PnP](Pick And Place) files, performing cross-checking to ensure if those files contents matches.

Project selection:
![sshot1](doc/sshot1.png)

BOM preview:
![sshot2](doc/sshot2.png)

PnP preview:
![sshot3](doc/sshot3.png)

Report:
![sshot4](doc/sshot4.png)

The following checks are performed:

* BOM contains element that is missing in the PnP file
* PnP contains reference to element that is not present in the BOM
* Part comment (value) differs between BOM and PnP files
* Checks if the center of any two components in PnP file are closer that 3mm (120mils)

## Supported formats

* [BOM](. "Bill Of Materials")
  * .xls
  * .xlsx
  * .ods
  * .csv
* [PnP](. "Pick And Place")
  * .xls
  * .xlsx
  * .ods
  * any other extension - considered as a CSV file

> NOTE
>
> If xls/xlsx/ods file contains several sheets, only the first one will be used.

## Prerequisites

### Python

[Python for Windows with addons](https://www.python.org/).
Remember to check these options:

* pip
* tcl\tk
* Add Python to environment variables

Minimum required version is **Python 3.9**.

### Libraries

To install required libraries, open the PowerShell and:

```ps1
# .xls reader, .xlsx reader, .ods reader, UI lib, natural sorting, http requests, image formats
pip install xlrd openpyxl odfpy customtkinter natsort requests pillow

# alternative form, if the pip program cannot be found:
python -m pip install xlrd openpyxl odfpy customtkinter natsort requests pillow

# using local copy of fixed:
#   tkhtmlview - HTML widgets,
#   klembord - clipboard
```

## How to run

From PowerShell:

```ps1
python src/app.py
```

To get colored logs, use Linux-like terminal, eg. [MSys2](msys2.org/), but still using the Windows installation of the Python:

```sh
$ /c/Program\ Files/Python39/python.exe src/app.py
```

![msys2con](doc/msys2-console.png)

## Trouble shooting

* *ModuleNotFoundError: No module named 'tkinter'*

  `tkinter` was not installed together with the Python -
  follow the instructions [here](https://bobbyhadz.com/blog/python-no-module-named-tkinter).
* *ERROR: Cannot load BOM: 'utf-8' codec can't decode byte*

  Only UTF-8 files are accepted; if the BOM or PnP file uses ANSI or WINDOWS encoding, use `Notepad++` or other editor to change the encoding to UTF-8
*

## Unit tests

Uses [pytest](https://docs.pytest.org/en/latest/):

```ps1
pip install pytest
cd tests
# run all
pytest
# run single test
pytest test_csv_reader.py::test_no_file
# print everything
pytest -s
```

### Tests coverage

Uses [Coverage](https://coverage.readthedocs.io/en/):

```ps1
pip install coverage
cd tests
coverage run -m pytest
coverage report --omit "test_*"
# Name                 Stmts   Miss  Cover
# ----------------------------------------
# src/csv_reader.py       48      9    81%
# src/ods_reader.py       24      1    96%
# src/text_grid.py        49     27    45%
# src/xls_reader.py       24      1    96%
# src/xlsx_reader.py      23      0   100%
# ----------------------------------------
# TOTAL                  243     38    84%
coverage html --omit "test_*"
# open tests\htmlcov\index.html
```

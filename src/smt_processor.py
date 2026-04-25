"""
SMT Data Processor - Изолированное ядро для обработки BOM/PnP данных.

Модуль не содержит GUI зависимостей, работает только с pandas DataFrame.
Принимает пути к файлам или DataFrame, возвращает DataFrame с результатами.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional
import re
import datetime


# ==============================================================================
# Custom Exceptions
# ==============================================================================

class SMTProcessorError(Exception):
    """Базовое исключение для SMT Processor"""
    pass


class SMTFileNotFoundError(SMTProcessorError):
    """Файл не найден"""
    pass


class SMTSheetNotFoundError(SMTProcessorError):
    """Лист в Excel файле не найден"""
    pass


class SMTColumnNotFoundError(SMTProcessorError):
    """Требуемая колонка не найдена"""
    pass


class SMTEmptyDataError(SMTProcessorError):
    """Данные пустые или отсутствуют"""
    pass


# ==============================================================================
# Data Classes
# ==============================================================================

@dataclass
class ColumnConfig:
    """Конфигурация колонок для обработки"""
    designator: str = "?"
    comment: str = "?"
    # PnP дополнительные
    footprint: str = "?"
    coord_x: str = "?"
    coord_y: str = "?"
    rotation: str = "?"
    layer: str = "?"
    first_row: int = 0  # 0-based
    last_row: int = -1  # -1 = все строки
    has_header: bool = True
    separator: str = ","


@dataclass
class CrossCheckResult:
    """Результат cross-check"""
    designator: str
    issue_type: str  # "missing_in_bom", "missing_in_pnp", "mismatch", "duplicate_coord"
    bom_value: Optional[str] = None
    pnp_value: Optional[str] = None
    footprint: Optional[str] = None
    coord_x: Optional[float] = None
    coord_y: Optional[float] = None
    severity: str = "warning"  # critical, warning, info


@dataclass
class ProcessorConfig:
    """Глобальная конфигурация процессора"""
    # Overlap: centers closer than this (mm) on the same layer; O(n²) on PnP size — disable for dense boards.
    min_distance_mm: float = 3.0
    check_overlap: bool = False
    coord_unit_mils: bool = True  # True = mm, False = mils
    normalize_comments: bool = False  # нормализация comment перед сравнением
    # Optional callback (message, level) e.g. GUI log; safe from worker thread if level uses Qt::QueuedConnection.
    progress_log: Optional[Callable[[str, str], None]] = field(default=None, repr=False)

    def emit_progress(self, message: str, level: str = "info") -> None:
        if self.progress_log is not None:
            self.progress_log(message, level)


# ==============================================================================
# File Readers
# ==============================================================================

def read_file(path: str, sheet_name: Optional[str] = None, first_row: int = 0, last_row: int = -1, separator: Optional[str] = None) -> pd.DataFrame:
    """
    Универсальный ридер файлов BOM/PnP.
    
    Args:
        path: Путь к файлу (.xlsx, .xls, .csv, .ods)
        sheet_name: Имя листа (для Excel/ODS). Если None - первый лист.
        first_row: Индекс первой строки с данными (0-based)
        last_row: Индекс последней строки (-1 = все строки)
        separator: Разделитель для CSV (None = auto)
    
    Returns:
        pandas.DataFrame
    
    Raises:
        SMTFileNotFoundError: Файл не найден
        SMTSheetNotFoundError: Лист не найден
        SMTEmptyDataError: Файл пустой
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        raise SMTFileNotFoundError(f"File not found: {path}")
    
    suffix = path_obj.suffix.lower()
    df: pd.DataFrame
    
    if suffix in ['.xlsx', '.xls']:
        df = _read_excel(path, sheet_name)
    elif suffix in ['.csv', '.txt', '.tab']:
        if separator == "spaces":
            raise SMTProcessorError(
                "Separator 'spaces' (classic SPACES/*sp) is applied in the GUI only: "
                "it uses read_text_whitespace_sp() and optional apply_row_as_column_header(). "
                "Call those from code, or use read_file() with another separator."
            )
        sep_value = None
        if separator and separator != "auto":
            if separator == "2+sp":
                sep_value = "2+sp"  # Special: split on 2+ spaces
            elif separator == "fixed":
                sep_value = "fixed"
            elif separator == "space":
                sep_value = " "
            else:
                sep_value = separator
        df = _read_csv(path, separator=sep_value)
    elif suffix == '.ods':
        df = _read_ods(path, sheet_name)
    else:
        raise SMTProcessorError(f"Unsupported file format: {suffix}")
    
    # Очистка пустых строк
    df = _clean_empty_rows(df)
    
    if df.empty:
        raise SMTEmptyDataError(f"File is empty or has no valid rows: {path}")
    
    # Применяем first_row если указан
    if first_row > 0 and first_row < len(df):
        df = df.iloc[first_row:].reset_index(drop=True)
    
    # Применяем last_row если указан
    if last_row > 0 and last_row < len(df):
        df = df.iloc[:last_row].reset_index(drop=True)
    
    return df


def _drop_fully_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove columns that are 100% NaN only.

    Merged cells in Excel often yield 'Unnamed: N' headers; those columns can still
    hold data and must be kept. The old filter dropped all Unnamed columns and hid
    real BOM fields (e.g. 9 columns shown as 6).
    """
    if df.empty or len(df.columns) == 0:
        return df
    keep = [c for c in df.columns if not df[c].isna().all()]
    if not keep:
        return df
    return df[keep].copy()


def _read_excel(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Читает Excel файл - специальная обработка для китайских форматов BOM"""
    try:
        suffix = Path(path).suffix.lower()
        engine = "xlrd" if suffix == ".xls" else "openpyxl"
        # Open file and get first sheet
        xls = pd.ExcelFile(path, engine=engine)
        sheet = sheet_name if sheet_name else xls.sheet_names[0]
        
        # First read to check structure
        df = pd.read_excel(xls, sheet_name=sheet)
        
        # Check if column 1 (second column) is datetime - indicates Chinese BOM with merged cells
        if len(df.columns) > 1:
            col1 = df.columns[1]
            # If second column header is datetime, use row 3 as header
            if isinstance(col1, datetime.datetime):
                # This is a Chinese BOM - read with header at row 3
                df = pd.read_excel(xls, sheet_name=sheet, header=3)
                df = _drop_fully_empty_columns(df)
                return df
        
        return df
        
    except Exception as e:
        # Some vendor exports are plain text/CSV with a misleading Excel extension.
        # Try the robust text reader before giving up, so users can still import data.
        try:
            return _read_csv(path, separator=None)
        except Exception:
            raise SMTProcessorError(
                f"Cannot read Excel file: {e}. "
                "If this is a text placement file, rename it to .txt/.csv or open it as a text file."
            )


EAGLE_CMP_9_COLS: list[str] = [
    "Designator",
    "Value",
    "Footprint",
    "Mid-X (mil)",
    "Mid-Y (mil)",
    "Pos-X (mm)",
    "Pos-Y (mm)",
    "Rotation",
    "Layer",
]


def _check_row_valid_whitespace_sp(row_cells: list[str]) -> bool:
    """Same rules as csv_reader.__check_row_valid for SPACES / *sp."""
    if len(row_cells) <= 3:
        return False
    if not (row_cells[0] or row_cells[1] or row_cells[2]):
        return False
    if row_cells[0].startswith("___"):
        return False
    return True


def _read_sp_quoted_row(row_cells: list[str]) -> list[str]:
    """Merge double-quoted runs like csv_reader.__read_sp."""
    row_out: list[str] = []
    quoted_cell = ""
    for cell in row_cells:
        if cell.startswith('"'):
            quoted_cell = cell
        elif len(quoted_cell) > 0:
            quoted_cell += " "
            quoted_cell += cell
            if cell.endswith('"'):
                quoted_cell = quoted_cell[1:-1]
                row_out.append(quoted_cell)
                quoted_cell = ""
        else:
            row_out.append(cell.strip())
    return row_out


def _unique_dataframe_column_names(raw: list[str]) -> list[str]:
    used: set[str] = set()
    out: list[str] = []
    for i, n in enumerate(raw):
        base = str(n).strip() if n is not None and str(n).strip() else f"Unnamed_{i}"
        name = base
        j = 0
        while name in used:
            j += 1
            name = f"{base}__{j}"
        used.add(name)
        out.append(name)
    return out


def read_text_whitespace_sp(path: str) -> pd.DataFrame:
    """
    Classic Boomer SPACES (Profile SPACES / *sp): use str.split() on each line.
    Same validation and quoting as csv_reader for delim '*sp'. Does not set header row;
    use apply_row_as_header() when Has headers + 1st points at that row.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            file_lines = f.read().splitlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            file_lines = f.read().splitlines()
    max_cols = 0
    out_rows: list[list[str]] = []
    for row in file_lines:
        row_cells = row.split()
        if not _check_row_valid_whitespace_sp(row_cells):
            continue
        row_out = _read_sp_quoted_row(row_cells)
        max_cols = max(max_cols, len(row_out))
        out_rows.append(row_out)
    if not out_rows:
        return pd.DataFrame()
    for r in out_rows:
        if len(r) < max_cols:
            r.extend([""] * (max_cols - len(r)))
    return pd.DataFrame(out_rows, columns=[str(i) for i in range(max_cols)])


def apply_row_as_column_header(df: pd.DataFrame, row_index: int) -> pd.DataFrame:
    """
    Use df.iloc[row_index] as column names, drop that row. Matches classic Boomer
    when first_row points to the header line (see cross_check.__extract_grid).
    """
    if row_index < 0 or row_index >= len(df):
        raise SMTProcessorError(
            f"Header row {row_index} out of range (0..{len(df) - 1})"
        )
    raw = [str(x) for x in df.iloc[row_index].tolist()]
    names = _unique_dataframe_column_names(raw)
    out = df.iloc[row_index + 1 :].copy()
    out.columns = names
    return out.reset_index(drop=True)


def _read_csv(path: str, separator: Optional[str] = None, skip_meta: bool = True) -> pd.DataFrame:
    """Читает CSV файл с автоопределением разделителя и пропуском метаданных"""
    # Handle special separators
    if separator in ("2+sp", "fixed"):
        return _read_fixed_width(path, 0)  # Use read_file(..., first_row=) to skip Board/header lines
    
    # Try detecting file type first
    start_row = 0
    if skip_meta:
        start_row = _find_data_start(path)
    
    # Detect if fixed-width (multiple spaces as columns)
    is_fixed_width = _is_fixed_width(path, start_row)
    
    if is_fixed_width:
        return _read_fixed_width(path, start_row)
    
    # Auto-detect separator
    if separator is None:
        separator = _detect_delimiter(path)
    
    try:
        df = pd.read_csv(path, sep=separator, encoding='utf-8', skiprows=start_row, on_bad_lines='skip')
    except (UnicodeDecodeError, pd.errors.ParserError):
        try:
            df = pd.read_csv(path, sep=separator, encoding='latin-1', skiprows=start_row, on_bad_lines='skip')
        except:
            df = pd.read_csv(path, sep='\t', encoding='utf-8', skiprows=start_row, on_bad_lines='skip')
    return df


def _is_fixed_width(path: str, start_row: int) -> bool:
    """Определяет fixed-width формат по наличию множественных пробелов"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(24))
        hl = head.lower()
        if "board" in hl and "unit" in hl and ("mm" in hl or "mil" in hl):
            return True
        f2 = open(path, "r", encoding="utf-8")
        try:
            for i, line in enumerate(f2):
                if i < start_row:
                    continue
                if i > start_row + 2:
                    break
                line = line.rstrip("\n")
                if not line:
                    continue
                if "  " in line and "\t" not in line:
                    if len(line) > 20 and " " in line:
                        return True
        finally:
            f2.close()
    except Exception:
        pass
    return False


def _read_fixed_width(path: str, start_row: int) -> pd.DataFrame:
    """Читает fixed-width формат - split by 2+ spaces"""
    import re
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            lines = f.readlines()
    
    try:
        if len(lines) <= start_row:
            return pd.DataFrame()
        
        # Skip to actual data (after metadata rows)
        data_lines = []
        for i in range(start_row, len(lines)):
            line = lines[i].strip()
            if line.upper().startswith(("UUNITS", "UNITS")):
                continue
            if line and not line.startswith('#'):
                data_lines.append(line)
        
        if len(data_lines) < 2:
            return pd.DataFrame()
        
        # Split all data rows using 2+ spaces
        data_rows = []
        for line in data_lines:
            parts = re.split(r' {2,}', line.strip())
            parts = [p.strip() for p in parts if p.strip()]
            
            # Split last column if it has both rotation + angle
            if len(parts) > 0 and ' ' in parts[-1]:
                try_parts = parts[-1].split()
                if len(try_parts) >= 2:
                    if try_parts[0].replace('.','').replace('-','').isdigit():
                        parts = parts[:-1] + try_parts
                    elif (
                        len(try_parts) == 2
                        and len(try_parts[0]) <= 2
                        and re.fullmatch(r"[A-Za-z]+", try_parts[0])
                    ):
                        parts = parts[:-1] + try_parts
            
            data_rows.append(parts)
        
        if not data_rows:
            return pd.DataFrame()
        
        # Eagle/Board: some rows have 8 fields (value+package in one) vs 9 (split) — align to 9
        head_eagle = "".join(lines[:24]).lower()
        is_eagle_board = "board" in head_eagle and "unit" in head_eagle
        is_xy_list = "uunits" in head_eagle or (
            data_rows
            and max(len(row) for row in data_rows) <= 6
            and all(len(row) >= 5 for row in data_rows[: min(20, len(data_rows))])
        )
        if is_eagle_board:
            for i, row in enumerate(data_rows):
                if len(row) == 8:
                    data_rows[i] = row[:2] + [""] + row[2:]
        if is_xy_list and max(len(row) for row in data_rows) == 6:
            for i, row in enumerate(data_rows):
                if len(row) == 5:
                    data_rows[i] = row[:4] + [""] + row[4:]

        # Number of columns from data
        max_cols = max(len(row) for row in data_rows)
        
        xy_6 = ["Ref", "X", "Y", "Rotation", "Layer", "Footprint"]
        xy_5 = ["Ref", "X", "Y", "Rotation", "Footprint"]
        generic_11 = [
            "Designator", "Footprint", "Mid-X", "Mid-Y", "Ref-X",
            "Ref-Y", "Pad-X", "Pad-Y", "Layer", "Rotation", "Comment",
        ]
        if is_xy_list and max_cols <= 6:
            if max_cols == 6:
                cols = xy_6
            else:
                cols = xy_5[:max_cols]
            actual_cols = max_cols
        elif max_cols == 9:
            cols = list(EAGLE_CMP_9_COLS)
            actual_cols = 9
        elif max_cols <= len(generic_11):
            cols = generic_11[:max_cols]
            actual_cols = max_cols
        else:
            cols = generic_11 + [f"Col{i+1}" for i in range(len(generic_11), max_cols)]
            actual_cols = max_cols
        
        # Normalize rows to actual column count
        normalized = []
        for row in data_rows:
            row = row[:actual_cols]
            if len(row) < actual_cols:
                row = row + [""] * (actual_cols - len(row))
            normalized.append(row)
        
        df = pd.DataFrame(normalized, columns=cols)
        
        return df
        
    except Exception:
        pass
    
    return pd.read_csv(path, sep='\t', skiprows=start_row, header=None)


def _detect_delimiter(path: str) -> str:
    """Автоматически определяет разделитель в CSV"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            first_lines = [f.readline() for _ in range(15)]
    except UnicodeDecodeError:
        with open(path, 'r', encoding='latin-1') as f:
            first_lines = [f.readline() for _ in range(15)]
    
    # Считаем разделители
    separators = {',': 0, ';': 0, '\t': 0, '|': 0}
    for line in first_lines:
        for sep in separators:
            separators[sep] += line.count(sep)
    
    # Возвращаем самый частый
    if max(separators.values()) > 0:
        return max(separators, key=separators.get)
    return ','  # Default


def _find_data_start(path: str) -> int:
    """Находит строку с реальными данными (пропускает метаданные)"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                
                # Skip separator lines like ====
                if line.startswith('==='):
                    continue
                
                line_lower = line.lower()
                
                # Skip pure metadata lines (key: value) - no comma, no quotes
                # But still check if line has column content
                has_columns = any(k in line_lower for k in ['designator', 'comment', 'layer', 'footprint', 
                                           'center', 'pattern', 'refdes', 'valued',
                                           'name', 'rotation', 'center-x', 'center-y'])
                
                # Has quoted CSV header (has both quotes and comma)
                if line.startswith('"') and '"' in line and ',' in line:
                    return i
                
                # Has tab-separated columns
                if '\t' in line and has_columns:
                    return i
                
                # Has typical column names AND has separator (comma/tab)
                if has_columns and (',' in line or '\t' in line):
                    return i
                
                # Has multiple spaces between words and has columns
                if '  ' in line and not line.startswith(' '):
                    parts = line.split()
                    if len(parts) >= 3 and has_columns:
                        return i
    except:
        pass
    return 0  # Default


def _read_ods(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Читает ODS файл (Open Document Spreadsheet)"""
    try:
        if sheet_name:
            df = pd.read_excel(path, sheet_name=sheet_name, engine='odf')
        else:
            df = pd.read_excel(path, engine='odf')
    except Exception as e:
        raise SMTProcessorError(f"Cannot read ODS file: {e}")
    return df


def _clean_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Удаляет строки, где все ячейки пустые илиNaN.
    Также удаляет строки, начинающиеся с '___'.
    """
    if df.empty:
        return df
    
    # Удаляем строки где все значения NaN
    df = df.dropna(how='all')
    
    # Удаляем строки начинающиеся с ___ (разделители в Excel)
    if not df.empty and len(df.columns) > 0:
        first_col = df.columns[0]
        df = df[~df[first_col].astype(str).str.startswith('___')]
    
    df = df.reset_index(drop=True)
    return df


# ==============================================================================
# Main Processor
# ==============================================================================

class SMTDataProcessor:
    """
    Основной процессор для SMT данных.
    
    Изолирован от GUI, работает только с pandas.
    """
    
    def __init__(self, config: Optional[ProcessorConfig] = None):
        self.config = config or ProcessorConfig()
        self._bom_df: Optional[pd.DataFrame] = None
        self._pnp_df: Optional[pd.DataFrame] = None
        self._bom_config: Optional[ColumnConfig] = None
        self._pnp_config: Optional[ColumnConfig] = None
    
    # --------------------------------------------------------------------------
    # Loading Methods
    # --------------------------------------------------------------------------
    
    def load_bom(self, path: str, config: ColumnConfig) -> "SMTDataProcessor":
        """
        Загружает BOM файл.
        
        Args:
            path: Путь к файлу BOM
            config: Конфигурация колонок
        
        Returns:
            self для цепочки вызовов
        """
        self._bom_df = read_file(path, first_row=config.first_row)
        self._bom_config = config
        return self
    
    def load_pnp(self, path: str, config: ColumnConfig) -> "SMTDataProcessor":
        """
        Загружает PnP файл.
        
        Args:
            path: Путь к файлу PnP
            config: Конфигурация колонок
        
        Returns:
            self для цепочки вызовов
        """
        self._pnp_df = read_file(path, first_row=config.first_row)
        self._pnp_config = config
        return self
    
    def set_dataframes(self, bom_df: pd.DataFrame, pnp_df: pd.DataFrame,
                     bom_config: ColumnConfig, pnp_config: ColumnConfig) -> "SMTDataProcessor":
        """
        Устанавливает DataFrame напрямую (минуя загрузку из файла).
        
        Args:
            bom_df: DataFrame с данными BOM
            pnp_df: DataFrame с данными PnP
            bom_config: Конфигурация колонок BOM
            pnp_config: Конфигурация колонок PnP
        
        Returns:
            self для цепочки вызовов
        """
        self._bom_df = bom_df
        self._pnp_df = pnp_df
        self._bom_config = bom_config
        self._pnp_config = pnp_config
        return self
    
    # --------------------------------------------------------------------------
    # Getters
    # --------------------------------------------------------------------------
    
    @property
    def bom_df(self) -> Optional[pd.DataFrame]:
        return self._bom_df
    
    @property
    def pnp_df(self) -> Optional[pd.DataFrame]:
        return self._pnp_df
    
    @property
    def bom_columns(self) -> list[str]:
        """Возвращает список колонок BOM"""
        if self._bom_df is None:
            return []
        return list(self._bom_df.columns)
    
    @property
    def pnp_columns(self) -> list[str]:
        """Возвращает список колонок PnP"""
        if self._pnp_df is None:
            return []
        return list(self._pnp_df.columns)
    
    def find_column_index(self, df: pd.DataFrame, col_identifier: str, has_header: bool = True) -> int:
        """
        Находит индекс колонки по имени или номеру.
        
        Args:
            df: DataFrame для поиска
            col_identifier: Имя колонки (str) или номер (int)
            has_header: Есть ли заголовки
        
        Returns:
            Индекс колонки (0-based)
        
        Raises:
            SMTColumnNotFoundError: Колонка не найдена
        """
        # Allow "_skip_" to mean "optional - skip this check"
        if col_identifier == "_skip_" or col_identifier is None:
            return -1  # Return -1 to indicate "skip"
        
        if col_identifier == "?" or col_identifier == "":
            raise SMTColumnNotFoundError(f"Column not specified: {col_identifier}")
        
        # Если число - возвращаем как индекс
        if isinstance(col_identifier, int):
            return col_identifier
        
        if isinstance(col_identifier, str):
            # Пробуем как номер
            try:
                idx = int(col_identifier)
                if 0 <= idx < len(df.columns):
                    return idx
            except ValueError:
                pass
            
            # Пробуем как имя (точно или часть)
            cols = [str(c).strip() if c is not None else "" for c in df.columns]
            col_upper = str(col_identifier).strip().upper()
            
            # Точное совпадение
            for i, c in enumerate(cols):
                if c.upper() == col_upper:
                    return i
            
            # Частичное совпадение
            for i, c in enumerate(cols):
                if col_upper in c.upper():
                    return i
        
        raise SMTColumnNotFoundError(f"Column '{col_identifier}' not found in DataFrame")
    
    # --------------------------------------------------------------------------
    # Cross-Check
    # --------------------------------------------------------------------------
    
    def cross_check(self) -> pd.DataFrame:
        """
        Основной метод: сравнение BOM и PnP.
        
        Returns:
            DataFrame с результатами: 
            - Designator, IssueType, BOM_Value, PnP_Value, 
            - Footprint, Coord_X, Coord_Y, Severity
        """
        if self._bom_df is None:
            raise SMTEmptyDataError("BOM not loaded. Call load_bom() or set_dataframes() first.")
        if self._pnp_df is None:
            raise SMTEmptyDataError("PnP not loaded. Call load_pnp() or set_dataframes() first.")
        
        self.config.emit_progress("Cross-check: resolving column mapping...", "info")
        results: list[CrossCheckResult] = []
        
        # Находим индексы колонок
        bom_config = self._bom_config or ColumnConfig()
        pnp_config = self._pnp_config or ColumnConfig()
        
        try:
            bom_designator_idx = self.find_column_index(self._bom_df, bom_config.designator, bom_config.has_header)
            bom_comment_idx = self.find_column_index(self._bom_df, bom_config.comment, bom_config.has_header)
        except SMTColumnNotFoundError as e:
            raise SMTColumnNotFoundError(f"BOM configuration error: {e}")
        
        try:
            pnp_designator_idx = self.find_column_index(self._pnp_df, pnp_config.designator, pnp_config.has_header)
            pnp_comment_idx = self.find_column_index(self._pnp_df, pnp_config.comment, pnp_config.has_header)
        except SMTColumnNotFoundError as e:
            raise SMTColumnNotFoundError(f"PnP configuration error: {e}")
        
        # Извлекаем данные
        self.config.emit_progress("Cross-check: reading BOM and PnP parts...", "info")
        bom_parts = self._extract_bom_parts(bom_designator_idx, bom_comment_idx)
        pnp_parts = self._extract_pnp_parts(pnp_designator_idx, pnp_comment_idx, pnp_config)
        self.config.emit_progress(
            f"Cross-check: {len(bom_parts)} BOM designators, {len(pnp_parts)} PnP rows",
            "info",
        )
        
        # 1. Проверяем: BOM parts missing in PnP (warning - часто fiducials/разъемы не в BOM)
        for designator, bom_comment in bom_parts.items():
            if designator and designator not in pnp_parts:
                results.append(CrossCheckResult(
                    designator=designator,
                    issue_type="missing_in_pnp",
                    bom_value=bom_comment,
                    pnp_value=None,
                    severity="warning"  # Warning - может быть нормально
                ))
        
        # 2. Проверяем: PnP parts missing in BOM (critical - компонент есть но нет в BOM!)
        for designator, pnp_data in pnp_parts.items():
            if designator and designator not in bom_parts:
                pnp_comment = pnp_data[0] if pnp_data else None
                results.append(CrossCheckResult(
                    designator=designator,
                    issue_type="missing_in_bom",
                    bom_value=None,
                    pnp_value=pnp_comment,
                    severity="critical"  # Critical - реальная проблема
                ))
        
        # 3. Проверяем: Comment mismatch
        for designator in bom_parts:
            if designator in pnp_parts:
                bom_val = bom_parts[designator]
                pnp_val = pnp_parts[designator][0] if pnp_parts[designator] else None
                
                if self.config.normalize_comments:
                    bom_val = _normalize_comment(bom_val)
                    pnp_val = _normalize_comment(pnp_val)
                
                if bom_val != pnp_val:
                    footprint = pnp_parts[designator][1] if len(pnp_parts[designator]) > 1 else None
                    coord_xy = pnp_parts[designator][2:] if len(pnp_parts[designator]) > 2 else (None, None)
                    results.append(CrossCheckResult(
                        designator=designator,
                        issue_type="mismatch",
                        bom_value=bom_val,
                        pnp_value=pnp_val,
                        footprint=footprint,
                        coord_x=coord_xy[0],
                        coord_y=coord_xy[1],
                        severity="warning"
                    ))
        
        # 4. Проверяем: Duplicate coordinates (exact match)
        self.config.emit_progress("Cross-check: duplicate exact coordinates (same X/Y)...", "info")
        coord_map: dict[tuple, list[str]] = {}
        for designator, pnp_data in pnp_parts.items():
            if len(pnp_data) > 2 and pnp_data[2] is not None:
                try:
                    coord = (float(pnp_data[2]), float(pnp_data[3]) if len(pnp_data) > 3 else 0.0)
                    if coord != (0.0, 0.0):
                        if coord not in coord_map:
                            coord_map[coord] = []
                        coord_map[coord].append(designator)
                except (ValueError, TypeError):
                    pass
        
        dup_pairs = 0
        for coord, parts in coord_map.items():
            if len(parts) > 1:
                for i in range(len(parts)):
                    for j in range(i + 1, len(parts)):
                        dup_pairs += 1
                        results.append(CrossCheckResult(
                            designator=f"{parts[i]}<->{parts[j]}",
                            issue_type="duplicate_coord",
                            pnp_value=f"({coord[0]}, {coord[1]})",
                            severity="critical"
                        ))
        if dup_pairs:
            self.config.emit_progress(f"Duplicate exact coordinates: {dup_pairs} pair(s)", "info")

        # 5. Overlapping (close centers) — like cross_check __check_distances; optional, heavy on large PnP
        if self.config.check_overlap and self.config.min_distance_mm > 0:
            n = len(pnp_parts)
            self.config.emit_progress(
                f"Overlap check: same-layer pairs with center distance < {self.config.min_distance_mm} mm "
                f"({n} placements — O(n²), can be slow on dense boards)",
                "info",
            )
            conflicts = _check_overlapping(pnp_parts, self.config.min_distance_mm, self.config.coord_unit_mils)
            self.config.emit_progress(f"Overlap: {len(conflicts)} pair(s) within threshold", "info")
            for part1, part2, dist in conflicts:
                results.append(CrossCheckResult(
                    designator=f"{part1} <--> {part2}",
                    issue_type="overlapping",
                    pnp_value=f"{dist:.1f}mm",
                    severity="info"
                ))
        else:
            self.config.emit_progress("Overlap check: off (faster; enable on Report tab if needed)", "info")

        self.config.emit_progress("Cross-check: building result table...", "info")
        # Конвертируем в DataFrame
        return self._results_to_dataframe(results)
    
    def _extract_bom_parts(self, designator_idx: int, comment_idx: int) -> dict[str, str]:
        """Извлекает компоненты из BOM"""
        parts = {}
        
        # Skip if designator_idx is -1
        if designator_idx < 0:
            return parts
            
        cols = list(self._bom_df.columns)
        
        for _, row in self._bom_df.iterrows():
            designator_col = cols[designator_idx] if designator_idx < len(cols) else None
            comment_col = cols[comment_idx] if comment_idx >= 0 and comment_idx < len(cols) else None
            
            if designator_col is None or pd.isna(row[designator_col]):
                continue
            
            designators = str(row[designator_col]).split(',')
            comment = str(row[comment_col]) if comment_col and not pd.isna(row[comment_col]) else ""
            
            for d in designators:
                d = d.strip()
                if d:
                    parts[d] = comment
        
        return parts
    
    def _extract_pnp_parts(self, designator_idx: int, comment_idx: int, 
                         config: ColumnConfig) -> dict[str, tuple]:
        """Извлекает компоненты из PnP"""
        parts = {}
        
        # Skip if designator_idx is -1
        if designator_idx < 0:
            return parts
            
        cols = list(self._pnp_df.columns)
        
        # Находим дополнительные колонки
        coord_x_col = coord_y_col = footprint_col = None
        for c in cols:
            c_upper = c.strip().upper()
            if config.coord_x not in ("?", "_skip_", None) and c_upper == config.coord_x.upper():
                coord_x_col = c
            if config.coord_y not in ("?", "_skip_", None) and c_upper == config.coord_y.upper():
                coord_y_col = c
            if config.footprint not in ("?", "_skip_", None) and c_upper == config.footprint.upper():
                footprint_col = c
        
        for _, row in self._pnp_df.iterrows():
            designator_col = cols[designator_idx] if designator_idx < len(cols) else None
            comment_col = cols[comment_idx] if comment_idx < len(cols) else None
            
            if designator_col is None or pd.isna(row[designator_col]):
                continue
            
            designators = str(row[designator_col]).split(',')
            comment = str(row[comment_col]) if comment_col and not pd.isna(row[comment_col]) else ""
            
            # Координаты
            coord_x = coord_y = None
            if coord_x_col and not pd.isna(row[coord_x_col]):
                try:
                    coord_x = self._parse_coord(row[coord_x_col])
                except:
                    pass
            if coord_y_col and not pd.isna(row[coord_y_col]):
                try:
                    coord_y = self._parse_coord(row[coord_y_col])
                except:
                    pass
            
            # Footprint
            footprint = None
            if footprint_col and not pd.isna(row[footprint_col]):
                footprint = str(row[footprint_col])
            
            for d in designators:
                d = d.strip()
                if d:
                    parts[d] = (comment, footprint, coord_x, coord_y)
        
        return parts
    
    def _parse_coord(self, value) -> Optional[float]:
        """Парсит координату в число"""
        if value is None or pd.isna(value):
            return None
        s = str(value)
        s = re.sub(r'[^\d.,\-]', '', s)
        try:
            return float(s)
        except ValueError:
            return None
    
    def _results_to_dataframe(self, results: list[CrossCheckResult]) -> pd.DataFrame:
        """Конвертирует результаты в DataFrame"""
        if not results:
            return pd.DataFrame(columns=[
                "Designator", "IssueType", "BOM_Value", "PnP_Value", 
                "Footprint", "Coord_X", "Coord_Y", "Severity"
            ])
        
        data = []
        for r in results:
            data.append({
                "Designator": r.designator,
                "IssueType": r.issue_type,
                "BOM_Value": r.bom_value if r.bom_value else "",
                "PnP_Value": r.pnp_value if r.pnp_value else "",
                "Footprint": r.footprint if r.footprint else "",
                "Coord_X": r.coord_x if r.coord_x else "",
                "Coord_Y": r.coord_y if r.coord_y else "",
                "Severity": r.severity
            })
        
        return pd.DataFrame(data)
    
    # --------------------------------------------------------------------------
    # Merge
    # --------------------------------------------------------------------------
    
    def merge_bom_pnp(self, include_dnp: bool = True) -> pd.DataFrame:
        """
        Объединяет BOM и PnP данные.
        
        Args:
            include_dnp: Включать ли компоненты со значением "DNP"
        
        Returns:
            DataFrame с колонками: Ref, Value, Footprint, X, Y, Rotation, Layer
        """
        if self._bom_df is None or self._pnp_df is None:
            raise SMTEmptyDataError("Both BOM and PnP must be loaded")
        
        bom_config = self._bom_config or ColumnConfig()
        pnp_config = self._pnp_config or ColumnConfig()
        
        # Имена колонок
        bom_cols = list(self._bom_df.columns)
        pnp_cols = list(self._pnp_df.columns)
        
        bom_designator_col = bom_comment_col = None
        for c in bom_cols:
            c_upper = c.strip().upper()
            if bom_config.designator != "?" and c_upper == bom_config.designator.upper():
                bom_designator_col = c
            if bom_config.comment != "?" and c_upper == bom_config.comment.upper():
                bom_comment_col = c
        
        pnp_designator_col = pnp_comment_col = None
        for c in pnp_cols:
            c_upper = c.strip().upper()
            if pnp_config.designator != "?" and c_upper == pnp_config.designator.upper():
                pnp_designator_col = c
            if pnp_config.comment != "?" and c_upper == pnp_config.comment.upper():
                pnp_comment_col = c
        
        # PnP дополнительные колонки
        pnp_x_col = pnp_y_col = pnp_rot_col = pnp_layer_col = pnp_fp_col = None
        for c in pnp_cols:
            c_upper = c.strip().upper()
            if pnp_config.coord_x != "?" and c_upper == pnp_config.coord_x.upper():
                pnp_x_col = c
            if pnp_config.coord_y != "?" and c_upper == pnp_config.coord_y.upper():
                pnp_y_col = c
            if pnp_config.rotation != "?" and c_upper == pnp_config.rotation.upper():
                pnp_rot_col = c
            if pnp_config.layer != "?" and c_upper == pnp_config.layer.upper():
                pnp_layer_col = c
            if pnp_config.footprint != "?" and c_upper == pnp_config.footprint.upper():
                pnp_fp_col = c
        
        def _ref_key(value: object) -> str:
            return str(value).strip().upper()

        # Map BOM designator -> comment
        bom_map = {}
        for _, row in self._bom_df.iterrows():
            if bom_designator_col is None or pd.isna(row[bom_designator_col]):
                continue
            designators = str(row[bom_designator_col]).split(',')
            comment = str(row[bom_comment_col]) if bom_comment_col and not pd.isna(row[bom_comment_col]) else ""
            for d in designators:
                d = d.strip()
                if d:
                    bom_map[_ref_key(d)] = comment
        
        # Создаем результат
        merged = []
        coord_mult = 25.4 if self.config.coord_unit_mils else 1.0
        
        for _, row in self._pnp_df.iterrows():
            if pnp_designator_col is None or pd.isna(row[pnp_designator_col]):
                continue
            
            ref = str(row[pnp_designator_col]).strip()
            if not ref:
                continue
            ref_key = _ref_key(ref)
            in_bom = ref_key in bom_map

            # Delete DNP in merge means "only keep placements found in BOM".
            if not include_dnp and not in_bom:
                continue
            
            # Value from BOM or PnP
            value = bom_map.get(ref_key, "")
            if not value:
                value = str(row[pnp_comment_col]) if pnp_comment_col and not pd.isna(row[pnp_comment_col]) else ""
            
            # Skip DNP
            if not include_dnp and value.upper() in ["DNP", "DNP_FROM_BOM"]:
                continue
            
            # Coordinates
            x = y = 0.0
            try:
                if pnp_x_col and not pd.isna(row[pnp_x_col]):
                    x = float(self._parse_coord(row[pnp_x_col]) or 0) * coord_mult
            except:
                pass
            try:
                if pnp_y_col and not pd.isna(row[pnp_y_col]):
                    y = float(self._parse_coord(row[pnp_y_col]) or 0) * coord_mult
            except:
                pass
            
            # Rotation
            rotation = ""
            if pnp_rot_col and not pd.isna(row[pnp_rot_col]):
                rotation = str(row[pnp_rot_col])
            
            # Layer
            layer = "Top"
            if pnp_layer_col and not pd.isna(row[pnp_layer_col]):
                layer = str(row[pnp_layer_col])
            
            # Footprint
            footprint = ""
            if pnp_fp_col and not pd.isna(row[pnp_fp_col]):
                footprint = str(row[pnp_fp_col])
            
            merged.append({
                "Ref": ref,
                "Value": value,
                "Footprint": footprint,
                "X": round(x, 3),
                "Y": round(y, 3),
                "Rotation": rotation,
                "Layer": layer
            })
        
        return pd.DataFrame(merged)
    
    def export_csv(self, df: pd.DataFrame, path: str) -> None:
        """Экспорт DataFrame в CSV"""
        df.to_csv(path, index=False, encoding='utf-8')
    
    def export_excel(self, df: pd.DataFrame, path: str) -> None:
        """Экспорт DataFrame в Excel"""
        df.to_excel(path, index=False, engine='openpyxl')


# ==============================================================================
# Helper Functions
# ==============================================================================

def _normalize_comment(comment: str) -> str:
    """
    Нормализует комментарий для сравнения.
    Обрезает после первого разделителя (, или |).
    """
    if not comment:
        return ""
    comment = str(comment).strip()
    # Обрезаем после первой запятой или вертикальной черты
    if ',' in comment:
        comment = comment.split(',')[0]
    if '|' in comment:
        comment = comment.split('|')[0]
    return comment.strip()


def _check_overlapping(pnp_parts: dict, min_distance: float, unit_is_mils: bool) -> list[tuple]:
    """
    Проверяет компоненты на перекрытие.
    
    Returns:
        Список (part1, part2, distance)
    """
    import math
    
    conflicts = []
    decoded_coords: dict[str, tuple] = {}
    checked: dict[str, list] = {}
    
    for key_a in pnp_parts:
        for key_b in pnp_parts:
            if key_a == key_b:
                continue
            
            # Уже проверяли?
            if key_a in checked.get(key_b, []):
                continue
            if key_b not in checked:
                checked[key_b] = []
            checked[key_b].append(key_a)
            
            # Одинаковый слой?
            pnp_data_a = pnp_parts.get(key_a, ())
            pnp_data_b = pnp_parts.get(key_b, ())
            layer_a = pnp_data_a[2] if len(pnp_data_a) > 2 else None
            layer_b = pnp_data_b[2] if len(pnp_data_b) > 2 else None
            
            coord_a = decoded_coords.get(key_a)
            if not coord_a and len(pnp_data_a) > 2 and pnp_data_a[2] is not None:
                try:
                    coord_a = (float(pnp_data_a[2] or 0), float(pnp_data_a[3] or 0) if len(pnp_data_a) > 3 else 0.0)
                    decoded_coords[key_a] = coord_a
                except:
                    continue
            
            coord_b = decoded_coords.get(key_b)
            if not coord_b and len(pnp_data_b) > 2 and pnp_data_b[2] is not None:
                try:
                    coord_b = (float(pnp_data_b[2] or 0), float(pnp_data_b[3] or 0) if len(pnp_data_b) > 3 else 0.0)
                    decoded_coords[key_b] = coord_b
                except:
                    continue
            
            if coord_a and coord_b:
                dist = math.sqrt((coord_a[0] - coord_b[0])**2 + (coord_a[1] - coord_b[1])**2)
                if 0 < dist < min_distance:
                    conflicts.append((key_a, key_b, round(dist, 1)))
    
    return conflicts


# ==============================================================================
# Quick Functions (for direct usage)
# ==============================================================================

def load_bom(path: str, **kwargs) -> pd.DataFrame:
    """Быстрая загрузка BOM"""
    config = ColumnConfig(
        designator=kwargs.get('designator', '?'),
        comment=kwargs.get('comment', '?'),
        first_row=kwargs.get('first_row', 0),
        has_header=kwargs.get('has_header', True)
    )
    return read_file(path, first_row=config.first_row)


def load_pnp(path: str, **kwargs) -> pd.DataFrame:
    """Быстрая загрузка PnP"""
    config = ColumnConfig(
        designator=kwargs.get('designator', '?'),
        comment=kwargs.get('comment', '?'),
        first_row=kwargs.get('first_row', 0),
        has_header=kwargs.get('has_header', True)
    )
    return read_file(path, first_row=config.first_row)
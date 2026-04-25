import pytest
import sys
import os

tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

import smt_processor


# ==============================================================================
# Test read_file - all formats
# ==============================================================================

def test_read_file_no_file():
    with pytest.raises(smt_processor.SMTFileNotFoundError):
        smt_processor.read_file("/nonexistent/file.xlsx")


def test_read_file_xlsx():
    path = os.path.join(tests_path, "assets", "bom.xlsx")
    df = smt_processor.read_file(path)
    assert not df.empty
    assert len(df.columns) > 0


@pytest.mark.skip(reason="xlrd doesn't support xlsx in Python 3.14")
def test_read_file_xls():
    path = os.path.join(tests_path, "assets", "bom.xls")
    df = smt_processor.read_file(path)
    assert not df.empty


def test_read_file_csv_comma():
    path = os.path.join(tests_path, "assets", "comma.csv")
    df = smt_processor.read_file(path, separator=",")
    assert not df.empty


def test_read_file_csv_tab():
    path = os.path.join(tests_path, "assets", "tabs.csv")
    df = smt_processor.read_file(path, separator="\t")
    assert not df.empty


def test_read_file_csv_auto():
    path = os.path.join(tests_path, "assets", "comma.csv")
    df = smt_processor.read_file(path, separator="auto")
    assert not df.empty


def test_read_file_first_row():
    path = os.path.join(tests_path, "assets", "comma.csv")
    df = smt_processor.read_file(path, first_row=1)
    assert not df.empty


def test_read_file_last_row():
    path = os.path.join(tests_path, "assets", "comma.csv")
    df = smt_processor.read_file(path, first_row=0, last_row=5)
    assert len(df) <= 5


# ==============================================================================
# Test ColumnConfig
# ==============================================================================

def test_column_config_defaults():
    cfg = smt_processor.ColumnConfig()
    assert cfg.designator == "?"
    assert cfg.comment == "?"
    assert cfg.has_header == True


def test_column_config_custom():
    cfg = smt_processor.ColumnConfig(
        designator="PartNumber",
        comment="Description",
        has_header=False
    )
    assert cfg.designator == "PartNumber"
    assert cfg.comment == "Description"
    assert cfg.has_header == False


# ==============================================================================
# Test ProcessorConfig
# ==============================================================================

def test_processor_config_defaults():
    cfg = smt_processor.ProcessorConfig()
    # Just check it has expected attributes
    assert hasattr(cfg, 'normalize_comments')
    assert hasattr(cfg, 'min_distance_mm')


# ==============================================================================
# Test SMTDataProcessor initialization
# ==============================================================================

def test_processor_init():
    proc = smt_processor.SMTDataProcessor(smt_processor.ProcessorConfig())
    assert proc is not None


def test_processor_set_dataframes():
    proc = smt_processor.SMTDataProcessor()
    
    bom_df = smt_processor.read_file(os.path.join(tests_path, "assets", "bom.xlsx"))
    pnp_df = smt_processor.read_file(os.path.join(tests_path, "assets", "bom.xlsx"))
    
    bom_cfg = smt_processor.ColumnConfig(designator="PartNumber", comment="Description")
    pnp_cfg = smt_processor.ColumnConfig(designator="PartNumber")
    
    proc.set_dataframes(bom_df, pnp_df, bom_cfg, pnp_cfg)
    
    assert proc._bom_df is not None
    assert proc._pnp_df is not None


def test_find_column_index():
    proc = smt_processor.SMTDataProcessor()
    
    test_df = __import__('pandas').DataFrame({
        'Designator': ['R1', 'R2'],
        'Value': ['100R', '220R'],
        'Package': ['0402', '0805']
    })
    
    # Test exact match
    idx = proc.find_column_index(test_df, "Designator", True)
    assert idx == 0
    
    # Test partial match
    idx = proc.find_column_index(test_df, "sign", True)
    assert idx == 0
    
    # Test with "_skip_" (should return -1)
    idx = proc.find_column_index(test_df, "_skip_", True)
    assert idx == -1
    
    # Test with "?" (should raise error)
    with pytest.raises(smt_processor.SMTColumnNotFoundError):
        proc.find_column_index(test_df, "?", True)


# ==============================================================================
# Test cross_check basic
# ==============================================================================

def test_cross_check_basic():
    proc = smt_processor.SMTDataProcessor()
    
    # Simple test BOM and PnP
    bom_df = __import__('pandas').DataFrame({
        'Designator': ['R1', 'R2', 'C1'],
        'Value': ['100R', '200R', '100nF']
    })
    pnp_df = __import__('pandas').DataFrame({
        'Designator': ['R1', 'R2', 'C1'],
        'Package': ['0402', '0805', '0603']
    })
    
    bom_cfg = smt_processor.ColumnConfig(designator="Designator", comment="Value")
    # Use _skip_ for optional PnP columns (no comment column)
    pnp_cfg = smt_processor.ColumnConfig(
        designator="Designator", 
        comment="_skip_",
        footprint="_skip_",
        coord_x="_skip_",
        coord_y="_skip_",
        rotation="_skip_",
        layer="_skip_"
    )
    
    proc.set_dataframes(bom_df, pnp_df, bom_cfg, pnp_cfg)
    result = proc.cross_check()
    
    assert result is not None
    assert len(result) > 0
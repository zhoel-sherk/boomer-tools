import pytest
import sys
import os

# adding src path to search list
tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(os.path.dirname(tests_path), "src"))

# tested module
import cross_check
import text_grid

# -----------------------------------------------------------------------------

def test_cross_check_result():
    # sourcery skip: extract-duplicate-method

    # check if every result uses it's own tables, not the shared, default created
    ccr1 = cross_check.CrossCheckResult()
    ccr1.bom_parst_missing_in_pnp.append(1)
    ccr1.pnp_parst_missing_in_bom.append(2)
    ccr1.parts_comment_mismatch.append(3)

    ccr2 = cross_check.CrossCheckResult()
    ccr2.bom_parst_missing_in_pnp.append("a")
    ccr2.pnp_parst_missing_in_bom.append("b")
    ccr2.parts_comment_mismatch.append("c")

    assert len(ccr1.bom_parst_missing_in_pnp) == 1
    assert len(ccr1.pnp_parst_missing_in_bom) == 1
    assert len(ccr1.parts_comment_mismatch) == 1
    assert ccr1.parts_comment_mismatch[0] == 3

    assert len(ccr2.bom_parst_missing_in_pnp) == 1
    assert len(ccr2.pnp_parst_missing_in_bom) == 1
    assert len(ccr2.parts_comment_mismatch) == 1
    assert ccr2.parts_comment_mismatch[0] == "c"

def test_no_bom():
    with pytest.raises(ValueError):
        cross_check.compare(None, None, None, False)


def test_no_pnp():
    with pytest.raises(ValueError):
        bom = text_grid.ConfiguredTextGrid()
        cross_check.compare(bom, None, None, False)

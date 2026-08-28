import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import store

def test_load_all_returns_expected_keys():
    data = store.load_all()
    assert set(data.keys()) == {"meta", "records", "scenarios", "credit_grids", "underwriting", "_lenders"}

def test_load_all_finds_known_lender():
    data = store.load_all()
    lenders = set(r["lender_canonical"] for r in data["records"])
    assert "CV3" in lenders
    assert "Constructive" in lenders

def test_load_all_record_shape():
    data = store.load_all()
    cv3_records = [r for r in data["records"] if r["lender_canonical"] == "CV3" and r["product"] == "sfr_dscr"]
    assert any(r["attr_name"] == "fico_requirement_at_max_ltv" for r in cv3_records)
    rec = next(r for r in cv3_records if r["attr_name"] == "fico_requirement_at_max_ltv")
    # value_numeric is NULL for this attribute in corpus.db (it's stored as
    # value_text only), so attr_value (COALESCE(value_numeric, value_text, ''))
    # comes back as the string "660.0", not the float 660.0.
    assert rec["attr_value"] == "660.0"
    assert rec["source_sheet"]
    assert rec["source_row"] == 28

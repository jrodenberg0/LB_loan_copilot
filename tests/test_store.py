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

def test_get_lender_records_filters_by_lender_and_product():
    recs = store.get_lender_records("CV3", "sfr_dscr")
    assert all(r["lender_canonical"] == "CV3" and r["product"] == "sfr_dscr" for r in recs)
    assert any(r["attr_name"] == "fico_requirement_at_max_ltv" for r in recs)

def test_get_lender_records_no_product_filter_returns_all_products():
    recs = store.get_lender_records("CV3")
    products = set(r["product"] for r in recs)
    assert "sfr_dscr" in products
    assert "fix_and_flip" in products

def test_get_lenders_index_has_products_list():
    idx = store.get_lenders_index()
    assert "CV3" in idx
    assert "sfr_dscr" in idx["CV3"]["products"]
    assert isinstance(idx["CV3"]["aliases"], list)

def test_get_scenarios_returns_conditions():
    scenarios = store.get_scenarios()
    assert len(scenarios) > 0
    assert all("condition" in s for s in scenarios)

def test_get_freshness_has_real_fields():
    fresh = store.get_freshness()
    assert "file_path" in fresh
    assert "file_mtime" in fresh
    assert "imported_at" in fresh
    assert "age_days" in fresh
    assert isinstance(fresh["age_days"], float)
    assert "n_records" in fresh and fresh["n_records"] > 0
    assert "n_lenders" in fresh and fresh["n_lenders"] > 0

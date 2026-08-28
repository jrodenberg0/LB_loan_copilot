import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import llm_parse


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point llm_parse at a scratch cache file so tests never mutate
    the real corpus/llm_cache.json."""
    monkeypatch.setattr(llm_parse, "CACHE_PATH", tmp_path / "llm_cache.json")


def test_parse_fico_ltv_tiers_uncached_fico_attr_returns_min_fico_tier():
    """Regression: parse_fico_ltv_tiers must recognize the CORRECT
    attribute name "fico_requirement_at_max_ltv" (not the legacy
    "fico_at_max_ltv") on the live-parse path (raw value not already
    in llm_cache.json). Without the fix, this falls through to the
    generic {"tiers": [{"value": val}]} shape with no min_fico key.
    """
    raw = "725"

    result = llm_parse.parse_fico_ltv_tiers(raw, attr_name="fico_requirement_at_max_ltv")

    assert result["tiers"], "expected at least one tier"
    assert "min_fico" in result["tiers"][0], (
        f"expected min_fico key in tier, got {result['tiers'][0]!r} — "
        "attribute name branch in _parse_fico_internal did not match"
    )
    assert result["tiers"][0]["min_fico"] == 725


def test_parse_fico_ltv_tiers_uncached_ltv_attr_returns_max_ltv_tier():
    """Same regression, for the max__ltv_purchase / max__ltv_cash_out_refi
    branch (formerly ltv_purchase_max / ltv_cashout_max)."""
    raw = "65"

    result = llm_parse.parse_fico_ltv_tiers(raw, attr_name="max__ltv_purchase")

    assert result["tiers"], "expected at least one tier"
    assert "max_ltv" in result["tiers"][0], (
        f"expected max_ltv key in tier, got {result['tiers'][0]!r} — "
        "attribute name branch in _parse_fico_internal did not match"
    )
    assert result["tiers"][0]["max_ltv"] == 65

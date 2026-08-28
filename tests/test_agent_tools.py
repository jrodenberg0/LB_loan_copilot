import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_tools import CreditBoxAgent

def test_get_lender_profile_returns_real_attrs():
    agent = CreditBoxAgent()
    profile = agent.get_lender_profile("CV3", "sfr_dscr")
    assert "error" not in profile
    assert "fico_requirement_at_max_ltv" in profile["products"]["sfr_dscr"]

def test_get_freshness_has_new_field_names():
    agent = CreditBoxAgent()
    fresh = agent.get_freshness()
    assert "age_days" in fresh
    assert "n_lenders" in fresh and fresh["n_lenders"] > 0

def test_no_credentials_leak_unflagged():
    agent = CreditBoxAgent()
    profile = agent.get_lender_profile("CV3", "sfr_dscr")
    for attr_name, info in profile["products"]["sfr_dscr"].items():
        if attr_name in ("user_name", "password"):
            assert info["sensitive"] is True

def test_check_criteria_fico_branch_fires():
    agent = CreditBoxAgent()
    result = agent.check_criteria("CV3", "sfr_dscr", {"fico": 700})
    # Before the fix, the FICO check silently never appended to result["checks"]
    # because it looked up a nonexistent attribute name ("fico_at_max_ltv").
    fico_checks = [c for c in result["checks"] if "FICO" in c["criterion"]]
    assert len(fico_checks) > 0
    assert fico_checks[0]["pass"] is True

def test_estimate_pricing_ltv_tier_notes_fire():
    agent = CreditBoxAgent()
    # ROC Capital/sfr_dscr has max__ltv_purchase (80%, min_fico 740) and
    # max__ltv_cash_out_refi (75%, min_fico 720) tiers in corpus.db.
    result = agent.estimate_pricing("ROC Capital", "sfr_dscr", ltv=75, fico=700)
    # Before the fix, LTV-tier notes never appeared because the lookup used
    # nonexistent attribute names ("ltv_purchase_max"/"ltv_cashout_max").
    assert any("max__ltv_purchase" in note for note in result["notes"])
    assert any("max__ltv_cash_out_refi" in note for note in result["notes"])

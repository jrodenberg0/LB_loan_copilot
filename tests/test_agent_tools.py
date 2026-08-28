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

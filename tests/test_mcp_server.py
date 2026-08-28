import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server


def test_find_lenders_tool_returns_matches():
    result = mcp_server.find_lenders("640 FICO Baltimore fix and flip")
    assert "matches" in result
    assert isinstance(result["matches"], list)


def test_get_lender_profile_tool():
    result = mcp_server.get_lender_profile("CV3", "sfr_dscr")
    assert "error" not in result


def test_ingest_excel_tool_rejects_missing_file():
    result = mcp_server.ingest_excel("/nonexistent/path.xlsx")
    assert "error" in result


def test_server_registers_all_ten_tools():
    tool_names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    expected = {
        "find_lenders", "get_lender_profile", "compare_lenders",
        "get_fico_ltv_tiers", "scenario_details", "get_freshness",
        "check_criteria", "estimate_pricing", "what_if", "ingest_excel",
    }
    assert expected <= tool_names

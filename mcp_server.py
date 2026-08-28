"""
Host-agnostic MCP server for credit-box-rag.

Exposes the 9 CreditBoxAgent tools plus ingest_excel (first-run setup).
This server has no knowledge of which host (Claude Code, Codex, or
anything else) is calling it — that's the point. Host-specific wiring
lives in .claude-plugin/ and codex/, not here.
"""

import subprocess, sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from agent_tools import CreditBoxAgent

ROOT = Path(__file__).parent
mcp = FastMCP("credit-box-rag")
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = CreditBoxAgent()
    return _agent


@mcp.tool()
def find_lenders(query: str, max_loan: int = None) -> dict:
    """Route a loan deal query. Returns ranked lenders with scores, reasoning, and source citations."""
    return _get_agent().find_lenders(query, max_loan=max_loan)


@mcp.tool()
def get_lender_profile(lender: str, product: str = None) -> dict:
    """All attributes for a lender, optionally filtered by product."""
    return _get_agent().get_lender_profile(lender, product)


@mcp.tool()
def compare_lenders(lender1: str, lender2: str, product: str = None) -> dict:
    """Side-by-side attribute comparison of two lenders."""
    return _get_agent().compare_lenders(lender1, lender2, product)


@mcp.tool()
def get_fico_ltv_tiers(lender: str, product: str = None) -> dict:
    """Structured FICO/LTV tier data for a lender."""
    return _get_agent().get_fico_ltv_tiers(lender, product)


@mcp.tool()
def scenario_details(scenario_text: str) -> dict:
    """Full recommendation text for a matched scenario rule."""
    return _get_agent().scenario_details(scenario_text)


@mcp.tool()
def get_freshness() -> dict:
    """Data age, source file, and record counts — use to warn if data is stale."""
    return _get_agent().get_freshness()


@mcp.tool()
def check_criteria(lender: str, product: str, criteria: dict) -> dict:
    """Check whether a lender meets specific deal criteria (FICO, state, etc)."""
    return _get_agent().check_criteria(lender, product, criteria)


@mcp.tool()
def estimate_pricing(lender: str, product: str, ltv: int = None, fico: int = None) -> dict:
    """Estimate rate/pricing for a lender given borrower params."""
    return _get_agent().estimate_pricing(lender, product, ltv=ltv, fico=fico)


@mcp.tool()
def what_if(params: dict) -> dict:
    """Re-route a deal with modified parameters. Returns updated matches."""
    return _get_agent().what_if(params)


@mcp.tool()
def ingest_excel(path: str) -> dict:
    """First-run setup: build corpus.db from a local Master Credit Box Excel file.

    Call this when get_freshness (or any other tool) errors with
    'Corpus DB not found' — ask the user for their Excel file's path,
    then call this tool with it.
    """
    excel_path = Path(path).expanduser()
    if not excel_path.exists():
        return {"error": f"File not found: {excel_path}"}

    result = subprocess.run(
        [sys.executable, str(ROOT / "migrate.py"), "--excel", str(excel_path)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if result.returncode != 0:
        return {"error": "migrate.py failed", "stderr": result.stderr[-2000:]}

    global _agent
    _agent = None  # force reload on next tool call, picking up the new corpus.db

    return {"status": "ok", "stdout": result.stdout[-2000:]}


if __name__ == "__main__":
    mcp.run()

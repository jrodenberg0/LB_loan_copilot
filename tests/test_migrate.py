import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl
from migrate import _first_lender_col

def _make_sheet(row1_values):
    """row1_values: list starting at column A. e.g. ["VOTE COLUMN", "Attr Label", "LenderA", "LenderB"]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(row1_values, start=1):
        ws.cell(row=1, column=i, value=v)
    return ws

def test_standard_layout_with_vote_column_starts_at_col_3():
    ws = _make_sheet(["VOTE COLUMN", None, "LenderA", "LenderB"])
    assert _first_lender_col(ws) == 3

def test_layout_missing_vote_column_starts_at_col_2():
    ws = _make_sheet([None, "Attr Label", "Stormfield", "LenderB"])
    # No "VOTE COLUMN" in column A -> lenders actually start one column
    # earlier than the standard layout assumes.
    assert _first_lender_col(ws) == 2

def test_vote_column_detection_is_case_insensitive():
    ws = _make_sheet(["vote column", None, "LenderA"])
    assert _first_lender_col(ws) == 3

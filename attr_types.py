"""
Attribute type definitions for Master Credit Box.

Explicitly typed for scoring-relevant attrs.
Heuristic fallback for the rest.
"""

import re

# Types: percent, number, dollar, date, boolean, json, text
SCORING_ATTRS = {
    # State / location
    "state_coverage": "json",
    "rural": "text",
    "rural_exclusion": "text",

    # FICO / credit
    "fico_min": "number",
    "fico_at_max_ltv": "number",
    "fico_qualification": "text",
    "max_lates": "number",
    "bk_fc_wait_years": "number",
    "bk_fc_in_x_years": "number",
    "tradeline_reqs": "text",
    "credit_pull": "text",
    "uses_loanbidz": "boolean",

    # LTV / loan structure
    "ltv_purchase_max": "percent",
    "ltv_cashout_max": "percent",
    "ltv_rateterm_max": "percent",
    "ltv_at_max_fico": "percent",
    "ltv_at_min_fico": "percent",
    "ltv_max": "percent",
    "ltc_max": "percent",
    "max_%_arv": "percent",
    "max_%_of_rehab": "percent",
    "max_%_as_completed_value": "percent",
    "max_%_of_purchase_(land)": "percent",
    "max_%_of_refinance_(as_is_value)": "percent",
    "max_%_of_construction_costs": "percent",
    "max_cashback_rateterm": "percent",
    "seller_second_allowed": "boolean",
    "seller_contribution_max": "percent",
    "wholesaler_assignment": "percent",
    "max_seller_concession": "percent",

    # DSCR / debt
    "dscr_range": "number",
    "dscr_min": "number",
    "dscr_max": "number",

    # Experience
    "experience_minimum": "number",
    "experience_minimum_(see_experience_cheat_sheet)": "text",
    "min_experience_for_max_ltc_arv": "number",
    "experience_lookback_period": "text",

    # Rates
    "rate_range": "text",
    "floor_rate": "percent",
    "lowest_rate_**": "percent",
    "lowest_rate_at_max_ltv": "percent",
    "lowest_rate_at_max_ltc_arv": "percent",
    "origination_fee": "percent",
    "uw_fee": "dollar",
    "processing_fee": "dollar",
    "other_fees": "text",
    "prepay_penalty": "text",
    "broker_comp": "text",
    "ysp_buyup": "text",
    "ysp_to_floor": "boolean",
    "ysp_or_interest_strip_available": "boolean",

    # Terms
    "term_months": "number",
    "fixed_period": "text",
    "amortization": "text",
    "io_available": "boolean",
    "payment": "text",
    "interest_based_on": "text",
    "days_to_close": "number",

    # Loan amounts
    "loan_min": "dollar",
    "loan_max": "dollar",
    "property_value_min": "dollar",
    "loan_amount": "dollar",
    "max_guarantor_exposure": "dollar",
    "minimum_initial_advance": "dollar",

    # Property types
    "max_#_of_units": "number",
    "min_units_per_loan": "number",
    "sfr_(1_unit)": "boolean",
    "2_4_units": "boolean",
    "condominiums": "text",
    "warrantable_condominiums": "text",
    "non_warrantable_condominiums": "text",
    "townhomes": "boolean",
    "multifamily": "text",
    "manufactured_homes_on_perm_foundation": "boolean",
    "mobile_homes_on_perm_foundation": "boolean",
    "commercial": "text",
    "mixed_use": "text",
    "mixed_use_or_commercial": "boolean",

    # Borrower
    "entity_types": "text",
    "foreign_nationals": "text",
    "non_recourse_available": "text",
    "occupancy": "text",
    "is_portfolio": "boolean",
    "portfolio": "boolean",
    "channels": "text",

    # Reserves
    "reserves_pitia_months": "number",
    "interest_reserve_(months)": "number",
    "interest_reserve_(months_required)": "number",
    "payment_reserve_months": "number",
    "payment_reserve_(months_required)": "number",
    "payment_reserve_(required)": "number",
    "asset_aging_months": "number",

    # Insurance
    "insurance__loss_of_rent": "number",
    "insurance__deductible": "dollar",
    "insurance__liability_coverage": "dollar",

    # Time-based
    "purchase_seasoning_months": "number",
    "delay_purchase_allowed_(months)": "number",
    "delayed_purchase_allowed_(months)": "number",
    "recent_purchase___rehab_cost_docs_mos": "number",
    "proof_of_rental_payments": "number",
    "#_months_banks_statements": "number",
    "credit_&_background": "number",
    "appraisal": "number",
    "title_commitment": "number",
    "cpl": "number",
    "condo_questionnaire": "number",
    "list_of_completed_rehab_from_the_last_12_months": "number",
    "tax_returns_years": "number",
    "track_record_doc_years": "number",
    "verification_of_rents_(months)": "number",
    "verification_of_rents": "number",
    "minimum_occupancy_requirement_%": "percent",
}


def guess_type(samples):
    """Heuristic type inference from sample values."""
    if not samples:
        return "text"
    clean = [str(s).strip().lower() for s in samples if s is not None and str(s).strip()]

    # Check if all are numeric
    nums = 0
    for v in clean:
        try:
            float(v.rstrip("%"))
            nums += 1
        except ValueError:
            pass
    if len(clean) > 0 and nums / len(clean) > 0.7:
        # Check if any have %
        if any("%" in v for v in clean):
            return "percent"
        # Check if any have $
        if any("$" in v for v in clean):
            return "dollar"
        # Check date-like
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')
        if any(date_pattern.search(v) for v in clean):
            return "date"
        return "number"

    # Boolean heuristics
    bool_vals = {"yes", "no", "y", "n", "true", "false", "n/a", "none", "na"}
    bool_count = sum(1 for v in clean if v in bool_vals)
    if len(clean) > 0 and bool_count / len(clean) > 0.6:
        return "boolean"

    return "text"


def get_type(attr_name, samples=None):
    """Get typed classification for an attribute."""
    if attr_name in SCORING_ATTRS:
        return SCORING_ATTRS[attr_name]
    if samples:
        return guess_type(samples)
    return "text"

"""Manual LLM judgment overrides for all unparseable/build-time-failed entries.

Uses my understanding (as the LLM) to fill gaps the pattern-based builder missed.
"""
import json
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "corpus" / "llm_cache.json"

# Load existing cache
cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

# ====================================================
# STATE COVERAGE OVERRIDES
# ====================================================

state_overrides = {
    "About Crebrid | Hard Money Lending Experts": {
        "type": "unknown",
        "included": [],
        "excluded": [],
        "notes": "Not a state coverage description; website text scraped into field",
        "raw": "About Crebrid | Hard Money Lending Experts"
    },
    "Non license states": {
        "type": "unknown",
        "included": [],
        "excluded": [],
        "notes": "References non-license state list elsewhere",
        "raw": "Non license states"
    },
    "m": {
        "type": "unknown",
        "included": [],
        "excluded": [],
        "notes": "Likely data fragment",
        "raw": "m"
    },
    # Additional tricky ones that regex likely got wrong
}

# ====================================================
# FICO/LTV OVERRIDES
# ====================================================

fico_overrides = {
    # ltv_purchase_max values
    '80% ($200K+ Value)\n75% (150K - $199,999)\n70% ($125K - $149,999 ER)': {
        "tiers": [
            {"max_ltv": 80, "min_loan_amount": 200000, "note": "$200K+ property value"},
            {"max_ltv": 75, "min_loan_amount": 150000, "max_loan_amount": 199999},
            {"max_ltv": 70, "min_loan_amount": 125000, "max_loan_amount": 149999, "note": "ER"},
        ],
        "note_type": "tiered",
        "notes": "3 LTV tiers based on property value",
        "raw": "80% ($200K+ Value)\n75% (150K - $199,999)\n70% ($125K - $149,999 ER)"
    },
    "80% (700+)": {
        "tiers": [{"max_ltv": 80, "min_fico": 700}],
        "note_type": "tiered",
        "notes": "80% LTV for 700+ FICO",
        "raw": "80% (700+)"
    },
    "80% (680+) to $1.5 MM": {
        "tiers": [{"max_ltv": 80, "min_fico": 680, "max_loan_amount": 1500000}],
        "note_type": "tiered",
        "notes": "80% LTV for 680+ FICO up to $1.5MM",
        "raw": "80% (680+) to $1.5 MM"
    },
    "80% (700+ FICO)": {
        "tiers": [{"max_ltv": 80, "min_fico": 700}],
        "note_type": "tiered",
        "notes": "80% LTV for 700+ FICO",
        "raw": "80% (700+ FICO)"
    },
    "80% (State Dependant)": {
        "tiers": [{"max_ltv": 80, "qualifier": "state_dependent"}],
        "note_type": "text",
        "notes": "80% LTV, state dependent",
        "raw": "80% (State Dependant)"
    },
    "70% (75%LTV for 1 - 4 Unit)": {
        "tiers": [{"max_ltv_cashout": 70, "max_ltv_purchase": 75, "property_type": "1-4 unit"}],
        "note_type": "tiered",
        "notes": "70% cashout, 75% purchase for 1-4 unit",
        "raw": "70% (75%LTV for 1 - 4 Unit)"
    },
    "75% (680+) to $1.5 MM": {
        "tiers": [{"max_ltv": 75, "min_fico": 680, "max_loan_amount": 1500000}],
        "note_type": "tiered",
        "notes": "75% LTV for 680+ FICO up to $1.5MM",
        "raw": "75% (680+) to $1.5 MM"
    },
    "75% (700+)": {
        "tiers": [{"max_ltv": 75, "min_fico": 700}],
        "note_type": "tiered",
        "notes": "75% LTV for 700+ FICO",
        "raw": "75% (700+)"
    },
    "70% (720+)": {
        "tiers": [{"max_ltv": 70, "min_fico": 720}],
        "note_type": "tiered",
        "notes": "70% LTV for 720+ FICO",
        "raw": "70% (720+)"
    },
    "75% (720+)": {
        "tiers": [{"max_ltv": 75, "min_fico": 720}],
        "note_type": "tiered",
        "notes": "75% LTV for 720+ FICO",
        "raw": "75% (720+)"
    },

    # fico_at_max_ltv values
    "700 c/o & 720 Purch/R&T": {
        "tiers": [
            {"min_fico": 700, "loan_type": "cash_out"},
            {"min_fico": 720, "loan_type": "purchase_rate_term"},
        ],
        "note_type": "tiered",
        "notes": "700 cash-out, 720 purchase/rate-term",
        "raw": "700 c/o & 720 Purch/R&T"
    },
    "700 (680-699 capped at 75LTV)": {
        "tiers": [
            {"min_fico": 700, "note": "unlimited"},
            {"min_fico": 680, "max_fico": 699, "max_ltv": 75},
        ],
        "note_type": "tiered",
        "notes": "700+ full; 680-699 capped at 75% LTV",
        "raw": "700 (680-699 capped at 75LTV)"
    },
    "720 (purchase) & 700 (rate/term & cash out)": {
        "tiers": [
            {"min_fico": 720, "loan_type": "purchase"},
            {"min_fico": 700, "loan_type": "rate_term_cash_out"},
        ],
        "note_type": "tiered",
        "notes": "720 purchase, 700 rate-term/cash-out",
        "raw": "720 (purchase) & 700 (rate/term & cash out)"
    },
    "725 for 80%": {
        "tiers": [{"min_fico": 725, "max_ltv": 80}],
        "note_type": "tiered",
        "notes": "725 FICO for 80% LTV",
        "raw": "725 for 80%"
    },
    "700 / 680": {
        "tiers": [
            {"min_fico": 700, "note": "target"},
            {"min_fico": 680, "note": "minimum"},
        ],
        "note_type": "tiered",
        "notes": "700 target FICO, 680 min",
        "raw": "700 / 680"
    },
    "700+": {
        "tiers": [{"min_fico": 700}],
        "note_type": "single_value",
        "notes": "FICO ≥700",
        "raw": "700+"
    },
    "680+": {
        "tiers": [{"min_fico": 680}],
        "note_type": "single_value",
        "notes": "FICO ≥680",
        "raw": "680+"
    },
    "620.0": {
        "tiers": [{"min_fico": 620}],
        "note_type": "single_value",
        "notes": "FICO ≥620",
        "raw": "620.0"
    },

    # fico_qualification values
    "Highest Mid Score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "Uses highest mid FICO score among borrowers",
        "raw": "Highest Mid Score"
    },
    "Highest Mid Score. higher FICO of partners (must have 20%)": {
        "tiers": [{"qualifier": "highest_mid", "note": "higher FICO of partners, must have 20%"}],
        "note_type": "text",
        "notes": "Highest mid score, higher FICO of partners with 20% ownership required",
        "raw": "Highest Mid Score. higher FICO of partners (must have 20%)"
    },
    "Mid Score, Lowest FICO of Partners (Must have 51% combined Ownership)": {
        "tiers": [{"qualifier": "mid_score", "note": "lowest FICO of partners, 51% ownership"}],
        "note_type": "text",
        "notes": "Mid score, lowest FICO of partners with 51% ownership",
        "raw": "Mid Score, Lowest FICO of Partners (Must have 51% combined Ownership)"
    },
    "soft pull (Equifax & Experian)-lower of the 2": {
        "tiers": [{"qualifier": "soft_pull_lower", "note": "Equifax & Experian, lower of the 2"}],
        "note_type": "text",
        "notes": "Soft pull Equifax & Experian, uses lower score",
        "raw": "soft pull (Equifax & Experian)-lower of the 2"
    },
    "Lowest FICO Score from Tri Merge": {
        "tiers": [{"qualifier": "lowest_tri_merge"}],
        "note_type": "text",
        "notes": "Lowest FICO score from tri-merge report",
        "raw": "Lowest FICO Score from Tri Merge"
    },
    "Lowest Mid Score (Average among all Owners) anyone with 10% or greater will get looked at": {
        "tiers": [{"qualifier": "lowest_mid_average", "note": "average among all owners with 10%+ ownership"}],
        "note_type": "text",
        "notes": "Lowest mid score averaged among owners with 10%+",
        "raw": "Lowest Mid Score (Average among all Owners) anyone with 10% or greater will get looked at"
    },
    "Lowest Mid Score of majority owner": {
        "tiers": [{"qualifier": "lowest_mid_majority"}],
        "note_type": "text",
        "notes": "Lowest mid score of majority owner",
        "raw": "Lowest Mid Score of majority owner"
    },
    "Highest Mid Score but all borrowers who have their credit pulled must qualify": {
        "tiers": [{"qualifier": "highest_mid", "note": "all borrowers must qualify"}],
        "note_type": "text",
        "notes": "Highest mid score but all borrowers with credit pulled must qualify",
        "raw": "Highest Mid Score but all borrowers who have their credit pulled must qualify"
    },
    "Highest Mid Score (all borrowers on loan must be 660+": {
        "tiers": [{"qualifier": "highest_mid", "min_fico": 660}],
        "note_type": "text",
        "notes": "Highest mid score, all borrowers must be 660+",
        "raw": "Highest Mid Score (all borrowers on loan must be 660+"
    },
    "Highest mid score of the tri-merge (partner llc)": {
        "tiers": [{"qualifier": "highest_mid_tri_merge"}],
        "note_type": "text",
        "notes": "Highest mid score of tri-merge for partner LLC",
        "raw": "Highest mid score of the tri-merge (partner llc)"
    },
    "Highest Mid Score. higher FICO of partners (must have 20%)": {
        "tiers": [{"qualifier": "highest_mid_higher_partner", "note": "higher FICO of partners, 20% ownership"}],
        "note_type": "text",
        "notes": "Highest mid, higher FICO of partners with 20%",
        "raw": "Highest Mid Score. higher FICO of partners (must have 20%)"
    },
    "Highest Mid Score: All >650": {
        "tiers": [{"qualifier": "highest_mid", "min_fico": 650}],
        "note_type": "text",
        "notes": "Highest mid score, all borrowers >650",
        "raw": "Highest Mid Score: All >650"
    },
    "Highest mid score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Highest mid score"
    },
    "Highest Score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Highest Score"
    },
    "High Mid Score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "High Mid Score"
    },
    "Higher Mid Score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Higher Mid Score"
    },
    "Highest Mid": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Highest Mid"
    },
    "Mid Score": {
        "tiers": [{"qualifier": "mid_score"}],
        "note_type": "text",
        "notes": "",
        "raw": "Mid Score"
    },
    "Mid score": {
        "tiers": [{"qualifier": "mid_score"}],
        "note_type": "text",
        "notes": "",
        "raw": "Mid score"
    },
    "Mid-score": {
        "tiers": [{"qualifier": "mid_score"}],
        "note_type": "text",
        "notes": "",
        "raw": "Mid-score"
    },
    "Midscore": {
        "tiers": [{"qualifier": "mid_score"}],
        "note_type": "text",
        "notes": "",
        "raw": "Midscore"
    },
    "Low mid": {
        "tiers": [{"qualifier": "low_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Low mid"
    },
    "Lowest Mid": {
        "tiers": [{"qualifier": "lowest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Lowest Mid"
    },
    "Lowest Mid Score": {
        "tiers": [{"qualifier": "lowest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Lowest Mid Score"
    },
    "soft pull Experian": {
        "tiers": [{"qualifier": "soft_pull_experian"}],
        "note_type": "text",
        "notes": "",
        "raw": "soft pull Experian"
    },
    "Mid FICO Score from Tri Merge": {
        "tiers": [{"qualifier": "mid_tri_merge"}],
        "note_type": "text",
        "notes": "",
        "raw": "Mid FICO Score from Tri Merge"
    },
    "Avg the 2 Mids": {
        "tiers": [{"qualifier": "avg_2_mids"}],
        "note_type": "text",
        "notes": "",
        "raw": "Avg the 2 Mids"
    },
    "1 Guarantor Only (Take Higher)": {
        "tiers": [{"qualifier": "guarantor_higher"}],
        "note_type": "text",
        "notes": "",
        "raw": "1 Guarantor Only (Take Higher)"
    },
    "Highest party mid score": {
        "tiers": [{"qualifier": "highest_mid"}],
        "note_type": "text",
        "notes": "",
        "raw": "Highest party mid score"
    },
    "Highest Mid score\nAll guarantors must have at least 20% ownership": {
        "tiers": [{"qualifier": "highest_mid", "note": "guarantors need 20% ownership"}],
        "note_type": "text",
        "notes": "Highest mid score, guarantors 20% ownership",
        "raw": "Highest Mid score\nAll guarantors must have at least 20% ownership"
    },

    # dscr_range values that need override
    '1.10 for max LTV. 1.00 to get 75%LTV to 680, 70% to 640 <1.0 DSCR to 65% LTV': {
        "tiers": [
            {"min_dscr": 1.10, "note": "max LTV"},
            {"min_dscr": 1.00, "max_ltv": 75, "min_fico": 680},
            {"max_ltv": 70, "min_fico": 640},
            {"min_dscr": 1.0, "max_ltv": 65, "condition": "below 1.0 DSCR"},
        ],
        "note_type": "tiered",
        "notes": "Kiavi: 1.10 max LTV; 1.00 → 75% to 680; 70% to 640; <1.0 → 65%",
        "raw": "1.10 for max LTV. 1.00 to get 75%LTV to 680, 70% to 640 <1.0 DSCR to 65% LTV"
    },
    '0.75x DSCR\n\n1.00 DSCR for $150k+ loan amounts.\n\n1.25 DSCR for $100k-$150k': {
        "tiers": [
            {"min_dscr": 0.75, "note": "minimum"},
            {"min_dscr": 1.00, "min_loan_amount": 150000},
            {"min_dscr": 1.25, "min_loan_amount": 100000, "max_loan_amount": 150000},
        ],
        "note_type": "tiered",
        "notes": "Silver Hill: 0.75 base, 1.00 for $150k+, 1.25 for $100-150k",
        "raw": "0.75x DSCR\n\n1.00 DSCR for $150k+ loan amounts.\n\n1.25 DSCR for $100k-$150k"
    },
    '1.10 Min  720+ FICO\n1.20 680-719 FICO': {
        "tiers": [
            {"min_dscr": 1.10, "min_fico": 720},
            {"min_dscr": 1.20, "min_fico": 680, "max_fico": 719},
        ],
        "note_type": "tiered",
        "notes": "LendingOne: 1.10 for 720+, 1.20 for 680-719",
        "raw": "1.10 Min  720+ FICO\n1.20 680-719 FICO"
    },
    '1.1 for 720+ FICO\n1.2 for <720 FICO\n< of 100% of Mkt Rents or Actual (Leased)\n90% of Mkt Rents (Vacant)': {
        "tiers": [
            {"min_dscr": 1.1, "min_fico": 720},
            {"min_dscr": 1.2, "max_fico": 719},
        ],
        "note_type": "tiered",
        "notes": "Archwest: 1.1 for 720+, 1.2 for <720",
        "raw": "1.1 for 720+ FICO\n1.2 for <720 FICO\n< of 100% of Mkt Rents or Actual (Leased)\n90% of Mkt Rents (Vacant)"
    },
    '.65-1.0 available,   1.1 for 720+ FICO\n1.2 for <720 FICO\n< of 110% of Mkt Rents or Actual (Leased)\n90% of Mkt Rents (Vacant)': {
        "tiers": [
            {"min_dscr": 0.65, "max_dscr": 1.0, "note": "available range"},
            {"min_dscr": 1.1, "min_fico": 720},
            {"min_dscr": 1.2, "max_fico": 719},
        ],
        "note_type": "tiered",
        "notes": "Constructive Expanded: 0.65-1.0 available, 1.1 for 720+, 1.2 for <720",
        "raw": ".65-1.0 available, 1.1 for 720+ FICO\n1.2 for <720 FICO"
    },
    'DSCR 1.10 Minimum 720+ FICO. 1.2 Min < 720.': {
        "tiers": [
            {"min_dscr": 1.10, "min_fico": 720},
            {"min_dscr": 1.2, "max_fico": 719},
        ],
        "note_type": "tiered",
        "notes": "RCN: 1.10 for 720+, 1.2 for <720",
        "raw": "DSCR 1.10 Minimum 720+ FICO. 1.2 Min < 720."
    },
    '1.0 Min FICO 700, min property value $250,000.\n1.2 if below 700 or property value below $250,000.': {
        "tiers": [
            {"min_dscr": 1.0, "min_fico": 700, "min_property_value": 250000},
            {"min_dscr": 1.2, "note": "if FICO <700 or property value <$250K"},
        ],
        "note_type": "tiered",
        "notes": "Lima One: 1.0 for 700+ FICO & $250K+; otherwise 1.2",
        "raw": "1.0 Min FICO 700, min property value $250,000.\n1.2 if below 700 or property value below $250,000."
    },
    '1.0 to get max LTV with 700+ FICO': {
        "tiers": [{"min_dscr": 1.0, "min_fico": 700, "note": "max LTV"}],
        "note_type": "tiered",
        "notes": "IceCap: 1.0 DSCR for max LTV with 700+ FICO",
        "raw": "1.0 to get max LTV with 700+ FICO"
    },
    'Min 1.0\nRate break at 1.20 DSCR': {
        "tiers": [
            {"min_dscr": 1.0, "note": "minimum"},
            {"min_dscr": 1.20, "note": "rate break"},
        ],
        "note_type": "tiered",
        "notes": "BPC: min 1.0, rate break at 1.20",
        "raw": "Min 1.0\nRate break at 1.20 DSCR"
    },
    '1.10, Exceptions to 1.0\n Refinances: \n 1.00 for <70%\n 1.15 for 75%': {
        "tiers": [
            {"min_dscr": 1.10, "note": "standard"},
            {"min_dscr": 1.0, "note": "exception"},
            {"loan_type": "refinance", "max_ltv": 70, "min_dscr": 1.00},
            {"loan_type": "refinance", "max_ltv": 75, "min_dscr": 1.15},
        ],
        "note_type": "tiered",
        "notes": "Conventus: 1.10 standard; refinance: 1.00 <70% LTV, 1.15 for 75%",
        "raw": "1.10, Exceptions to 1.0\n Refinances: \n 1.00 for <70%\n 1.15 for 75%"
    },
    'Investor 1.15x DSCR\n Owner-Occupied 1.20x DSCR': {
        "tiers": [
            {"min_dscr": 1.15, "occupancy": "investor"},
            {"min_dscr": 1.20, "occupancy": "owner_occupied"},
        ],
        "note_type": "tiered",
        "notes": "Silver Hill: 1.15 investor, 1.20 owner-occupied",
        "raw": "Investor 1.15x DSCR\n Owner-Occupied 1.20x DSCR"
    },
    '1.25 - 1.5 based on property type': {
        "tiers": [{"min_dscr": 1.25, "max_dscr": 1.5, "note": "varies by property type"}],
        "note_type": "tiered",
        "notes": "Apex: 1.25-1.5 based on property type",
        "raw": "1.25 - 1.5 based on property type"
    },
    '1.2 Standard,\n1.3 Small Mkt, 1.4 Very Small': {
        "tiers": [
            {"min_dscr": 1.2, "market": "standard"},
            {"min_dscr": 1.3, "market": "small"},
            {"min_dscr": 1.4, "market": "very_small"},
        ],
        "note_type": "tiered",
        "notes": "ROC: 1.2 standard, 1.3 small market, 1.4 very small",
        "raw": "1.2 Standard,\n1.3 Small Mkt, 1.4 Very Small"
    },
    'Minimum DSCR: 1.15x (amortization); 1.20x (interest-only)': {
        "tiers": [
            {"min_dscr": 1.15, "amortization": "amortizing"},
            {"min_dscr": 1.20, "amortization": "interest_only"},
        ],
        "note_type": "tiered",
        "notes": "Verus: 1.15 amortizing, 1.20 interest-only",
        "raw": "Minimum DSCR: 1.15x (amortization); 1.20x (interest-only)"
    },
    'NA for 12 month Term\n  1.0 for 24 month Term': {
        "tiers": [
            {"term_months": 12, "note": "N/A for 12-month"},
            {"min_dscr": 1.0, "term_months": 24},
        ],
        "note_type": "tiered",
        "notes": "Civic: N/A for 12mo, 1.0 for 24mo term",
        "raw": "NA for 12 month Term\n  1.0 for 24 month Term"
    },
    '1.20 / 1.15': {
        "tiers": [{"min_dscr": 1.15, "max_dscr": 1.20}],
        "note_type": "tiered",
        "notes": "DSCR 1.15-1.20",
        "raw": "1.20 / 1.15"
    },
    '0.75,  1.0+ to get standard pricing': {
        "tiers": [
            {"min_dscr": 0.75, "note": "minimum"},
            {"min_dscr": 1.0, "note": "standard pricing"},
        ],
        "note_type": "tiered",
        "notes": "EasyStreet: 0.75 min, 1.0+ for standard pricing",
        "raw": "0.75,  1.0+ to get standard pricing"
    },
    '.8 Min, but 1.0 for max LTV.\n< of Mkt Rents or actual.  Up to 125% of Mkt Rents can be used with 3 month rent receipts.': {
        "tiers": [
            {"min_dscr": 0.8, "note": "minimum"},
            {"min_dscr": 1.0, "note": "for max LTV"},
        ],
        "note_type": "tiered",
        "notes": "Truly Investor: 0.8 min, 1.0 for max LTV",
        "raw": ".8 Min, but 1.0 for max LTV.\n< of Mkt Rents or actual.  Up to 125% of Mkt Rents can be used with 3 month rent receipts."
    },
    '1.00 / 1.25': {
        "tiers": [{"min_dscr": 1.00, "max_dscr": 1.25}],
        "note_type": "tiered",
        "notes": "DSCR 1.00-1.25",
        "raw": "1.00 / 1.25"
    },
    'Gross Rents x .90 to 1.0. Interest Taxes Insurance HOA.': {
        "tiers": [{"qualifier": "gross_rents_formula", "note": "Gross Rents x 0.90 to 1.0, less ITIH"}],
        "note_type": "text",
        "notes": "Civic: gross rents × 0.90 to 1.0 minus taxes/insurance/HOA",
        "raw": "Gross Rents x .90 to 1.0. Interest Taxes Insurance HOA."
    },

    # ltv values with nested conditions
    '75% to 720, 70% to 700, 65% to 680, 60% to 660': {
        "tiers": [
            {"max_ltv": 75, "min_fico": 720},
            {"max_ltv": 70, "min_fico": 700},
            {"max_ltv": 65, "min_fico": 680},
            {"max_ltv": 60, "min_fico": 660},
        ],
        "note_type": "tiered",
        "notes": "ltv_cashout_max: 75/70/65/60 for 720/700/680/660 FICO",
        "raw": "75% to 720, 70% to 700, 65% to 680, 60% to 660"
    },
    '75%: 740+, 70%: 700+, 65% else': {
        "tiers": [
            {"max_ltv": 75, "min_fico": 740},
            {"max_ltv": 70, "min_fico": 700},
            {"max_ltv": 65, "condition": "else"},
        ],
        "note_type": "tiered",
        "notes": "ltv_cashout_max: 75% for 740+, 70% for 700+, 65% else",
        "raw": "75%: 740+, 70%: 700+, 65% else"
    },
    '80% to 740, 75% to 700, 70% to 680, 65% to 660': {
        "tiers": [
            {"max_ltv": 80, "min_fico": 740},
            {"max_ltv": 75, "min_fico": 700},
            {"max_ltv": 70, "min_fico": 680},
            {"max_ltv": 65, "min_fico": 660},
        ],
        "note_type": "tiered",
        "notes": "ltv_purchase_max: 80/75/70/65 for 740/700/680/660 FICO",
        "raw": "80% to 740, 75% to 700, 70% to 680, 65% to 660"
    },
    '80%: 740+, 75%: 700+, 70% else': {
        "tiers": [
            {"max_ltv": 80, "min_fico": 740},
            {"max_ltv": 75, "min_fico": 700},
            {"max_ltv": 70, "condition": "else"},
        ],
        "note_type": "tiered",
        "notes": "ltv_purchase_max: 80% for 740+, 75% for 700+, 70% else",
        "raw": "80%: 740+, 75%: 700+, 70% else"
    },
    '80% LTC': {
        "tiers": [{"max_ltc": 80}],
        "note_type": "single_value",
        "notes": "80% LTC (loan-to-cost)",
        "raw": "80% LTC"
    },
    '75% LTC': {
        "tiers": [{"max_ltc": 75}],
        "note_type": "single_value",
        "notes": "75% LTC (loan-to-cost)",
        "raw": "75% LTC"
    },
    '70% (75%LTV for 1 - 4 Unit)': {
        "tiers": [{"max_ltv_cashout": 70, "max_ltv_purchase_1_4": 75}],
        "note_type": "tiered",
        "notes": "70% cashout, 75% for 1-4 unit purchase",
        "raw": "70% (75%LTV for 1 - 4 Unit)"
    },
    '70% (75%LTV for 1 Unit)': {
        "tiers": [{"max_ltv_cashout": 70, "max_ltv_purchase_1": 75}],
        "note_type": "tiered",
        "notes": "70% cashout, 75% for 1 unit purchase",
        "raw": "70% (75%LTV for 1 Unit)"
    },
    '70% (Max $250K Cash Out)': {
        "tiers": [{"max_ltv_cashout": 70, "max_cashout_amount": 250000}],
        "note_type": "tiered",
        "notes": "70% LTV cashout, max $250K cash out",
        "raw": "70% (Max $250K Cash Out)"
    },
    '60% (Max $250K Cash Out)': {
        "tiers": [{"max_ltv_cashout": 60, "max_cashout_amount": 250000}],
        "note_type": "tiered",
        "notes": "60% LTV cashout, max $250K cash out",
        "raw": "60% (Max $250K Cash Out)"
    },
    '70% (1.3 DSCR Required)': {
        "tiers": [{"max_ltv_cashout": 70, "min_dscr": 1.3}],
        "note_type": "tiered",
        "notes": "70% cashout with 1.3 DSCR required",
        "raw": "70% (1.3 DSCR Required)"
    },
    '60% land': {
        "tiers": [{"max_ltv": 60, "property_type": "land"}],
        "note_type": "single_value",
        "notes": "60% LTV for land",
        "raw": "60% land"
    },
    '65%-70%': {
        "tiers": [{"min_ltv": 65, "max_ltv": 70}],
        "note_type": "single_value",
        "notes": "LTV 65-70%",
        "raw": "65%-70%"
    },
    '75% / 80%': {
        "tiers": [{"min_ltv": 75, "max_ltv": 80}],
        "note_type": "single_value",
        "notes": "LTV 75-80%",
        "raw": "75% / 80%"
    },
    '75% - 80%': {
        "tiers": [{"min_ltv": 75, "max_ltv": 80}],
        "note_type": "single_value",
        "notes": "LTV 75-80%",
        "raw": "75% - 80%"
    },
    '75% Multi,  65% Commercial': {
        "tiers": [
            {"max_ltv": 75, "property_type": "multifamily"},
            {"max_ltv": 65, "property_type": "commercial"},
        ],
        "note_type": "tiered",
        "notes": "75% multifamily, 65% commercial",
        "raw": "75% Multi,  65% Commercial"
    },
    '75%, 85% BLTC': {
        "tiers": [{"max_ltv": 75, "max_bltc": 85}],
        "note_type": "tiered",
        "notes": "75% LTV, 85% BLTC",
        "raw": "75%, 85% BLTC"
    },
    '75.0': {
        "tiers": [{"max_ltv": 75}],
        "note_type": "single_value",
        "notes": "75% LTV",
        "raw": "75.0"
    },
    '85% LTC': {
        "tiers": [{"max_ltc": 85}],
        "note_type": "single_value",
        "notes": "85% LTC",
        "raw": "85% LTC"
    },

    # Complex tiered purchase values
    '(Double Double)-90% (2+ Exp in 36 mos and 30% return)\n (Standard & BNPL)80% if less than 2\n85% LTC all others\nAltitdue 1 or more 90%': {
        "tiers": [
            {"max_ltv": 90, "experience": 2, "note": "Double Double: 2+ exp in 36mo and 30% return"},
            {"max_ltv": 80, "experience": 1, "note": "Standard & BNPL: 80% if <2 exp"},
            {"max_ltc": 85, "note": "all others"},
            {"max_ltv": 90, "experience": 1, "note": "Altitude: 1+ exp"},
        ],
        "note_type": "tiered",
        "notes": "Complex tiering based on experience and program",
        "raw": "(Double Double)-90% (2+ Exp in 36 mos and 30% return)\n (Standard & BNPL)80% if less than 2\n85% LTC all others\nAltitdue 1 or more 90%"
    },
    '90%(100% w extra colleratal)': {
        "tiers": [{"max_ltv": 90, "note": "100% with extra collateral"}],
        "note_type": "text",
        "notes": "90% LTV, 100% with extra collateral",
        "raw": "90%(100% w extra colleratal)"
    },
    '90%: (680+ FICO) and 5+ Rehabs\n75% No Rehab': {
        "tiers": [
            {"max_ltv": 90, "min_fico": 680, "experience": 5, "note": "90% for 680+ FICO and 5+ rehabs"},
            {"max_ltv": 75, "note": "no rehab experience"},
        ],
        "note_type": "tiered",
        "notes": "90% for experienced (680+, 5+), 75% for no rehab",
        "raw": "90%: (680+ FICO) and 5+ Rehabs\n75% No Rehab"
    },
    '90%: 4+ Experience\n85%: 2-3 Experience\n80%: 0-1 Experience': {
        "tiers": [
            {"max_ltv": 90, "experience": 4},
            {"max_ltv": 85, "experience": 2, "max_experience": 3},
            {"max_ltv": 80, "experience": 0, "max_experience": 1},
        ],
        "note_type": "tiered",
        "notes": "LTV based on experience: 90% for 4+, 85% for 2-3, 80% for 0-1",
        "raw": "90%: 4+ Experience\n85%: 2-3 Experience\n80%: 0-1 Experience"
    },
    '95% with 5+ exp, 92.5% with 3+': {
        "tiers": [
            {"max_ltv": 95, "experience": 5},
            {"max_ltv": 92.5, "experience": 3},
        ],
        "note_type": "tiered",
        "notes": "95% for 5+ exp, 92.5% for 3+ exp",
        "raw": "95% with 5+ exp, 92.5% with 3+"
    },
    'No Experience: 75/80/65\n2-5 Exp: 80/90/70\n5+ Exp: 80/100/75': {
        "tiers": [
            {"experience": 0, "max_purchase": 75, "max_ltc": 80, "max_cashout": 65},
            {"experience": 2, "max_experience": 5, "max_purchase": 80, "max_ltc": 90, "max_cashout": 70},
            {"experience": 5, "max_purchase": 80, "max_ltc": 100, "max_cashout": 75},
        ],
        "note_type": "tiered",
        "notes": "Purchase/LTC/Cashout tiers by experience level",
        "raw": "No Experience: 75/80/65\n2-5 Exp: 80/90/70\n5+ Exp: 80/100/75"
    },
    'A Tier: 90%/100%/75% \n(720 FICO + 10 Ever Flips or Rentals)\nB Tier: 85%/100%/70% \n(720 FICO + 3 Exp or 680 + 10 Exp)\nCan do 85% LTC': {
        "tiers": [
            {"tier": "A", "max_purchase": 90, "max_ltc": 100, "max_cashout": 75,
             "min_fico": 720, "experience": 10},
            {"tier": "B", "max_purchase": 85, "max_ltc": 100, "max_cashout": 70,
             "note": "720 FICO + 3 exp or 680 + 10 exp"},
            {"max_ltc": 85},
        ],
        "note_type": "tiered",
        "notes": "A/B tiered pricing by FICO and experience",
        "raw": "A Tier: 90%/100%/75% \n(720 FICO + 10 Ever Flips or Rentals)\nB Tier: 85%/100%/70% \n(720 FICO + 3 Exp or 680 + 10 Exp)\nCan do 85% LTC"
    },
    'A Tier: 90%/100%/75% \n(720 FICO + 10 Ever Flips or Rentals)\nB Tier: 85%/100%/70% \n(720 FICO + 3 Exp or 680 + 10 Exp)\nCan do 85% LTC ': {
        "tiers": [
            {"tier": "A", "max_purchase": 90, "max_ltc": 100, "max_cashout": 75,
             "min_fico": 720, "experience": 10},
            {"tier": "B", "max_purchase": 85, "max_ltc": 100, "max_cashout": 70,
             "note": "720 FICO + 3 exp or 680 + 10 exp"},
            {"max_ltc": 85},
        ],
        "note_type": "tiered",
        "notes": "A/B tiered pricing by FICO and experience",
        "raw": "A Tier: 90%/100%/75% \n(720 FICO + 10 Ever Flips or Rentals)\nB Tier: 85%/100%/70% \n(720 FICO + 3 Exp or 680 + 10 Exp)\nCan do 85% LTC"
    },
    '90/100/90/75': {
        "tiers": [{"note": "values likely purchase/LTC/other/cashout", "v1": 90, "v2": 100, "v3": 90, "v4": 75}],
        "note_type": "text",
        "notes": "Compound ratio values: 90/100/90/75",
        "raw": "90/100/90/75"
    },
    '~90% purchase 90% LTC': {
        "tiers": [{"max_ltv": 90, "max_ltc": 90}],
        "note_type": "single_value",
        "notes": "~90% purchase, 90% LTC",
        "raw": "~90% purchase 90% LTC"
    },
    'Platinum: 5+  85% Light, 80% Heavy\n(90% available for 740+ FICO Purch)\nGold: 3-4  85% Light, 80% Heavy\nSilver: 1-2  80% Light, NA He': {
        "tiers": [
            {"tier": "Platinum", "experience": 5, "max_ltv_light": 85, "max_ltv_heavy": 80, "note": "90% for 740+ FICO purchase"},
            {"tier": "Gold", "experience": 3, "max_experience": 4, "max_ltv_light": 85, "max_ltv_heavy": 80},
            {"tier": "Silver", "experience": 1, "max_experience": 2, "max_ltv_light": 80},
        ],
        "note_type": "tiered",
        "notes": "Platinum/Gold/Silver tiered LTV by experience and light/heavy rehab",
        "raw": "Platinum: 5+  85% Light, 80% Heavy\n(90% available for 740+ FICO Purch)\nGold: 3-4  85% Light, 80% Heavy\nSilver: 1-2  80% Light, NA He"
    },
    'Platinum: 6+  90/100/75 Light, 85/100/75 Heavy\nGold: 3-5  85/100/75 Light, 75/100/75 Heavy\nSilver: 1-2  80/100/70 Light, 70/100/70 H': {
        "tiers": [
            {"tier": "Platinum", "experience": 6, "light": "90/100/75", "heavy": "85/100/75"},
            {"tier": "Gold", "experience": 3, "max_experience": 5, "light": "85/100/75", "heavy": "75/100/75"},
            {"tier": "Silver", "experience": 1, "max_experience": 2, "light": "80/100/70", "heavy": "70/100/70"},
        ],
        "note_type": "tiered",
        "notes": "Platinum/Gold/Silver tiered Purchase/LTC/Cashout by experience and light/heavy",
        "raw": "Platinum: 6+  90/100/75 Light, 85/100/75 Heavy\nGold: 3-5  85/100/75 Light, 75/100/75 Heavy\nSilver: 1-2  80/100/70 Light, 70/100/70 H"
    },
    'Tier 1: 0 exits, no loan\nTier 2: 1 exit (sell or refinance) 85% total LTC max \nTier 3: 3 exits (sell or refinance) 90% total LTC max': {
        "tiers": [
            {"tier": 1, "experience": 0, "note": "no loan"},
            {"tier": 2, "experience": 1, "max_ltc": 85},
            {"tier": 3, "experience": 3, "max_ltc": 90},
        ],
        "note_type": "tiered",
        "notes": "Tiered by exits (flips completed): no exits = no loan, 1 exit = 85% LTC, 3 exits = 90% LTC",
        "raw": "Tier 1: 0 exits, no loan\nTier 2: 1 exit (sell or refinance) 85% total LTC max \nTier 3: 3 exits (sell or refinance) 90% total LTC max"
    },
    '90% to cost basis @ 11.99%': {
        "tiers": [{"max_ltv": 90, "rate": 11.99, "note": "90% to cost basis"}],
        "note_type": "tiered",
        "notes": "90% LTV to cost basis at 11.99% rate",
        "raw": "90% to cost basis @ 11.99%"
    },
    '75% (700+)': {
        "tiers": [{"max_ltv": 75, "min_fico": 700}],
        "note_type": "tiered",
        "notes": "75% LTV for 700+ FICO",
        "raw": "75% (700+)"
    },
    '0.85': {
        "tiers": [{"max_ltv": 85}],
        "note_type": "single_value",
        "notes": "85% LTV",
        "raw": "0.85"
    },
    '0.75': {
        "tiers": [{"max_ltv": 75}],
        "note_type": "single_value",
        "notes": "75% LTV",
        "raw": "0.75"
    },
    '0.65': {
        "tiers": [{"max_ltv": 65}],
        "note_type": "single_value",
        "notes": "65% LTV",
        "raw": "0.65"
    },
    '0.45': {
        "tiers": [{"max_ltv": 45}],
        "note_type": "single_value",
        "notes": "45% LTV",
        "raw": "0.45"
    },
    '620.0': {
        "tiers": [{"min_fico": 620}],
        "note_type": "single_value",
        "notes": "FICO ≥620",
        "raw": "620.0"
    },
    '640.0': {
        "tiers": [{"min_fico": 640}],
        "note_type": "single_value",
        "notes": "FICO ≥640",
        "raw": "640.0"
    },
    '650.0': {
        "tiers": [{"min_fico": 650}],
        "note_type": "single_value",
        "notes": "FICO ≥650",
        "raw": "650.0"
    },
    '660.0': {
        "tiers": [{"min_fico": 660}],
        "note_type": "single_value",
        "notes": "FICO ≥660",
        "raw": "660.0"
    },
    '675.0': {
        "tiers": [{"min_fico": 675}],
        "note_type": "single_value",
        "notes": "FICO ≥675",
        "raw": "675.0"
    },
    '680.0': {
        "tiers": [{"min_fico": 680}],
        "note_type": "single_value",
        "notes": "FICO ≥680",
        "raw": "680.0"
    },
    '700.0': {
        "tiers": [{"min_fico": 700}],
        "note_type": "single_value",
        "notes": "FICO ≥700",
        "raw": "700.0"
    },
    '710.0': {
        "tiers": [{"min_fico": 710}],
        "note_type": "single_value",
        "notes": "FICO ≥710",
        "raw": "710.0"
    },
    '720.0': {
        "tiers": [{"min_fico": 720}],
        "note_type": "single_value",
        "notes": "FICO ≥720",
        "raw": "720.0"
    },
    '740.0': {
        "tiers": [{"min_fico": 740}],
        "note_type": "single_value",
        "notes": "FICO ≥740",
        "raw": "740.0"
    },
    '800.0': {
        "tiers": [{"min_fico": 800}],
        "note_type": "single_value",
        "notes": "FICO ≥800",
        "raw": "800.0"
    },
    '620.0\nNote:': {
        "tiers": [{"min_fico": 620}],
        "note_type": "single_value",
        "notes": "",
        "raw": "620.0\nNote:"
    },
    '640.0\nNote:': {
        "tiers": [{"min_fico": 640}],
        "note_type": "single_value",
        "notes": "",
        "raw": "640.0\nNote:"
    },
    '660.0\nNote:': {
        "tiers": [{"min_fico": 660}],
        "note_type": "single_value",
        "notes": "",
        "raw": "660.0\nNote:"
    },
    '700.0\nNote:': {
        "tiers": [{"min_fico": 700}],
        "note_type": "single_value",
        "notes": "",
        "raw": "700.0\nNote:"
    },
    '720.0\nNote:': {
        "tiers": [{"min_fico": 720}],
        "note_type": "single_value",
        "notes": "",
        "raw": "720.0\nNote:"
    },
    '740.0\nNote:': {
        "tiers": [{"min_fico": 740}],
        "note_type": "single_value",
        "notes": "",
        "raw": "740.0\nNote:"
    },
    'no': {
        "tiers": [{"qualifier": "none"}],
        "note_type": "text",
        "notes": "No FICO requirement stated",
        "raw": "no"
    },
    'n': {
        "tiers": [{"qualifier": "none"}],
        "note_type": "text",
        "notes": "No FICO requirement stated",
        "raw": "n"
    },
    'No Min': {
        "tiers": [{"qualifier": "no_min"}],
        "note_type": "text",
        "notes": "No minimum",
        "raw": "No Min"
    },
    'No Ratio': {
        "tiers": [{"qualifier": "no_ratio"}],
        "note_type": "text",
        "notes": "No DSCR ratio required",
        "raw": "No Ratio"
    },
    'No Ratio. Comm& Multi >$700K+ 1.2': {
        "tiers": [
            {"qualifier": "no_ratio", "note": "general"},
            {"min_dscr": 1.2, "property_type": "commercial_multi", "loan_amount": 700000},
        ],
        "note_type": "tiered",
        "notes": "Velocity: No ratio for most; 1.2 for commercial/multi over $700K",
        "raw": "No Ratio. Comm& Multi >$700K+ 1.2"
    },
    'Min 1.0, No DSCR available': {
        "tiers": [{"min_dscr": 1.0}],
        "note_type": "text",
        "notes": "Min 1.0, no DSCR option available",
        "raw": "Min 1.0, No DSCR available"
    },
    'Rents above Market Rents OK up to 120% of 1007 amount.\n1.0 DSCR   lesser of mkt vs in-place.... refi, use rent range OR 1007. would need t': {
        "tiers": [{"min_dscr": 1.0}],
        "note_type": "text",
        "notes": "CV3: 1.0 DSCR, rents up to 120% of 1007 amount",
        "raw": "Rents above Market Rents OK up to 120% of 1007 amount.\n1.0 DSCR   lesser of mkt vs in-place.... refi, use rent range OR 1007. would need t"
    },
    '1.1 \n< of 100% of Mkt Rents or Actual (Leased)\n90% of Mkt Rents (Vacant)': {
        "tiers": [{"min_dscr": 1.1}],
        "note_type": "single_value",
        "notes": "1.1 DSCR with market rent calculations",
        "raw": "1.1 \n< of 100% of Mkt Rents or Actual (Leased)\n90% of Mkt Rents (Vacant)"
    },
    '1.0\n(Vacant Purchase Units qualify at 95% of Mkt Rents)': {
        "tiers": [{"min_dscr": 1.0}],
        "note_type": "single_value",
        "notes": "1.0 DSCR, vacant purchase at 95% market rents",
        "raw": "1.0\n(Vacant Purchase Units qualify at 95% of Mkt Rents)"
    },
    'Case by Case': {
        "tiers": [{"qualifier": "case_by_case"}],
        "note_type": "text",
        "notes": "DSCR determined case by case",
        "raw": "Case by Case"
    },
    '.90x DSCR': {
        "tiers": [{"min_dscr": 0.90}],
        "note_type": "single_value",
        "notes": "DSCR ≥0.90",
        "raw": ".90x DSCR"
    },
    '.85 PDTI \n  (6% Rent Haircut)': {
        "tiers": [{"min_pdti": 0.85, "note": "6% rent haircut"}],
        "note_type": "text",
        "notes": "85% PDTI with 6% rent haircut",
        "raw": ".85 PDTI \n  (6% Rent Haircut)"
    },
    '1.20 DSCR': {
        "tiers": [{"min_dscr": 1.20}],
        "note_type": "single_value",
        "notes": "DSCR ≥1.20",
        "raw": "1.20 DSCR"
    },
    '1.30 DSCR': {
        "tiers": [{"min_dscr": 1.30}],
        "note_type": "single_value",
        "notes": "DSCR ≥1.30",
        "raw": "1.30 DSCR"
    },
    '1.25 - 1.35': {
        "tiers": [{"min_dscr": 1.25, "max_dscr": 1.35}],
        "note_type": "tiered",
        "notes": "DSCR 1.25-1.35",
        "raw": "1.25 - 1.35"
    },
}

# Merge overrides into cache
for k, v in state_overrides.items():
    cache[f"state_coverage::{k}"] = v

for k, v in fico_overrides.items():
    cache[f"fico_ltv::{k}"] = v

# Write
CACHE_PATH.write_text(json.dumps(cache, indent=2, default=str))
print(f"Wrote {len(cache)} entries to cache ({len(state_overrides)} state + {len(fico_overrides)} fico overrides)")

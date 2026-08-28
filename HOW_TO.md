# How To: Loan-Pricing Partner Agent

## Setup

```bash
cd ~/Desktop/credit-box-rag
```

## Quick Start

```bash
# Route a deal
python3 query.py "640 FICO Baltimore fix and flip, 1 prior flip"

# With loan amount filter
python3 query.py "700 FICO Chicago DSCR cash-out"

# Check data freshness
python3 query.py --freshness

# Show all available scenarios
python3 query.py --list-scenarios

# Profile a lender
python3 query.py --show-lender "Constructive"

# Compare two lenders
python3 query.py --compare "Constructive" "CV3" --product sfr_dscr

# View tier tables for a lender
python3 query.py --show-tiers "Conventus" sfr_dscr
```

## Conversation Mode

Run queries — state persists in `~/.credit-box/state.json`:

```bash
python3 query.py "640 FICO Baltimore fix and flip"
# → see top 3 lenders

python3 query.py "make it 700 FICO"        # refinement — replaces FICO
python3 query.py "what about higher LTV"    # appends to last query
python3 query.py !show 1                    # deep-dive first result
python3 query.py !show 2                    # deep-dive second result
python3 query.py !compare 1 3               # side-by-side first vs third
python3 query.py !not Groundfloor           # re-query excluding Groundfloor
python3 query.py !history                   # recent queries
python3 query.py !clear                     # reset
```

## Agent Tool API (for LLM orchestration)

```python
from agent_tools import CreditBoxAgent

agent = CreditBoxAgent()

# Route deal — with max_loan filter built-in
agent.find_lenders("640 FICO Baltimore fix and flip", max_loan=2_000_000)

# Get full profile
agent.get_lender_profile("Kiavi", "fix_and_flip")

# Compare
agent.compare_lenders("Constructive", "CV3", "sfr_dscr")

# Pricing estimate
agent.estimate_pricing("Conventus", "sfr_dscr", ltv=75, fico=720)

# Check specific criteria
agent.check_criteria("Hard Money Co", "fix_and_flip", {"fico": 600})

# Scenario docs
agent.scenario_details("Baltimore")

# What-if analysis
agent.what_if({"query": "640 FICO fix and flip", "fico": 700})

# Data freshness
agent.get_freshness()
```

## City Map (Suburb → Metro Detection)

`corpus/city_map.json` maps 25 Baltimore suburbs to trigger city restrictions:

| Query mentions | Engine detects | Scenario triggered |
|---------------|----------------|--------------------|
| "Towson duplex" | City: Baltimore | Baltimore Allowed (5% LTV haircut, rate adder) |
| "Pikesville" | City: Baltimore | Baltimore Allowed |
| "Canton" | City: Baltimore | Baltimore Allowed |

Currently only Baltimore has documented restrictions. Expansion requires adding entries to `city_map.json` + matching scenarios in the corpus.

## Agent Conversation Rules

When borrowing amounts are known, use `max_loan=` to filter out lenders with insufficient capacity:

```python
agent.find_lenders("Chicago fix and flip", max_loan=2_000_000)
```

If borrower mentions 3+ properties without saying "blanket", ask whether they want blanket or individual loans.

If borrower says "light rehab", ask: cosmetic or structural? Cost as % of ARV?

If borrower says "80 cents on the dollar", ask: 80% of ARV or purchase price?

If borrower asks "are these rates good?" without deal context, refuse: need product, FICO, LTV, loan amount, property type.

## Understanding Evals Output

Every query auto-runs 7 evals. Each returns PASS / WARN / FAIL:

```
  Verification:
    ✓ source_integrity: All 12 sources verified
    ✓ attribute_existence: All cited attributes verified in corpus
    ✓ lender_validity: All 8 lenders are valid
    △ scenario_completeness: Scenario 'X' missing lenders {...}
    ✓ no_hallucinated_values: All values match corpus
    ✓ determinism: Result structure valid
    ✓ staleness: Data 10.9 days old (fresh)
    --- 6 passed, 1 warned, 0 failed ---
```

| Eval | What it catches |
|------|----------------|
| source_integrity | Hallucinated sheet names or row numbers |
| attribute_existence | Fake attribute names (e.g. "fico_min" vs "fico_max") |
| lender_validity | Unknown lender names in output |
| scenario_completeness | Lenders dropped from scenario recommendations |
| no_hallucinated_values | Values not matching corpus data |
| determinism | Structural output format issues |
| staleness | Data FAIL if >90d, WARN if >30d since Excel was parsed |

## Query Output: Reading the Results

Example output for `python3 query.py "680 FICO Chicago DSCR"`:

```
======================================================================
  Query: 680 FICO Chicago DSCR
======================================================================
  Parsed: FICO ≥680 | City: Chicago | Product: sfr_dscr

  Scenario match: City Restrictions, State-Specific Adjustments

  Recommendations (14 lenders):

  1. Velocity  (score: 1.00)
     - Offers sfr_dscr
     - FICO check: FICO 680 meets ≥ 650
     ...

  Scenario details:

  [CS-DSCR Implication] City Restrictions
    → Chicago/Cook County   Groundfloor (no issue, but won't do second...)
    → Detroit               Groundfloor (no issue, but won't do second...)
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No lenders matched" | Product or criteria too narrow | Drop FICO by 20pts, widen city, try different product |
| Staleness WARN/FAIL | Excel parsed >30 days ago | Re-run `python3 migrate.py --excel <excel>` |
| "State not found" | Misspelled state code | Use 2-letter code: "MD", "CA", "TX" |
| Lender missing from results | filtered out by `!not` or loan_max penalty | Check `!history` for active exclusions |
| Scenario not triggering | City not in city_map.json | Add entry or use metro city name directly |

## Data Pipeline

```bash
# Parse Excel → SQLite corpus.db
python3 migrate.py --excel ~/Downloads/Copy\ of\ THE\ Master\ Credit\ Box-IPLE\ 2026\ \(1\).xlsx

# Rebuild LLM cache (after data updates)
python3 build_llm_cache.py

# Run test suite
python3 test_runner.py

# Run evals standalone
python3 evals.py
```

## File Map

| Path | Purpose |
|------|---------|
| `corpus/corpus.db` | SQLite corpus: EAV records, lender index/aliases, scenarios |
| `corpus/llm_cache.json` | 261 pre-computed structured entries |
| `corpus/city_map.json` | Suburb → metro mapping for restriction inheritance |
| `migrate.py` | Excel → SQLite corpus.db |
| `store.py` | Data-access layer (sole reader of corpus.db) |
| `reason.py` | Deterministic engine — scoring, criteria parsing, scenario matching |
| `llm_parse.py` | LLM-as-judge for state coverage, FICO/LTV tier parsing |
| `agent_tools.py` | 9 agent tools wrapping engine |
| `query.py` | CLI entry point with conversation state |
| `state.py` | Conversation persistence |
| `evals.py` | 7 code-driven integrity checks |
| `test_runner.py` | 19 regression tests |
| `AGENT_TOOLS.md` | Full agent prompt — tool surface + conversation discipline + deal entry rules |
| `AVAILABLE_GAPS.md` | Capability analysis — what's not yet built |

## Known Gaps

See `AVAILABLE_GAPS.md` for detailed analysis of capabilities not yet built.

# Agent Tool Surface: Loan-Pricing Partner

Orchestrate LLM agent with these tools to answer multi-turn deal questions.

## Available Tools

### `find_lenders(query: str) -> list`
Current engine. Returns ranked lenders with scores + reasoning + source citations.
Best for: "who does 640 FICO Baltimore fix and flip?"

### `get_lender_profile(lender: str, product: str = None) -> dict`
All attributes for a lender+product. Includes credential fields tagged `[SENSITIVE]`.
Best for: "show me everything about Kiavi's fix-and-flip program"

### `compare_lenders(lender1: str, lender2: str, product: str = None) -> list`
Side-by-side diff of all differing attributes.
Best for: "how does Kiavi compare to Constructive on DSCR?"

### `get_fico_ltv_tiers(lender: str, product: str = None) -> dict`
Structured FICO/LTV tier tables from LLM-parsed cache. Shows exact conditions:
```
{note_type: "tiered",
 tiers: [
   {min_fico: 740, max_ltv: 80},
   {min_fico: 700, max_ltv: 75},
   {condition: "else", max_ltv: 70}
 ]}
```
Best for: "what LTV at 680 FICO?" "what DSCR do they need at 720?"

### `scenario_details(scenario: str) -> str`
Full recommendation text for a matched scenario rule.
Best for: "why is Baltimore a special case?" "what's the heavy rehab policy?"

### `get_freshness() -> dict`
Data age, file mtime, record count. Agent can warn user if data is stale.
Best for: "is this data current?"

### `check_criteria(lender: str, product: str, criteria: dict) -> dict`
Structured check of specific conditions against a lender's attributes.
criteria: {fico: 680, state: "MD", experience: 2, loan_amount: 150000}
Returns passes/fails per criterion with source evidence.
Best for: "does Conventus work for 680 FICO in Baltimore?"

### `estimate_pricing(lender: str, product: str, ltv: int, fico: int) -> dict`
Best-guess rate range by matching borrower params against lender's tier table + stated rate range.
Uses structured tier data to find applicable rate tier.
Returns: {rate_range: [min, max], origination: [min, max], notes: "..."}
Best for: "what rate can I expect with 75% LTV and 680 FICO?"

### `what_if(lender: str, param_changes: dict) -> dict`
Re-query engine with modified parameter. Shows how results change.
Best for: "what if I had 700 instead of 640?" "what if LTV was 80%?"

## Agent Workflow Patterns

### Deal triage (common)
1. `find_lenders(deal_params)` → ranked list
2. For top 3: `check_criteria(lender, product, deal_criteria)` → confirm fit
3. For top 3: `estimate_pricing(lender, product, ltv, fico)` → pricing comparison
4. Present user with: "Best fit: X (score Y). Rates: Z%-W%. Alternatives: ..."

### Deep dive
1. User picks a lender from triage
2. `get_lender_profile(lender, product)` → all details
3. `get_fico_ltv_tiers(lender, product)` → exactly how LTV scales with FICO
4. `scenario_details(matched_scenario)` → what special rules apply
5. Agent synthesizes: "At 680 FICO you get 75% LTV with 1.10 DSCR. Baltimore adds a 0.25% rate adder and 5% LTV haircut."

### Trade-off analysis
1. `compare_lenders("Kiavi", "Constructive", "fix_and_flip")` → attribute diffs
2. `what_if("Kiavi", {"fico": 700})` → see how score changes with higher FICO
3. Agent: "Constructive has lower rates (0.075 vs 0.105) but Kiavi doesn't do soft pull. With 700 FICO, Kiavi's score jumps 40%."

## Integration

Wrap tools as a JSON-RPC or simple Python API:
```
from agent_tools import CreditBoxAgent
agent = CreditBoxAgent()
agent.find_lenders("640 FICO Baltimore")
agent.find_lenders("640 FICO Chicago fix and flip", max_loan=2_000_000)
```

LLM agent prompt instruction:
"You are a loan-pricing partner. Use `find_lenders` to route deals, `get_fico_ltv_tiers` for pricing details, and `get_lender_profile` for program specifics. Cite sources. Never fabricate lender data."

## Deal Entry Rules (Pushback Patterns)

These rules govern how the agent handles ambiguous or under-specified deal entries. Apply them BEFORE making tool calls.

### R1 — Blanket Detection
If borrower mentions 3+ properties (e.g. "6 Texas properties") WITHOUT saying "blanket":
→ Ask: "Do you want one blanket loan covering all properties, or individual loans per property?"
→ If blanket: route to `sfr_blanket` product via `find_lenders(query, product="sfr_blanket")` or append "blanket" to query.
→ If individual: proceed with normal routing (`find_lenders` picks the right product from criteria).

### R2 — Light Rehab Ambiguity
If borrower says "light rehab" or "cosmetic" without specifying scope:
→ Ask: "What kind of work? Estimated cost as % of ARV?"
→ Rationale: Lenders classify rehab differently. "Light" to one may be "heavy" to another. Cost % triggers specific product rules.

### R3 — "80 Cents on the Dollar" / LTV Ambiguity
If borrower says "80 cents on the dollar," "80 cents," or similar:
→ Ask: "Is that 80% of ARV (after-repair value) or 80% of purchase price?"
→ If ARV: maps to max LTV/ARV constraints.
→ If purchase: maps to LTC (loan-to-cost) constraints.
→ Honest answer: "I can give better guidance once I know which."

### R4 — City/Region Awareness
If borrower says a suburb name, the engine auto-maps it to the parent metro city for restriction checking (e.g. Towson → Baltimore → triggers Baltimore scenario).
→ You do not need to ask about this — the engine handles it.
→ If the engine returns a city-specific scenario (e.g. Baltimore 5% haircut), mention the restriction and its source to the borrower.

### R5 — Rate Shopping Without Context
If borrower asks "are these rates good?" without deal context:
→ Refuse to answer. Ask for: product, FICO, LTV, loan amount, property type.
→ Rationale: Rates are meaningless without context. 11.5% for a 600-FICO fix-and-flip is fair; 11.5% for a 740-FICO DSCR is terrible.

## Agent Workflow Rules

1. Max 2 tool calls per turn. Must end with exactly 1 question. Checkpoint every 4 turns.
2. If `find_lenders` returns no good matches, ask what parameter the borrower is willing to change (FICO, LTV, experience, etc.) and run `what_if`.
3. Never dump all 10 matches at once. Present top 3 with a recommendation. Offer to go deeper on any of them.

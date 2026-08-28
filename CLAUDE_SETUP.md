# Claude Code Setup: Credit Box RAG

One-shot setup guide for running the loan-pricing partner on a new machine.

---

## What You Need

| Item | Where | Purpose |
|------|-------|---------|
| `credit-box-rag/` folder | Your Desktop | All code + corpus |
| `Copy of THE Master Credit Box-IPLE 2026 (1).xlsx` | Your Downloads | Source data |
| Python 3.10+ | System | Runtime |
| Claude Code | Terminal | LLM interface |

---

## Step 1: Copy These Files

Copy the entire `credit-box-rag/` folder to the new user's machine. Everything they need is inside:

```
credit-box-rag/
├── corpus/              ← pre-built data (corpus.db, llm_cache.json, etc.)
├── migrate.py           ← Excel → corpus.db (only needed if data updates)
├── store.py             ← data-access layer
├── reason.py            ← scoring engine
├── query.py             ← CLI interface
├── agent_tools.py       ← 9 Python tools for Claude
├── llm_parse.py         ← LLM-as-judge for state/FICO parsing
├── evals.py             ← integrity checks
├── state.py             ← conversation persistence
├── test_runner.py       ← regression tests
├── attr_types.py        ← attribute type validation
├── tests.json           ← test cases
├── credit-box           ← shell shortcut
├── AGENT_TOOLS.md       ← full agent prompt
├── HOW_TO.md            ← usage docs
└── AVAILABLE_GAPS.md    ← known gaps
```

**Do NOT include**: `__pycache__/`, `.pytest_cache/`

---

## Step 2: Install Dependencies

```bash
pip install openpyxl pydantic pyyaml
```

That's it. Only 3 third-party packages. Everything else is stdlib.

---

## Step 3: Verify Corpus

```bash
cd ~/Desktop/credit-box-rag
python3 -c "
from store import load_all, get_lenders_index, get_scenarios
data = load_all()
print(f'Corpus: {len(data[\"records\"])} records')
print(f'Lenders: {len(get_lenders_index())}')
print(f'Scenarios: {len(get_scenarios())}')
"
```

Expected output:
```
Corpus: 12345 records (number varies by import)
Lenders: ~145
Scenarios: 53
```

If this fails, re-migrate from Excel (see Step 5).

---

## Step 4: Create CLAUDE.md

Create this file at the project root (`~/Desktop/credit-box-rag/CLAUDE_MD`) — or add the contents to whatever project's CLAUDE.md Claude Code reads:

```markdown
# Credit Box RAG — Loan-Pricing Partner

You have access to a mortgage lending knowledge system covering ~145 wholesale lenders
and 9 product types (DSCR, fix-and-flip, new construction, multifamily, bridge, blanket, commercial).

## Setup

```bash
cd ~/Desktop/credit-box-rag
pip install openpyxl pydantic pyyaml
```

## Quick Start

Route a deal:
```bash
python3 query.py "640 FICO Baltimore fix and flip"
```

Refine:
```bash
python3 query.py "make it 700 FICO"
python3 query.py !show 1
python3 query.py !compare 1 3
```

## Agent Tools (Python API)

Use these to answer deal questions:

```python
from agent_tools import CreditBoxAgent
agent = CreditBoxAgent()

# Route deal
agent.find_lenders("640 FICO Baltimore fix and flip", max_loan=2_000_000)

# Get lender details
agent.get_lender_profile("Kiavi", "fix_and_flip")

# Compare lenders
agent.compare_lenders("Constructive", "CV3", "sfr_dscr")

# Check specific criteria
agent.check_criteria("Hard Money Co", "fix_and_flip", {"fico": 600})

# Pricing estimate
agent.estimate_pricing("Conventus", "sfr_dscr", ltv=75, fico=720)

# What-if
agent.what_if({"query": "640 FICO fix and flip", "fico": 700})

# Scenario details
agent.scenario_details("Baltimore")

# Data freshness
agent.get_freshness()
```

## Agent Rules

1. **Never fabricate lender data.** Always cite sources. If data missing, say so.
2. **Rate shopping without context → refuse.** Ask for product, FICO, LTV, loan amount, property type.
3. **"80 cents on the dollar" → clarify.** Ask: 80% of ARV or purchase price?
4. **3+ properties without "blanket" → ask.** Blanket vs individual?
5. **Light rehab → ask scope.** Cosmetic or structural? Cost as % of ARV?
6. **Baltimore suburbs auto-trigger Baltimore restrictions.** Towson, Pikesville, etc. → 5% LTV haircut, rate adders.
7. **Max 2 tool calls per turn.** End with 1 question. Checkpoint every 4 turns.
8. **Never dump all matches.** Top 3 + recommendation. Offer deeper dives.
9. **Credentials in data.** Never surface User Name/Password fields from corpus.
10. **Data freshness.** Warn if corpus is >30 days old.

## Common Queries

| Query | What Happens |
|-------|-------------|
| "640 FICO fix and flip Baltimore" | Routes deal, shows 3-6 lenders |
| "How does Constructive compare to CV3?" | Side-by-side attribute diff |
| "What rate at 720 FICO, 75% LTV?" | Estimates from tier data |
| "Anyone do 600 FICO?" | Hard Money Co only |
| "Is this data current?" | Shows days since last import |

## Updating Data

When new Excel arrives:

```bash
python3 migrate.py --excel ~/Downloads/NewCreditBox.xlsx
python3 build_llm_cache.py
```

Verify:
```bash
python3 test_runner.py
```

## File Map

| File | Purpose |
|------|---------|
| `corpus/corpus.db` | SQLite corpus: EAV records, lenders, scenarios |
| `corpus/llm_cache.json` | 241 pre-computed entries |
| `corpus/city_map.json` | Suburb → metro mapping |
| `store.py` | Data-access layer (sole reader of corpus.db) |
| `reason.py` | Scoring engine |
| `agent_tools.py` | 9 agent tools |
| `query.py` | CLI with conversation state |
| `AGENT_TOOLS.md` | Full agent prompt |
```

---

## Step 5: Re-parse (Only If Data Changed)

If the Excel file has been updated:

```bash
python3 migrate.py --excel ~/Downloads/NewCreditBox.xlsx
python3 build_llm_cache.py
python3 test_runner.py  # verify nothing broke
```

---

## Step 6: Test

```bash
cd ~/Desktop/credit-box-rag

# Quick test
python3 query.py "640 FICO fix and flip"

# Run all tests
python3 test_runner.py

# Run evals
python3 evals.py
```

---

## Usage Patterns

### Direct CLI

```bash
./credit-box "640 FICO Baltimore fix and flip"
./credit-box !show 1
./credit-box !compare 1 3
./credit-box !not Groundfloor
./credit-box !history
./credit-box !clear
```

### Ask Claude Code

Open Claude Code in the `credit-box-rag/` directory and ask:

- "Route this deal: 640 FICO, $90k in Towson, 1 prior flip"
- "Compare Constructive vs CV3 on DSCR"
- "Who has the best rates for 720 FICO at 75% LTV?"
- "Does Conventus work for Baltimore?"
- "What changed since last import?"

Claude will use the agent tools to answer.

### Python API (Custom Integrations)

```python
from agent_tools import CreditBoxAgent

agent = CreditBoxAgent()

# Batch check multiple deals
deals = [
    "640 FICO Baltimore fix and flip",
    "700 FICO Chicago DSCR",
    "720 FICO Phoenix new construction"
]

for deal in deals:
    results = agent.find_lenders(deal)
    print(f"\n{deal}")
    for r in results[:3]:
        print(f"  {r['lender']}: {r['score']:.2f}")
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'openpyxl'` | `pip install openpyxl` |
| "No lenders matched" | Widen criteria: lower FICO, drop city, try different product |
| Staleness warning | Re-parse from Excel |
| `corpus.db` missing | Re-run `python3 migrate.py --excel <excel>` |
| Engine crashes on load | Check Python 3.10+, reinstall deps |
| "State not found" | Use 2-letter code: "MD", "CA", "TX" |

---

## Security Notes

- **Credentials in data**: The Excel contains plaintext lender portal logins. These are extracted but flagged `sensitive: true` in the corpus. Never surface them in responses.
- **corpus.db is NOT encrypted**. Treat it as internal-only. Do not share outside the org.
- The `!not` exclusion list persists in `~/.credit-box/state.json`. Clear between users with `!clear`.

---

## What Claude Code Sees

When you open the `credit-box-rag/` directory in Claude Code, it reads:
1. `CLAUDE.md` (if present) — your agent prompt
2. `AGENT_TOOLS.md` — full tool documentation
3. `HOW_TO.md` — usage guide
4. `README.md` — full architecture context

Claude Code can then run the Python tools directly in conversation.

---

## One-Shot Prompt (Copy/Paste to New Claude Session)

```
You are a loan-pricing partner for IP Loan Exchange. You have access to a mortgage
lending knowledge system covering ~145 wholesale lenders and 9 product types.

Setup:
  cd ~/Desktop/credit-box-rag
  pip install openpyxl pydantic pyyaml

To answer questions, run:
  python3 query.py "your question here"

For the agent API:
  from agent_tools import CreditBoxAgent
  agent = CreditBoxAgent()
  agent.find_lenders("640 FICO Baltimore fix and flip")

Rules:
- Never fabricate lender data. Always cite sources.
- Rate shopping without context → refuse (need product, FICO, LTV, loan amount, property type).
- "80 cents on the dollar" → clarify ARV vs purchase price.
- 3+ properties without "blanket" → ask blanket vs individual.
- Baltimore suburbs (Towson, Pikesville, etc.) → auto-trigger Baltimore restrictions.
- Max 2 tool calls per turn. End with 1 question.
- Never dump all matches. Top 3 + recommendation.
- Never surface credentials (User Name/Password fields).
- Warn if corpus is >30 days old.
```

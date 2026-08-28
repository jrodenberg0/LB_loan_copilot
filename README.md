# Master Credit Box → RAG Knowledge System

## Status: Analysis Complete. Code: None.

### Business Context

**Who**: IP Loan Exchange (IPLE) — a mortgage brokerage that originates private-money loans for real estate investors. They broker deals to ~78 wholesale lenders.

**The Problem**: Their entire lending playbook lives in one massive Excel workbook ("Master Credit Box") that an analyst manually updates. It's the single source of truth for:
- Which lender to submit each deal to (routing decisions)
- What each lender's current rates, LTVs, fees, and coverage are
- Login credentials for each lender's portal/pricer
- Nuanced rules: who accepts Cook County deals, who does heavy rehab, who works with 0-experience borrowers

**What They Need**: A queryable knowledge system so a broker can ask "640 FICO, $90k property in Baltimore, 1 prior flip — where do I send this?" and get ranked lender recommendations with supporting rationale.

**Why It's Hard**: Data is in human-friendly wide-format tables with freeform text. ~23K cells, inconsistent attribute naming, merged cells in CS sheets, embedded narratives masquerading as data.

---

### What We Have

`/Users/jackrodenberg/Downloads/Copy of THE Master Credit Box-IPLE 2026 (1).xlsx`

| Sheet | Rows | Cols | Type | Purpose |
|---|---|---|---|---|
| SFR DSCR | 967 | 41 | Product Matrix | Single family rental loans. Most detailed sheet. |
| Fix & Flip | 988 | 42 | Product Matrix | Short-term rehab/BRRRR loans. |
| New Construction | 1018 | 29 | Product Matrix | Ground-up construction loans. |
| Multifamily Long Term | 983 | 28 | Product Matrix | 5+ unit apartment permanent financing. |
| SFR Bridge | 1009 | 32 | Product Matrix | Short-term bridge on SFR. |
| SFR Blanket | 1012 | 31 | Product Matrix | Multi-property blanket loans. |
| Multifamily Rehab | 1018 | 28 | Product Matrix | Multifamily fix & flip. |
| Multi-Comm Bridge | 985 | 30 | Product Matrix | Commercial/mixed-use bridge. |
| SB Commercial Long Term | 984 | 25 | Product Matrix | Small-balance commercial perm. |
| CS-DSCR Implication | 1009 | 26 | Decision Matrix | Borrower situation → lender routing (DSCR). |
| CS-FNF Implication | 1003 | 26 | Decision Matrix | Borrower situation → lender routing (FNF). |
| CS-LEASEOCCUPANCY | 999 | 29 | UW Detail | Per-lender vacancy/lease rules. |
| CS-CREDIT | 1008 | 22 | UW Detail | FICO grids per lender. |
| CS-EXPERIENCE | 1001 | 28 | UW Detail | Experience-tier matrices per lender. |
| CS-RESERVESASSETS | 1007 | 9 | UW Detail | Reserve requirements per lender. |
| Copy of CS-CREDIT | 1010 | 22 | Duplicate | Stale backup — ignore. |
| SSCS | 1012 | 57 | Reference | "Same thing, different name" — lender alias/DBAs. |

---

### Key Findings From Analysis

**Product sheets are clean.** Structure: Row 1 = lender names (columns B→), column A = attribute labels, values in cells. Zero merged cells across all 9 product sheets. Parsing is straightforward openpyxl work.

**CS sheets are messier but parseable.** Merged cells exist but only for visual grouping (e.g., merging header cells like "Poor Credit Score" across cols B-C). The actual data cells are individual. Biggest challenge: freeform text with embedded bullet lists, conditional logic, and multi-sentence narratives.

**Attribute names are inconsistent across sheets.** Examples found in the wild:
- `FICO Requirement at Max LTV`, `FICO Min`, `Min FICO`, `MINIMUM FICO`
- `Max % LTV (Purchase)`, `Max % of Purchase`, `Max % LTV (Purch.)`
- `Term in Months`, `Fixed Period`, `Amortization Period`
- `Interest Only Available`, `IO Available`

These need a manual mapping table (~40 entries) — not auto-derivable.

**78 raw lender names → ~55 canonical after alias resolution.** SSCS sheet helps. Example duplicates: "ROC" = "ROC Capital", "Kiavi" = "Kiavi Lending" (from emails), "LendingOne" = "Lending One", "CoreVest" = "Corevest". The `VOTE COLUMN` row sometimes has a numeric value like `0.14` that got misread as a lender name.

**Credentials are in plaintext.** Every product sheet has rows `User Name` and `Password` with broker portal logins (e.g., `IPLoan@00`, `217bec1b`). This is sensitive. The knowledge system should either (a) exclude credentials from RAG output or (b) store them encrypted with access control. Default: exclude from corpus, keep only in Obsidian vault with restricted read.

**Decision matrix sheets are the crown jewels.** CS-DSCR Implication and CS-FNF Implication encode routing logic:
```
[Condition] → [Lender(s) with notes]
Short seasoning → Constructive, RCN, CV3, Kiavi, Velocity, Conventus, Rain City
Heavy rehab → Rain City, Groundfloor, ROC, CV3, FlipCo, Kiavi, Crebrid
Baltimore → Constructive, CV3, Conventus, Gradient
No credit pull → FlipCo, Hard Money Co
```
These are essentially pre-built if-then rules. For RAG, they're the highest-value queries because they answer "where do I send this deal?"

**Some rows are "meta" not data.** Rows with values like `1.0`, `2.0`, `3.0` in column A are priority/version markers, not data rows. Need to skip or treat as metadata. `VOTE COLUMN` row at top is internal ranking, not a lender.

---

### Key Decisions So Far

1. **Normalization IS feasible** — the data is consistent enough. Product sheets need ~300 lines of Python. CS sheets need ~100 more. No client reformatting required.

2. **Update format should be structured templates, not PDF parsers.** The team should fill a YAML form, run `/ingest update.yaml`, and let the system diff + validate + commit. PDF parsers are fragile and will silently corrupt data when a lender changes their rate sheet layout. If the client insists on PDF ingestion, add a human verification step (diff output for approval).

3. **Output targets (all three):**
   - **Obsidian vault** (`.md` files with YAML frontmatter + bidirectional links) — for human browsing and graph-view exploration
   - **JSON corpus** (`corpus.json` — array of `{lender, product, attr_name, attr_value, confidence}`) — for programmatic RAG queries
   - **Vector index** (Chroma/LanceDB) — for semantic similarity search on narrative fields

4. **Confidence scoring.** Every attribute value gets a tag:
   - `typed` — clean numeric/boolean extracted from cell
   - `text` — freeform paragraph, usable for context but not exact filtering
   - `manual` — human-entered via template
   - `inferred` — derived from other values (e.g., state exclusion list parsed from "Nationwide Ex AK, ND, SD")

5. **Credentials stored but quarantined.** Login/password rows get extracted but flagged with `sensitive: true` in the JSON corpus. The RAG query layer omits them by default. Obsidian vault encrypts them or marks `#sensitive`.

---

### Schema: EAV Model

```python
# Core normalized record
{
  "lender": "Kiavi",
  "product": "fix-and-flip",      # canonical product key
  "attr_name": "fico_min",        # canonical attr key
  "attr_value": 680,              # typed where possible
  "raw_text": "680+",             # original cell value
  "source_sheet": "Fix & Flip",
  "source_row": 41,
  "confidence": "typed"           # typed | text | manual | inferred
}

# Entity relationships (for graph)
# Lender —has→ Contact
# Lender —offers→ Product
# Product —has→ Attribute
# Scenario —recommends→ Lender (+ notes)
# Lender —belongs_to→ DecisionMatrix (+ row data)
```

---

### Known Data Quirks & Edge Cases

| Issue | Example | Handling |
|---|---|---|
| Numeric stored as date | `Term in Months` = `2020-12-18` instead of `18` | Detect if value is a datetime, extract month component |
| Formula references | `=K114` in a date cell | Evaluate with openpyxl data_only=False fallback |
| Mixed typing | "80% (700+)" not just 0.8 | Store raw_text + extract best-effort typed value |
| Conditional logic in cells | "90% to 740, 75% to 700, 70% else" | Keep as text for RAG, extract structured LTV/FICO pairs where regex matches |
| Missing columns (lender has no data) | Empty cells for inactive lenders | Store as null with confidence=absent |
| Unknown row labels | Rows that appear in one sheet but not another | Keep as key-value; schema evolves open |
| State coverage freeform | "Nationwide: Ex AK, ND, SD, VT, OR, AZ, NV, UT" | Parse into include_all=True + exclusions list |
| Portfolio/Blanket distinction | SFR Blanket is own sheet but some lenders have blanket within DSCR sheet | Cross-reference product sheets; blanket may appear as a row in DSCR too |

---

### Update Workflow (Chosen Approach)

We decided against fragile PDF parsing. Instead:

```
1. Source changes (lender rate sheet, program update)
2. Human fills templated YAML:
     lender: Kiavi
     product: fix-and-flip
     effective_date: 2026-07-01
     changes:
       - attr: fico_min
         old: 700
         new: 680
       - attr: rate_floor
         old: 8.50%
         new: 7.99%
     source_doc: "Kiavi Q3 2026 Rate Sheet v2.pdf"
     updated_by: "Quinton"
3. ./ingest update.yaml
     → validates schema
     → diffs against current corpus
     → shows proposed changes for approval
     → on confirm, writes to corpus + regenerates vault + reindexes
```

The template acts as both input form and audit trail. Every change is timestamped, attributed, and sourced.

**If client refuses template workflow and insists on raw PDF/Word ingestion**: build a `parse` subcommand that uses docling + regex extraction, then outputs a pre-filled YAML for human review and approval. The human is still in the loop; the parser just speeds up form-filling.

---

### Obsidian Vault Layout (Target)

```
vault/
├── .obsidian/
├── Lenders/
│   ├── Kiavi.md              # YAML frontmatter + narrative + links
│   ├── CV3.md
│   ├── Constructive.md
│   └── ... (~55 files)
├── Products/
│   ├── SFR-DSCR.md            # Product overview + linked lenders + common scenarios
│   ├── Fix-and-Flip.md
│   └── ... (~9 files)
├── Scenarios/
│   ├── Baltimore-MD.md        # Which lenders handle it, what haircuts apply
│   ├── Heavy-Rehab.md
│   ├── Poor-Credit-600-639.md
│   ├── No-Experience.md
│   ├── Rural-Properties.md
│   └── ... (~15 files based on CS sheets)
├── Underwriting/
│   ├── Credit-Grids.md        # Master table: FICO → LTV per lender
│   ├── Experience-Tiers.md
│   ├── Reserves-Policy.md
│   ├── Lease-Occupancy.md
│   └── State-Coverage.md
├── Atlas.md                   # Root — MOC (map of content)
└── Changelog.md               # Every update logged here
```

Each lender note links to:
- `[[Products/SFR-DSCR]]` — they offer this product
- `[[Scenarios/Baltimore-MD]]` — they handle this scenario
- `[[Underwriting/Credit-Grids]]` — their FICO grid lives here
- `[[Changelog]]` — last updated + what changed

This gives Obsidian's graph view real value: click any lender and see all products, scenarios, and UW profiles connected.

---

### Next Steps (When Resuming)

```
Phase 1 — Parser (~2-3hr)
  □ Write Python script: openpyxl → [EAV tuples]
  □ Handle all 16 sheets, extract row labels, column headers
  □ Normalize attribute names (mapping dict of ~40 entries)
  □ Deduplicate lenders (78 → ~55 via SSCS alias table)
  □ Flag sensitive fields (credentials)

Phase 2 — Schema & Validation (~1hr)
  □ Define canonical attr names per product type (pydantic models)
  □ Build validation rules (min≤max, required attrs, ranges)
  □ State coverage parser (regex for "Nationwide: Ex X, Y, Z")
  □ FICO/LTV condition parser (regex for "X% to Y, Z% to W")

Phase 3 — Update Template & Diff Engine (~1hr)
  □ Design YAML schema matching canonical attr names
  □ Write diff engine: compare {lender, product, attr} key against corpus
  □ Output: {added, changed, removed, unchanged} with old/new values
  □ Dry-run mode: show changes without applying

Phase 4 — Output Generators (~1-2hr)
  □ Obsidian vault writer (.md per lender + product + scenario)
  □ JSON corpus emitter
  □ Vector index population (Chroma/LanceDB)

Phase 5 — Skill Wrapping (~1hr)
  □ Package as opencode skill (ingest-lender-data)
  □ Manual entry prompt template for ad-hoc updates
  □ Validation pass before commit
```

**Total build time estimate: ~6-8 hours of focused coding.**

---

### Reference Files

| File | Purpose |
|---|---|
| `Desktop/credit-box-rag/README.md` | This file — full context dump |
| `Desktop/lending-ontology-system.md` | Architecture diagrams (mermaid), schema, workflows |
| `Downloads/Copy of THE Master Credit Box-IPLE 2026 (1).xlsx` | Source data — 16 sheets, 78 lenders |

### Quick Resume

```bash
cd ~/Desktop/credit-box-rag
pip install openpyxl pydantic pyyaml

# Start with Phase 1: openpyxl → EAV tuples
# See lending-ontology-system.md for full architecture diagrams
```

### Key Contacts (from spreadsheet)

| Lender | AE | Email | Phone |
|---|---|---|---|
| Constructive (Standard) | Benn Jackson | bjackson@constructiveloans.com | 312-945-1024 |
| CV3 | Ben Shaevitz | ben@cv3financial.com | 323-839-2154 |
| Visio | John Sperling | John.Sperling@visiolending.com | 512-334-1506 |
| RCN | Jessie Scott | JScott@rcncapital.com | 860-373-2019 |
| Velocity | Jonah Belgini | jbelgrini@velocitymortgage.com | 305-421-9065 |
| Kiavi | Derek Foltz / Noah Howland | derek.foltz@kiavi.com | 415-231-2439 |
| ROC Capital | Jon Kelly | jon.kelly@roccapital.com | 332-207-4672 |
| Conventus | Lindsey Lawson | lindsey@cvlending.com | 925-323-2626 |
| Lima One | Teddy Choi | tchoi@limaone.com | 949-213-0073 |
| Easy Street | Raphael Junqueira | raphael@easystreetcap.com | 615-... |
| LendingOne | Mark Zummo-Hurley | mzummohurley@lendingone.com | direct |
| Templeview | Mark Burch | mburch@templeviewcapital.com | 240-351-5434 |
| Archwest | Danny Farber | dfarber@archwestcapital.com | 812-240-6982 |
| Rain City Capital | Austin Bunkers | austinb@raincitycapital.com | 419-351-4731 |
| Groundfloor | Jeff Seal | jeff@groundfloor.us | 918-638-0764 |
| (plus ~60 more — see spreadsheet) | | | |

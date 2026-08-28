# Loan Copilot: Data Model Unification, Plugin Packaging, and Reasoning Architecture

Status: Approved design. Phase 1 is ready for implementation planning. Phase 2 is a documented roadmap, not yet scheduled.

## Context

`credit-box-rag` is a working prototype (not a blank slate — ~5,900 lines of Python, 17/19 regression tests passing, 9/9 evals passing) that turns IP Loan Exchange's "Master Credit Box" Excel workbook (~78 lenders, 9 loan products, 16 sheets) into a queryable lending knowledge system. A broker or an LLM agent can ask "640 FICO, $90k property in Baltimore, 1 prior flip — where do I send this?" and get ranked lender recommendations with source citations.

Two goals drove this design:

1. **Housekeeping** — the prototype accumulated structural debt (duplicate data stores, manual-copy distribution) that has to be fixed before the system can be trusted or shipped anywhere else.
2. **Theory of the system** — once housekeeping is done, the actual reasoning architecture needs to match the stated goal: ingest structured deal data (increasingly via MCP, not just NL chat), apply hard constraints deterministically, reason over nuanced lender prose only where it belongs, and return multiple possible scenarios with citations traceable back to source data — not a single opaque score.

## Audit Findings (baseline, pre-Phase 1)

- **Split-brain data store.** `corpus/corpus.json` (flat EAV, written by `parser.py`, 129 lenders) and `corpus/corpus.db` (SQLite with proper FKs, written by `migrate.py`, 91 lenders) are two independent stores with no sync mechanism. `reason.py`'s `CreditBoxEngine` reads only from SQLite; `query.py`, `agent_tools.py`, `evals.py`, and `build_llm_cache.py` read `corpus.json` directly. The 129-vs-91 lender count discrepancy is unreconciled.
- **Confidence tagging already exists but isn't used consistently.** `attribute_definitions.data_type` and a `typed`/`text`/`manual`/`inferred` confidence tag on every EAV value already encode the hard-constraint-vs-prose distinction the copilot needs — but nothing downstream reads or propagates it. `llm_parse.py` does LLM-as-judge parsing of freeform tier text into structured tiers, cached in `llm_cache.json` — real scaffolding, just not wired end-to-end.
- **2 known-failing regression tests**, both scoped out of Phase 1 by decision: `chicago-cook-restrictions` (city-scenario matching incomplete outside Baltimore) and `fast-close` (a qualitative attribute not wired into scoring). Tracked in `AVAILABLE_GAPS.md` along with 6 other known-unbuilt items.
- **No installable distribution.** `CLAUDE_SETUP.md` describes a manual folder-copy + paste-into-CLAUDE.md workflow. No `.claude-plugin/plugin.json`, no MCP server, no packaged skill.
- **No version control of its own.** The directory had no dedicated git history before this spec (see baseline commit).

## Phase 1: Data Model Unification + Plugin Packaging

Goal: one source of truth for the data, one portable MCP server installable under both Claude Code and Codex CLI. No new reasoning capability in this phase — strictly foundation.

### 1. Data model unification

Introduce `store.py` as the single module permitted to touch `corpus.db`. Everything else calls it.

`store.py` responsibilities:
- Own the SQLite connection and expose typed functions per query pattern currently duplicated across files (`get_lender`, `get_products`, `get_attr_values`, `get_scenarios`, `get_credit_grid`, etc.).
- Return the `typed`/`text`/`manual`/`inferred` confidence tag as a first-class field on every value returned, so downstream code can't silently drop it.

Migration is incremental and test-gated, not a rewrite:

1. Write `store.py` against the existing `corpus.db` schema. No consumers change yet.
2. Swap `reason.py` onto `store.py` (replacing its own `_db()`/`load_all_from_db()`). Re-run `test_runner.py` — must hold at 17/19 with the same two failures.
3. Swap `agent_tools.py` off `corpus.json` onto `store.py`. Re-run tests.
4. Swap `query.py`'s remaining direct `corpus.json` reads (`--show-lender`, `--compare`, `--show-tiers`) onto `store.py`. Re-run tests.
5. Point `evals.py` and `build_llm_cache.py` at `store.py`.
6. Reconcile the 129-vs-91 lender discrepancy: diff what `parser.py` captured against `migrate.py`'s output to confirm nothing real is lost (likely aliases miscounted as lenders, or legitimate validation rejections in `migrate.py` — requires an actual diff, not an assumption).
7. Delete `corpus.json`, `lenders.json`, `scenarios.json`, and `parser.py`. `migrate.py` becomes the only ingestion path (Excel → `corpus.db`).

Test suite (19 regression tests + 9 evals) is the gate at every step — no swap lands unless the same 17/19 and 9/9 hold.

### 2. Cross-host packaging (Claude Code + Codex)

**Constraint: must work with both Claude Code and Codex CLI.** Claude Code has a plugin/skill system (`.claude-plugin/plugin.json`, `skills/SKILL.md`); Codex has neither — it only speaks MCP plus a plain `AGENTS.md`/`config.toml`. The two hosts share exactly one mechanism: **MCP**. So the portable core is a single host-agnostic `mcp_server.py`, and each host gets a thin, separate adapter on top of it — not one shared plugin package.

```
credit-box-rag/
├── mcp_server.py               # host-agnostic stdio MCP server (official `mcp` Python SDK) — the portable core
├── .claude-plugin/
│   └── plugin.json             # Claude Code adapter: manifest registering mcp_server.py + skill
├── skills/
│   └── loan-pricing-partner/
│       └── SKILL.md            # Claude Code adapter: tool-usage rules (consolidates AGENT_TOOLS.md + CLAUDE_SETUP.md rules)
├── codex/
│   ├── config.toml.example     # Codex adapter: mcp_servers entry pointing at mcp_server.py
│   └── AGENTS.md.snippet       # Codex adapter: same tool-usage rules, in Codex's format (pasted into the user's AGENTS.md)
├── store.py
├── migrate.py
├── reason.py / llm_parse.py / agent_tools.py / query.py   # updated per above
├── corpus/
│   └── city_map.json           # tracked — static config, not derived from Excel
└── (corpus.db, llm_cache.json — gitignored, built locally)
```

- `mcp_server.py` exposes the 9 `CreditBoxAgent` methods as MCP tools 1:1 (`find_lenders`, `get_lender_profile`, `compare_lenders`, `get_fico_ltv_tiers`, `scenario_details`, `get_freshness`, `check_criteria`, `estimate_pricing`, `what_if`), plus one new tool: `ingest_excel(path)` running `migrate.py` against a user-supplied Excel file — this is the first-run setup path, driven conversationally instead of a manual shell step.
- **Tool-usage rules are authored once**, in `skills/loan-pricing-partner/SKILL.md`, and mechanically mirrored into `codex/AGENTS.md.snippet` (same content, Codex's plain-markdown convention instead of skill frontmatter) so the two hosts never drift into different agent behavior.
- **Claude Code adapter**: `.claude-plugin/plugin.json` (fields: `name`, `description`, `version`, `author` — confirmed against the current plugin manifest schema) + `skills/` directory, installed via `--plugin-dir` for local testing or a marketplace for distribution.
- **Codex adapter**: no plugin system exists, so distribution is a documented manual step — `codex/config.toml.example` shows the `mcp_servers` block to copy into the user's Codex config, pointing at `mcp_server.py`; `codex/AGENTS.md.snippet` shows the block to paste into the user's `AGENTS.md`.
- **Data distribution decision:** neither adapter ships data. `corpus.db` and `llm_cache.json` are gitignored and built per-machine via `ingest_excel`, because the underlying data is derived from a private, credential-bearing Excel workbook. `city_map.json` (static suburb→metro config, not derived from the sensitive source) ships tracked.
- Credential handling is unchanged from the current system (values are tagged `sensitive` at ingestion and already excluded from agent-facing output) — worth re-verifying once `store.py` lands, not redesigning.

### 3. Testing / validation

- Existing 19 regression tests + 9 evals remain the acceptance bar through every incremental swap (2 known failures excluded per scope decision).
- New: a `store.py` smoke test — round-trip known lenders/attributes and confirm identical output to the old `_db()` path before it's deleted.
- New: MCP server smoke test — list tools, call `find_lenders` with a known query, assert parity with `query.py`'s result. Run once, used by both host adapters (no host-specific server logic to duplicate-test).
- New: fresh-clone smoke test — `git clone` → `ingest_excel` against a sample Excel → `find_lenders` returns results, run against both the Claude Code adapter (`--plugin-dir`) and a local Codex config pointed at `mcp_server.py`. This is the actual "does it work on another machine, with either tool" check.

### 4. Rollout order

1. `git init` in `credit-box-rag/` — done (baseline commit captures pre-surgery state).
2. Data model unification, steps 1–7 above, committing after each verified swap.
3. Build `mcp_server.py` (host-agnostic core), then the two thin adapters on top of it.
4. Final smoke test: fresh clone + `ingest_excel` + a handful of `query.py`/MCP calls, verified under both Claude Code and Codex.

## Phase 2: Loan Copilot Reasoning Architecture (roadmap, not yet scheduled)

Precondition: Phase 1 complete and merged. Phase 2 rebuilds the reasoning layer on top of the unified store — it does not touch `store.py`'s schema responsibilities.

### Critiques of the current theory (why Phase 2 exists)

1. **The hard-constraint/nuanced-reasoning split is simulated, not real.** `reason.py`'s single scoring function blends `typed` and `text`-confidence attributes into one number with hand-tuned weights. A lender that fails a hard FICO cutoff and one that's merely ambiguous in a narrative note currently look the same kind of "less likely" — they should not.
2. **"Multiple potential scenarios" is a data-model gap.** Today: one input → one parsed criteria dict → one ranked list. There's no structure for "if LTV is ARV-based you get lenders {A,B,C}; if purchase-based, {D,E}" — `what_if` is a manual single re-run, not a branching output.
3. **Structured intake wasn't a first-class path.** The system was built assuming a human types a sentence. The actual primary use case is structured deal data arriving programmatically (via MCP), with chat as a secondary channel for explanation and scenario mutation only.
4. **No outcome feedback loop.** Evals check internal consistency (no hallucinated values, valid sources) but nothing checks recommendations against what actually happened when a deal was submitted. The system's usefulness is currently unfalsifiable.
5. **Confidence is captured at ingestion and discarded by output time.** A score of `1.00` reads the same whether it rested on a hard numeric cutoff or a regex-guessed reading of a paragraph.
6. **A single opaque score won't stay debuggable or explainable** as more lenders and edge cases accumulate, and it structurally can't support branching into multiple scenarios (#2).

### Corrected interaction model

Primary path: structured deal data arrives (`DealInput`, via MCP) → Stage 1 filter → Stage 2 reasoning → `ScenarioSet` returned. **No clarifying-question loop by default.** Chat is secondary, used only to (a) explain or expand a `rationale`/`citation`, or (b) supply new/changed structured info that mutates the criteria and re-runs the pipeline — this is what `what_if` already does; it becomes the primary refinement mechanism rather than a side tool. The existing R1–R5 pushback rules (`AGENT_TOOLS.md`) shift from *blocking on ambiguity* to *triggering a multi-scenario branch* — ambiguity produces more than one `Scenario` in the output instead of a forced clarifying question.

### Two-stage reasoning engine (replaces single-score `CreditBoxEngine`)

- **Stage 1 — Constraint filter (deterministic, no LLM).** Operates only on `typed`-confidence attributes via `store.py`. Each hard constraint (FICO floor, LTV ceiling, loan amount range, state/city coverage) is an explicit pass/fail check with cited evidence. A lender structurally qualifies or it doesn't — no score.
- **Stage 2 — LLM reasoning over survivors only.** Lenders that pass Stage 1 get their `text`/`inferred` attributes (narrative UW notes, scenario prose, decision-matrix conditions) handed to the agent for ranking and annotation. Nuance is explicitly scoped to a small survivor set, not all ~90 lenders.

### Object model

```python
Citation = {
    "id": str,              # "c1"
    "source_type": "attribute" | "scenario_rule" | "decision_matrix"
                   | "credit_grid" | "experience_matrix",
    "source_sheet": str,
    "source_row": int | None,
    "attr_name": str | None,
    "raw_text": str,        # the actual cell/paragraph text this claim rests on
    "confidence": "typed" | "text" | "manual" | "inferred",
}

LenderMatch = {
    "lender": str,
    "stage1": [              # hard constraint checks, always citable to typed data
        {"constraint": "fico_min", "threshold": 680, "actual": 640,
         "passes": bool, "citation_id": "c1"}
    ],
    "stage2": {
        "citations": [Citation, ...],
        "rationale": str,    # narrative that inline-references citations, e.g.
                              # "handles heavy rehab [c3], no seasoning requirement [c5]"
    },
    "confidence": "high" | "medium" | "low",  # derived from the citation confidence mix
}

Scenario = {
    "interpretation": str,   # "LTV based on ARV"
    "criteria": Criteria,    # resolved structured deal params for this branch
    "eligible_lenders": [LenderMatch, ...],
    "confidence": "high" | "medium" | "low",
}

ScenarioSet = list[Scenario]
```

**Citation granularity: per-claim, inline-referenced.** `rationale` text must reference citation IDs inline (`[c3]`) rather than carrying one aggregate, unmapped citation list per lender. This requires a **citation validator** — a new gate that runs on every Stage 2 output before it's returned, checking: (a) every `[cN]` tag in `rationale` resolves to a declared `Citation`, (b) every `Citation` resolves to a real `(source_sheet, source_row, raw_text)` in the store, (c) no claim-bearing sentence in `rationale` lacks a citation tag (heuristic check). This subsumes and replaces the current post-hoc `source_integrity` / `no_hallucinated_values` evals — citation correctness becomes a structural gate on generation, not a downstream check on output.

### Structured intake path

A pydantic `DealInput` schema (borrower: FICO/experience/reserves; property: address/type/units; loan: amount/purpose/LTV) as a second entry point into the same internal `Criteria` object that NL parsing already produces. Exposed as an additional parameter shape on the Phase-1 MCP tools (`find_lenders(query: str | DealInput)`), not a separate server — designed generically now since there's no specific upstream system yet, so any future MCP client can populate it without new plumbing.

### Outcome feedback loop (new, minimal)

A `deal_outcomes` table in `corpus.db`: `{scenario_snapshot, submitted_lender, outcome (accepted/declined/repriced), actual_terms, notes, timestamp}`. Populated manually via a `log_outcome(...)` tool after a deal closes or dies — no ML on top of it yet. The value is having ground truth to eventually check recommendations against; without it, the system's usefulness claim stays unfalsifiable.

### Explicitly deferred (named, not solved in Phase 2)

- Live reconciliation against actual lender portals/rate sheets — the real long-term staleness risk, beyond the existing 30/90-day warning. Flagged as a known risk, not addressed here.
- Any ML/learning from `deal_outcomes` data — Phase 2 only captures it; using it is a future phase.

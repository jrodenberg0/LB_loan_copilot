# Loan Copilot Phase 1: Data Model Unification + Cross-Host MCP Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify `credit-box-rag`'s two data stores (`corpus.json` + `corpus.db`) onto SQLite behind a single `store.py` access layer, fix the attribute-name drift bug this exposes in `reason.py`, then package the system as a host-agnostic MCP server with thin adapters for Claude Code and Codex CLI.

**Architecture:** Introduce `store.py` as the only module that touches `corpus/corpus.db`. Migrate every consumer (`reason.py`, `agent_tools.py`, `query.py`, `evals.py`, `build_llm_cache.py`) onto it one file at a time, gated by the existing 19-test/9-eval regression suite at every step. Once unified, wrap the 9 `CreditBoxAgent` tools in a single `mcp_server.py`, then add a `.claude-plugin/` adapter and a `codex/` adapter on top of that one server.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`, `pytest` (new dependency — used only for the new `store.py`/`mcp_server.py` test files; existing regression suite stays on `test_runner.py`), `mcp` Python SDK (`pip install mcp`) for the server.

## Global Constraints

- The 19 regression tests in `tests.json` (via `test_runner.py`) and the 9 evals (via `evals.py`) are the acceptance gate at every task below. Baseline: 17/19 tests pass (`chicago-cook-restrictions` and `fast-close` fail and stay excluded — do not fix them in this plan), 9/9 evals pass.
- `corpus.db`, `corpus.db-shm`, `corpus.db-wal`, `corpus.json`, `lenders.json`, `scenarios.json`, `llm_cache.json` are gitignored (already done) — never re-add them to git.
- No credential values (`user_name`, `password` attrs) are ever returned by any new `store.py` function without a `sensitive: True` flag attached.
- Every commit must leave `test_runner.py` and `evals.py` at the gate above — commit only after verifying, never before.

---

### Task 1: Diagnose the 129-vs-91 lender count discrepancy

**Files:**
- Create: `scripts/diff_lender_sources.py`
- Create: `docs/superpowers/specs/2026-08-28-lender-diff-findings.md`

**Interfaces:**
- Produces: a written, human-reviewed conclusion on whether `migrate.py`'s 91-lender output is missing real lenders that `parser.py`'s 129-lender output captured. This conclusion gates Task 9 (deleting `corpus.json`) — if lenders are missing, `migrate.py` needs a fix before Task 9, not after.

- [ ] **Step 1: Write the diagnostic script**

```python
"""One-off diagnostic: compare lender coverage between corpus.json (parser.py)
and corpus.db (migrate.py). Read-only, no side effects."""
import json, sqlite3
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "corpus"

def json_lenders():
    data = json.loads((CORPUS_DIR / "corpus.json").read_text())
    return set(r["lender_canonical"] for r in data["records"])

def db_lenders():
    conn = sqlite3.connect(str(CORPUS_DIR / "corpus.db"))
    canonical = set(r[0] for r in conn.execute("SELECT canonical_name FROM lenders"))
    aliases = set(r[0] for r in conn.execute("SELECT alias FROM lender_aliases"))
    conn.close()
    return canonical, aliases

if __name__ == "__main__":
    jl = json_lenders()
    db_canonical, db_aliases = db_lenders()
    only_in_json = jl - db_canonical - db_aliases
    print(f"corpus.json lenders: {len(jl)}")
    print(f"corpus.db canonical: {len(db_canonical)}, aliases: {len(db_aliases)}")
    print(f"\nIn corpus.json but NOT in corpus.db (canonical or alias): {len(only_in_json)}")
    for name in sorted(only_in_json):
        print(f"  - {name}")
```

- [ ] **Step 2: Run it and capture output**

Run: `python3 scripts/diff_lender_sources.py`

Read every name in the "only in corpus.json" list. For each, manually check: does it appear in `corpus/corpus.db`'s `lender_aliases` table under a different spelling (e.g., via `sqlite3 corpus/corpus.db "SELECT * FROM lender_aliases WHERE alias LIKE '%<partial name>%'"`)? Does it correspond to a row `migrate.py` legitimately rejected (e.g., a `VOTE COLUMN` artifact or a numeric value misread as a lender name, per `README.md`'s known quirks)?

- [ ] **Step 3: Write findings to `docs/superpowers/specs/2026-08-28-lender-diff-findings.md`**

Document, for every name in the diff: which category it falls into (alias-under-different-spelling / legitimate-rejection / genuinely-missing-real-lender), with the evidence. If any name is genuinely a missing real lender, stop this plan and fix `migrate.py`'s parsing for that sheet/row before proceeding — that is a blocking data-integrity bug, not something Task 9 can paper over.

- [ ] **Step 4: Commit**

```bash
git add scripts/diff_lender_sources.py docs/superpowers/specs/2026-08-28-lender-diff-findings.md
git commit -m "docs: reconcile 129-vs-91 lender count discrepancy between corpus.json and corpus.db"
```

---

### Task 2: Create `store.py` with the core loader (parity with `reason.load_all_from_db`)

**Files:**
- Create: `store.py`
- Create: `tests/test_store.py`
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Produces: `store.load_all() -> dict` with keys `meta`, `records`, `scenarios`, `credit_grids`, `underwriting`, `_lenders` — identical shape to `reason.load_all_from_db()`. `store._db() -> sqlite3.Connection` (module-level cached connection, same caching pattern as `reason._db`).
- Consumes: `corpus/corpus.db` (existing schema, unchanged).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import store

def test_load_all_returns_expected_keys():
    data = store.load_all()
    assert set(data.keys()) == {"meta", "records", "scenarios", "credit_grids", "underwriting", "_lenders"}

def test_load_all_finds_known_lender():
    data = store.load_all()
    lenders = set(r["lender_canonical"] for r in data["records"])
    assert "CV3" in lenders
    assert "Constructive" in lenders

def test_load_all_record_shape():
    data = store.load_all()
    cv3_records = [r for r in data["records"] if r["lender_canonical"] == "CV3" and r["product"] == "sfr_dscr"]
    assert any(r["attr_name"] == "fico_requirement_at_max_ltv" for r in cv3_records)
    rec = next(r for r in cv3_records if r["attr_name"] == "fico_requirement_at_max_ltv")
    assert rec["attr_value"] == 660.0
    assert rec["source_sheet"]
    assert rec["source_row"] == 28
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Write `store.py`** (moved verbatim from `reason.py`'s `_db()` and `load_all_from_db()`, so behavior is proven identical before anything downstream changes)

```python
"""
Single data-access layer for credit-box-rag.

This is the only module permitted to open corpus/corpus.db directly.
Every other module (reason.py, agent_tools.py, query.py, evals.py,
build_llm_cache.py) reads through the functions here.
"""

import json, sqlite3
from pathlib import Path
from collections import defaultdict

CORPUS_DIR = Path(__file__).parent / "corpus"
DB_PATH = CORPUS_DIR / "corpus.db"

# Attribute names whose values must never be surfaced to an agent/user
# without a sensitive=True flag attached.
SENSITIVE_ATTR_NAMES = {"user_name", "password"}


def _db():
    if not hasattr(_db, "conn") or _db.conn is None:
        if not DB_PATH.exists():
            raise RuntimeError(f"Corpus DB not found at {DB_PATH}. Run `python3 migrate.py` first.")
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _db.conn = conn
    return _db.conn


def load_all():
    """Load all corpus data from the typed SQLite schema into a dict.

    Shape matches the pre-store.py `reason.load_all_from_db()` exactly,
    so this is a drop-in replacement.
    """
    db = _db()

    records = []
    for row in db.execute("""
        SELECT
            l.canonical_name AS lender,
            l.canonical_name AS lender_canonical,
            p.name AS product,
            a.name AS attr_name,
            COALESCE(lav.value_numeric, lav.value_text, '') AS attr_value,
            lav.raw_text AS raw_text,
            lav.source_sheet,
            lav.source_row,
            'text' AS confidence
        FROM lender_attr_values lav
        JOIN lenders l ON l.id = lav.lender_id
        JOIN products p ON p.id = lav.product_id
        JOIN attribute_definitions a ON a.id = lav.attr_id
        WHERE lav.import_id = (SELECT MAX(id) FROM imports)
    """).fetchall():
        r = dict(row)
        r["sensitive"] = r["attr_name"] in SENSITIVE_ATTR_NAMES
        records.append(r)

    scenarios_map = {}
    for row in db.execute("""
        SELECT scenario_id, condition, product_type, recommendation_lender, recommendation_detail, source_sheet, source_row
        FROM scenarios
        WHERE import_id = (SELECT MAX(id) FROM imports)
        ORDER BY source_row
    """).fetchall():
        s = dict(row)
        sid = s["scenario_id"]
        if sid not in scenarios_map:
            scenarios_map[sid] = {
                "scenario_id": sid,
                "condition": s["condition"],
                "product_type": s["product_type"],
                "recommendations": [],
                "source_sheet": s["source_sheet"],
                "source_row": s["source_row"],
            }
        scenarios_map[sid]["recommendations"].append({
            "lender_canonical": str(s["recommendation_lender"] or ""),
            "detail": str(s["recommendation_detail"] or ""),
        })
    scenarios = list(scenarios_map.values())

    credit_grids = []
    for row in db.execute("""
        SELECT cg.*, l.canonical_name AS lender_canonical
        FROM credit_grids cg
        JOIN lenders l ON l.id = cg.lender_id
        WHERE cg.import_id = (SELECT MAX(id) FROM imports)
    """).fetchall():
        g = dict(row)
        grid = {}
        if g.get("min_fico") is not None:
            grid[str(int(g["min_fico"]))] = g.get("ltv_purchase") or ""
        g["grid"] = grid
        g["lender_canonical"] = g.get("lender_canonical", "")
        g["source_sheet"] = g.get("source_sheet", "CS-CREDIT")
        credit_grids.append(g)

    underwriting = []
    for row in db.execute("""
        SELECT em.*, l.canonical_name AS lender_canonical
        FROM experience_matrices em
        JOIN lenders l ON l.id = em.lender_id
        WHERE em.import_id = (SELECT MAX(id) FROM imports)
    """).fetchall():
        u = dict(row)
        underwriting.append({
            "lender": u.get("lender_canonical", ""),
            "lender_canonical": u.get("lender_canonical", ""),
            "source_sheet": u.get("source_sheet", "CS-EXPERIENCE"),
            "type": "experience_matrix",
            "data": json.dumps({"exp_level": u.get("exp_level"), "ltc_terms": u.get("ltc_terms")}),
        })

    meta = {}
    for row in db.execute("SELECT key, value FROM meta").fetchall():
        meta[row["key"]] = row["value"]

    lenders = {}
    for row in db.execute("SELECT canonical_name FROM lenders").fetchall():
        lenders[row["canonical_name"]] = {"canonical": row["canonical_name"]}

    return {
        "meta": meta,
        "records": records,
        "scenarios": scenarios,
        "credit_grids": credit_grids,
        "underwriting": underwriting,
        "_lenders": lenders,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add store.py tests/
git commit -m "feat: add store.py with load_all(), moved verbatim from reason.load_all_from_db"
```

---

### Task 3: Add lender/scenario/freshness accessor functions to `store.py`

**Files:**
- Modify: `store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: `store.load_all()`, `store._db()` from Task 2.
- Produces:
  - `store.get_lender_records(lender: str, product: str = None) -> list[dict]` — replaces the `corpus.json` filtering currently duplicated in `agent_tools.get_lender_profile`, `query.cmd_show_lender`, `query.cmd_compare`, `query.cmd_show_tiers`.
  - `store.get_lenders_index() -> dict[str, dict]` — `{canonical_name: {"aliases": [...], "products": [...]}}`, replaces `corpus/lenders.json`.
  - `store.get_scenarios() -> list[dict]` — replaces `corpus/scenarios.json`.
  - `store.get_freshness() -> dict` — replaces the `corpus.json`-meta-based freshness fields in `agent_tools.get_freshness` and `query.cmd_freshness`, using the real `imports` table columns (`file_path`, `file_mtime`, `imported_at`) instead of the nonexistent `file_age_days`/`file_size_bytes`/`generated` meta keys the old code assumed.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_store.py

def test_get_lender_records_filters_by_lender_and_product():
    recs = store.get_lender_records("CV3", "sfr_dscr")
    assert all(r["lender_canonical"] == "CV3" and r["product"] == "sfr_dscr" for r in recs)
    assert any(r["attr_name"] == "fico_requirement_at_max_ltv" for r in recs)

def test_get_lender_records_no_product_filter_returns_all_products():
    recs = store.get_lender_records("CV3")
    products = set(r["product"] for r in recs)
    assert "sfr_dscr" in products
    assert "fix_and_flip" in products

def test_get_lenders_index_has_products_list():
    idx = store.get_lenders_index()
    assert "CV3" in idx
    assert "sfr_dscr" in idx["CV3"]["products"]
    assert isinstance(idx["CV3"]["aliases"], list)

def test_get_scenarios_returns_conditions():
    scenarios = store.get_scenarios()
    assert len(scenarios) > 0
    assert all("condition" in s for s in scenarios)

def test_get_freshness_has_real_fields():
    fresh = store.get_freshness()
    assert "file_path" in fresh
    assert "file_mtime" in fresh
    assert "imported_at" in fresh
    assert "age_days" in fresh
    assert isinstance(fresh["age_days"], float)
    assert "n_records" in fresh and fresh["n_records"] > 0
    assert "n_lenders" in fresh and fresh["n_lenders"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: 5 new FAILs with `AttributeError: module 'store' has no attribute 'get_lender_records'` (etc.)

- [ ] **Step 3: Add the functions to `store.py`**

```python
import datetime


def get_lender_records(lender, product=None):
    """All EAV records for a lender, optionally filtered by product."""
    data = load_all()
    return [
        r for r in data["records"]
        if r["lender_canonical"].lower() == lender.lower()
        and (product is None or r["product"] == product)
    ]


def get_lenders_index():
    """Replacement for corpus/lenders.json: {canonical_name: {aliases, products}}."""
    db = _db()
    index = {}
    for row in db.execute("SELECT id, canonical_name FROM lenders").fetchall():
        lender_id, canonical = row["id"], row["canonical_name"]
        aliases = [
            r["alias"] for r in
            db.execute("SELECT alias FROM lender_aliases WHERE lender_id = ?", (lender_id,)).fetchall()
        ]
        products = [
            r["name"] for r in db.execute("""
                SELECT p.name FROM product_offerings po
                JOIN products p ON p.id = po.product_id
                WHERE po.lender_id = ?
            """, (lender_id,)).fetchall()
        ]
        index[canonical] = {"aliases": aliases, "products": products}
    return index


def get_scenarios():
    """Replacement for corpus/scenarios.json."""
    return load_all()["scenarios"]


def get_freshness():
    """Data freshness report, derived from the imports table (not a synthetic meta blob)."""
    db = _db()
    row = db.execute("""
        SELECT file_path, file_mtime, imported_at
        FROM imports
        ORDER BY id DESC LIMIT 1
    """).fetchone()

    data = load_all()
    n_records = len(data["records"])
    n_lenders = len(data["_lenders"])
    n_scenarios = len(data["scenarios"])

    age_days = None
    if row and row["imported_at"]:
        imported_at = datetime.datetime.fromisoformat(row["imported_at"].replace(" ", "T"))
        age_days = (datetime.datetime.now() - imported_at).total_seconds() / 86400

    return {
        "file_path": row["file_path"] if row else None,
        "file_mtime": row["file_mtime"] if row else None,
        "imported_at": row["imported_at"] if row else None,
        "age_days": age_days,
        "n_records": n_records,
        "n_lenders": n_lenders,
        "n_scenarios": n_scenarios,
        "fresh": age_days is not None and age_days < 30,
        "stale": age_days is not None and age_days >= 30,
        "critically_stale": age_days is not None and age_days >= 90,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: add get_lender_records, get_lenders_index, get_scenarios, get_freshness to store.py"
```

---

### Task 4: Swap `reason.py` onto `store.py` and fix attribute-name drift

**Files:**
- Modify: `reason.py:1-183` (imports, `_db`/`load_all_from_db` removal, `CreditBoxEngine.__init__`)
- Modify: `reason.py:648, 265, 784, 797, 824-828` (hardcoded attribute names)

**Interfaces:**
- Consumes: `store.load_all()` (Task 2).
- Produces: `CreditBoxEngine` behaves identically for consumers (`agent_tools.py`, `query.py`, `evals.py`, `test_runner.py`) — same public methods, same return shapes. Internal data source changes; attribute names it looks up are corrected.

- [ ] **Step 1: Confirm current baseline before touching anything**

Run: `python3 test_runner.py`
Expected: `17/19 passed, 2/19 failed` (failures: `chicago-cook-restrictions`, `fast-close`)

Run: `python3 evals.py`
Expected: `9 passed, 0 warned, 0 failed`

- [ ] **Step 2: Remove `_db()` and `load_all_from_db()` from `reason.py`, import from `store` instead**

In `reason.py`, delete lines 8-17 (`import ... sqlite3`, `CORPUS_DIR`, `DB_PATH`) and lines 61-175 (`_db()` and `load_all_from_db()`). Replace the top of the file with:

```python
import json, re, sys
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

from llm_parse import parse_state_coverage, parse_fico_ltv_tiers, state_includes, fico_matches
import store

CORPUS_DIR = Path(__file__).parent / "corpus"
```

Change `CreditBoxEngine.__init__`:

```python
class CreditBoxEngine:
    def __init__(self, data=None):
        if data is not None:
            self.data = data
        else:
            self.data = store.load_all()
        self._build_index()
```

- [ ] **Step 3: Fix the 7 hardcoded attribute-name mismatches**

In `_build_index` (the `parsed_fico_tiers` block), change:
```python
elif attr_name in ("fico_at_max_ltv", "fico_qualification", "dscr_range",
                    "ltv_purchase_max", "ltv_cashout_max"):
```
to:
```python
elif attr_name in ("fico_requirement_at_max_ltv", "fico_qualification", "dscr_range",
                    "max__ltv_purchase", "max__ltv_cash_out_refi"):
```

In `query()`'s FICO-check block, change every occurrence of `"fico_at_max_ltv"` to `"fico_requirement_at_max_ltv"` and every occurrence of `("fico_at_max_ltv", "fico_qualification", "ltv_purchase_max", "ltv_cashout_max")` to `("fico_requirement_at_max_ltv", "fico_qualification", "max__ltv_purchase", "max__ltv_cash_out_refi")`.

In the loan-amount check block, change:
```python
min_recs = self.get_lender_attr(lender, product or "fix_and_flip", "loan_min")
...
max_recs = self.get_lender_attr(lender, product or "fix_and_flip", "loan_max")
```
to:
```python
min_recs = self.get_lender_attr(lender, product or "fix_and_flip", "min_loan_amount")
...
max_recs = self.get_lender_attr(lender, product or "fix_and_flip", "max_loan_amount")
```

In the experience check block, change:
```python
exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                "experience_minimum_(see_experience_cheat_sheet)")
if not exp_recs:
    exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                    "min_experience_for_max_ltc_arv")
```
to:
```python
exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                "experience_minimum_see_experience_cheat_sheet")
if not exp_recs:
    exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                    "min_experience_for_max_ltcarv")
```

And in `_build_index`'s experience index block, the substring match already uses `.replace('_', '').replace(' ', '')` before checking `'experienceminimum' in no_under`, so it's tolerant of the parenthesis/underscore differences — no change needed there, but leave a comment noting why:
```python
# Note: substring match here is already tolerant of the
# experience_minimum_(see_experience_cheat_sheet) vs
# experience_minimum_see_experience_cheat_sheet naming difference.
```

- [ ] **Step 4: Run the regression suite and evals, resolve any surfaced differences**

Run: `python3 test_runner.py`

Compare against the Step 1 baseline. The two known failures must still fail for the same stated reasons. If any of the other 17 change status:
- If a previously-passing test now fails: the fixed attribute names surfaced a real behavior change — inspect `test_runner.py --id <id> --verbose` output, determine whether the new (correct) behavior is actually right, and either fix the test's expectation in `tests.json` (with a comment explaining why) or find a remaining bug in the rename. Do not proceed until you understand which.
- If matches/scores changed but pass/fail status is identical: expected, since previously-dead lookups are now live. No action needed beyond confirming still-passing tests still pass.

Run: `python3 evals.py`
Expected: `9 passed, 0 warned, 0 failed` (evals.py still reads via `reason.load_all_from_db` at this point — Task 5 fixes that import path, not this one; confirm it still works because `reason.py` still needs to export something evals.py imports — see Step 5).

- [ ] **Step 5: Keep a thin backward-compatible alias for `evals.py` until Task 5**

Since `evals.py:35` still does `from reason import load_all_from_db`, add a one-line shim at the bottom of `reason.py`'s import section (removed again in Task 5):
```python
# Temporary shim for evals.py — removed in the store.py swap for evals.py (Task 5)
load_all_from_db = store.load_all
```

- [ ] **Step 6: Re-run full suite one more time to confirm the shim works**

Run: `python3 test_runner.py && python3 evals.py`
Expected: same result as Step 4/4 above.

- [ ] **Step 7: Commit**

```bash
git add reason.py
git commit -m "refactor: swap reason.py onto store.py, fix 7 hardcoded attribute-name mismatches

Attribute names in reason.py were written against parser.py's naming
and drifted from migrate.py's normalized names (fico_at_max_ltv vs
fico_requirement_at_max_ltv, loan_min/loan_max vs min_loan_amount/
max_loan_amount, etc). These lookups were silently returning nothing.
Fixed to match corpus.db's real attribute_definitions."
```

---

### Task 5: Swap `evals.py` onto `store.py`

**Files:**
- Modify: `evals.py:29-49, 464-491`

**Interfaces:**
- Consumes: `store.load_all()`.
- Produces: same `run_evals()`, `verify_query()` public API, unchanged for `query.py` and `test_runner.py`.

- [ ] **Step 1: Replace the `reason.load_all_from_db` import**

In `run_evals()`, change:
```python
    if corpus is None:
        from reason import load_all_from_db
        corpus = load_all_from_db()
```
to:
```python
    if corpus is None:
        import store
        corpus = store.load_all()
```

Do the same in `verify_query()` (currently at line ~467).

- [ ] **Step 2: Replace the `__main__` block's `corpus.json` read**

Change:
```python
    with open(CORPUS_DIR / "corpus.json") as f:
        corpus = json.load(f)
```
to:
```python
    import store
    corpus = store.load_all()
```

- [ ] **Step 3: Remove the now-unused `reason.load_all_from_db` shim from `reason.py`**

Delete the one line added in Task 4 Step 5:
```python
load_all_from_db = store.load_all
```

- [ ] **Step 4: Run the regression suite**

Run: `python3 test_runner.py && python3 evals.py`
Expected: identical to Task 4 Step 4's final result — same 17/19, same 9/9.

- [ ] **Step 5: Commit**

```bash
git add evals.py reason.py
git commit -m "refactor: swap evals.py onto store.py, remove reason.py backward-compat shim"
```

---

### Task 6: Swap `agent_tools.py` onto `store.py`

**Files:**
- Modify: `agent_tools.py:22-36, 64-86, 142-177`

**Interfaces:**
- Consumes: `store.get_lender_records()`, `store.get_lenders_index()`, `store.get_scenarios()`, `store.get_freshness()`.
- Produces: `CreditBoxAgent`'s 9 public methods, unchanged signatures — this is the class the future `mcp_server.py` (Task 10) wraps, so its public contract must not shift.

- [ ] **Step 1: Replace `_load_cache` and remove direct `corpus.json`/`lenders.json`/`scenarios.json` reads**

Change:
```python
import json, re
from pathlib import Path
from collections import defaultdict

from reason import CreditBoxEngine
from llm_parse import state_includes, fico_matches, parse_fico_ltv_tiers, parse_state_coverage

CORPUS_DIR = Path(__file__).parent / "corpus"


class CreditBoxAgent:
    def __init__(self):
        self.engine = CreditBoxEngine()
        self._load_cache()

    def _load_cache(self):
        cp = CORPUS_DIR / "llm_cache.json"
        self.cache = json.loads(cp.read_text()) if cp.exists() else {}
        cp2 = CORPUS_DIR / "corpus.json"
        self.corpus = json.loads(cp2.read_text())
        self.lenders = json.loads((CORPUS_DIR / "lenders.json").read_text())
        self.scenarios = json.loads((CORPUS_DIR / "scenarios.json").read_text())
```
to:
```python
import json, re
from pathlib import Path
from collections import defaultdict

from reason import CreditBoxEngine
from llm_parse import state_includes, fico_matches, parse_fico_ltv_tiers, parse_state_coverage
import store

CORPUS_DIR = Path(__file__).parent / "corpus"


class CreditBoxAgent:
    def __init__(self):
        self.engine = CreditBoxEngine()
        self._load_cache()

    def _load_cache(self):
        cp = CORPUS_DIR / "llm_cache.json"
        self.cache = json.loads(cp.read_text()) if cp.exists() else {}
        self.lenders = store.get_lenders_index()
        self.scenarios = store.get_scenarios()
```

- [ ] **Step 2: Fix `get_lender_profile` to use `store.get_lender_records`**

Change:
```python
    def get_lender_profile(self, lender: str, product: str = None) -> dict:
        """All attributes for a lender, optionally by product."""
        records = [
            r for r in self.corpus["records"]
            if r["lender_canonical"].lower() == lender.lower()
            and (not product or r["product"] == product)
        ]
```
to:
```python
    def get_lender_profile(self, lender: str, product: str = None) -> dict:
        """All attributes for a lender, optionally by product."""
        records = store.get_lender_records(lender, product)
```

- [ ] **Step 3: Fix `scenario_details` to use `self.scenarios` (already reassigned in Step 1) — no code change needed, just confirm**

`scenario_details` already reads `self.corpus.get("scenarios", [])` — change that one reference to `self.scenarios`:
```python
    def scenario_details(self, scenario_text: str) -> dict:
        """Full recommendation text for a scenario."""
        for s in self.scenarios:
            if scenario_text.lower() in s["condition"].lower():
                ...
        for s in self.scenarios:
            if any(w in s["condition"].lower() for w in scenario_text.lower().split()):
                return self.scenario_details(s["condition"])
        return {"error": f"Scenario '{scenario_text}' not found"}
```

- [ ] **Step 4: Fix `compare_lenders` and `get_fico_ltv_tiers`, which both read `self.corpus["records"]`**

`compare_lenders` calls `get_lender_profile` internally already — no `self.corpus` reference there, no change needed.

`get_fico_ltv_tiers` change:
```python
    def get_fico_ltv_tiers(self, lender: str, product: str = None) -> dict:
        """Structured FICO/LTV tier data for a lender."""
        records = [
            r for r in self.corpus["records"]
            if r["lender_canonical"].lower() == lender.lower()
            and r["attr_name"] in ("fico_at_max_ltv", "fico_qualification",
                                    "dscr_range", "ltv_purchase_max", "ltv_cashout_max")
            and (not product or r["product"] == product)
        ]
```
to:
```python
    def get_fico_ltv_tiers(self, lender: str, product: str = None) -> dict:
        """Structured FICO/LTV tier data for a lender."""
        all_records = store.get_lender_records(lender, product)
        records = [
            r for r in all_records
            if r["attr_name"] in ("fico_requirement_at_max_ltv", "fico_qualification",
                                    "dscr_range", "max__ltv_purchase", "max__ltv_cash_out_refi")
        ]
```
(Same attribute-name fix as Task 4, applied here since this is a second place the old names were hardcoded.)

- [ ] **Step 5: Fix `get_freshness` to use `store.get_freshness()`**

Change:
```python
    def get_freshness(self) -> dict:
        meta = self.corpus.get("meta", {})
        age = meta.get("file_age_days", 0)
        return {
            "source": meta.get("source", ""),
            "file_mtime": meta.get("file_mtime", ""),
            "file_age_days": age,
            "parsed": meta.get("generated", ""),
            "n_records": len(self.corpus.get("records", [])),
            "n_lenders": len(self.lenders),
            "n_scenarios": len(self.corpus.get("scenarios", [])),
            "fresh": age < 30,
            "stale": age >= 30,
            "critically_stale": age >= 90,
        }
```
to:
```python
    def get_freshness(self) -> dict:
        return store.get_freshness()
```

- [ ] **Step 6: Write a smoke test comparing old vs new behavior for the risky renames**

```python
# tests/test_agent_tools.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_tools import CreditBoxAgent

def test_get_lender_profile_returns_real_attrs():
    agent = CreditBoxAgent()
    profile = agent.get_lender_profile("CV3", "sfr_dscr")
    assert "error" not in profile
    assert "fico_requirement_at_max_ltv" in profile["products"]["sfr_dscr"]

def test_get_freshness_has_new_field_names():
    agent = CreditBoxAgent()
    fresh = agent.get_freshness()
    assert "age_days" in fresh
    assert "n_lenders" in fresh and fresh["n_lenders"] > 0

def test_no_credentials_leak_unflagged():
    agent = CreditBoxAgent()
    profile = agent.get_lender_profile("CV3", "sfr_dscr")
    for attr_name, info in profile["products"]["sfr_dscr"].items():
        if attr_name in ("user_name", "password"):
            assert info["sensitive"] is True
```

- [ ] **Step 7: Run tests**

Run: `python3 -m pytest tests/test_agent_tools.py -v && python3 test_runner.py && python3 evals.py`
Expected: 3 new passed, 17/19, 9/9 unchanged.

- [ ] **Step 8: Commit**

```bash
git add agent_tools.py tests/test_agent_tools.py
git commit -m "refactor: swap agent_tools.py onto store.py, remove corpus.json/lenders.json/scenarios.json reads"
```

---

### Task 7: Swap `query.py` onto `store.py`

**Files:**
- Modify: `query.py:21-43, 118-133, 161-192, 195-203, 217-272, 274-352`

**Interfaces:**
- Consumes: `store.get_lender_records()`, `store.get_lenders_index()`, `store.get_scenarios()`, `store.get_freshness()`.
- Produces: same CLI behavior for every `query.py` command (`--show-lender`, `--compare`, `--show-tiers`, `--freshness`, `--list-lenders`, `--list-scenarios`).

- [ ] **Step 1: Replace the three `corpus.json`/`lenders.json`/`scenarios.json` loader functions**

Change:
```python
def load_corpus():
    with open(CORPUS_DIR / "corpus.json") as f:
        return json.load(f)


def load_lenders():
    with open(CORPUS_DIR / "lenders.json") as f:
        return json.load(f)


def load_scenarios():
    with open(CORPUS_DIR / "scenarios.json") as f:
        return json.load(f)
```
to:
```python
import store

def load_scenarios():
    return {"scenarios": store.get_scenarios()}
```
(`load_corpus`/`load_lenders` callers are updated directly in the next steps rather than kept as shims, since every call site needs a different `store` function, not a drop-in dict replacement.)

- [ ] **Step 2: Fix `cmd_query`'s scenario-detail lookup (line ~120)**

Change:
```python
    if sm:
        print(f"  Scenario details:\n")
        data = load_corpus()
        for si_name in sm:
            for s in data["scenarios"]:
```
to:
```python
    if sm:
        print(f"  Scenario details:\n")
        scenarios = store.get_scenarios()
        for si_name in sm:
            for s in scenarios:
```

- [ ] **Step 3: Fix `cmd_freshness` (line ~161)**

Change the whole function body to:
```python
def cmd_freshness():
    fresh = store.get_freshness()

    print(f"\n{'='*60}")
    print(f"  Data Freshness Report")
    print(f"{'='*60}")
    print(f"  Source: {fresh['file_path']}")
    print(f"  File last modified: {(fresh['file_mtime'] or '?')[:16]}")
    print(f"  Imported: {(fresh['imported_at'] or '?')[:16]}")
    age = fresh['age_days'] or 0
    print(f"  Age: {age:.1f} days {'✓' if age < 30 else '⚠' if age < 90 else '✗'}")
    print(f"  Records: {fresh['n_records']}")
    print(f"  Lenders: {fresh['n_lenders']}")
    print(f"  Scenarios: {fresh['n_scenarios']}")
    print(f"  Status: ", end="")
    if fresh['fresh']:
        print("Fresh")
    elif fresh['stale'] and not fresh['critically_stale']:
        print(f"Stale — re-parse recommended ({age:.1f} days old)")
    else:
        print(f"CRITICALLY stale — re-parse needed ({age:.1f} days old)")
    print()
```

- [ ] **Step 4: Fix `cmd_list_lenders` (line ~195)**

Change:
```python
def cmd_list_lenders():
    lenders = load_lenders()
```
to:
```python
def cmd_list_lenders():
    lenders = store.get_lenders_index()
```
(rest of the function is unchanged — it already iterates `lenders.items()` with `info["aliases"]`/`info["products"]`, which `get_lenders_index()` provides in the same shape.)

- [ ] **Step 5: Fix `cmd_show_tiers` (line ~205)**

Change:
```python
    name = " ".join(args)
    cache = json.loads((CORPUS_DIR / "llm_cache.json").read_text())
    data = load_corpus()

    tier_attrs = ["fico_at_max_ltv", "fico_qualification", "dscr_range",
                   "ltv_purchase_max", "ltv_cashout_max"]
    ...
    records = [r for r in data["records"] if r["lender_canonical"].lower() == name.lower()]
```
to:
```python
    name = " ".join(args)
    cache = json.loads((CORPUS_DIR / "llm_cache.json").read_text())

    tier_attrs = ["fico_requirement_at_max_ltv", "fico_qualification", "dscr_range",
                   "max__ltv_purchase", "max__ltv_cash_out_refi"]
    ...
    records = store.get_lender_records(name)
```

- [ ] **Step 6: Fix `cmd_show_lender` (line ~274)**

Change:
```python
    name = " ".join(args)
    data = load_corpus()
    records = [r for r in data["records"] if r["lender_canonical"].lower() == name.lower()]
```
to:
```python
    name = " ".join(args)
    records = store.get_lender_records(name)
```

- [ ] **Step 7: Fix `cmd_compare` (line ~301)**

Change:
```python
    l1, l2 = args[0], args[1]
    data = load_corpus()

    r1 = [r for r in data["records"] if r["lender_canonical"].lower() == l1.lower() and (not product or r["product"] == product)]
    r2 = [r for r in data["records"] if r["lender_canonical"].lower() == l2.lower() and (not product or r["product"] == product)]
```
to:
```python
    l1, l2 = args[0], args[1]
    r1 = store.get_lender_records(l1, product)
    r2 = store.get_lender_records(l2, product)
```

- [ ] **Step 8: Run the manual CLI smoke checks**

Run each and eyeball the output against what `HOW_TO.md`'s examples show:
```bash
python3 query.py "640 FICO Baltimore fix and flip"
python3 query.py --list-lenders
python3 query.py --show-lender "CV3"
python3 query.py --compare "CV3" "Constructive" --product sfr_dscr
python3 query.py --show-tiers "CV3" --product sfr_dscr
python3 query.py --freshness
```
Expected: no tracebacks, same general shape of output as before the swap (freshness numbers will differ slightly — new field names, real `age_days` value — that's expected).

- [ ] **Step 9: Run the regression suite**

Run: `python3 test_runner.py && python3 evals.py`
Expected: unchanged from Task 6.

- [ ] **Step 10: Commit**

```bash
git add query.py
git commit -m "refactor: swap query.py onto store.py, remove corpus.json/lenders.json/scenarios.json reads"
```

---

### Task 8: Swap `build_llm_cache.py` onto `store.py`

**Files:**
- Modify: `build_llm_cache.py:11` (`CORPUS_PATH`) and its usage in `build_cache()`

**Interfaces:**
- Consumes: `store.load_all()`.
- Produces: same `corpus/llm_cache.json` output shape — this file stays a generated, gitignored, machine-local cache; only its input source changes.

- [ ] **Step 1: Read the current usage of `CORPUS_PATH` in `build_cache()`**

Run: `grep -n "CORPUS_PATH" build_llm_cache.py`

- [ ] **Step 2: Replace the `corpus.json` read with `store.load_all()`**

Change:
```python
CORPUS_PATH = Path(__file__).parent / "corpus" / "corpus.json"
```
to:
```python
import store
```
(remove `CORPUS_PATH` entirely)

In `build_cache()`, wherever it does something like:
```python
with open(CORPUS_PATH) as f:
    data = json.load(f)
```
replace with:
```python
data = store.load_all()
```

- [ ] **Step 3: Run the cache rebuild and diff against the previous cache**

```bash
cp corpus/llm_cache.json /tmp/llm_cache_before.json
python3 build_llm_cache.py
python3 -c "
import json
before = json.load(open('/tmp/llm_cache_before.json'))
after = json.load(open('corpus/llm_cache.json'))
print(f'before: {len(before)} entries, after: {len(after)} entries')
missing = set(before) - set(after)
new = set(after) - set(before)
print(f'missing after rebuild: {len(missing)}')
print(f'new after rebuild: {len(new)}')
"
```
Expected: entry counts close to identical (small differences are fine if they trace back to the Task 4 attribute-name fixes surfacing previously-invisible tier text; large unexplained drops mean the swap broke something — investigate before proceeding).

- [ ] **Step 4: Run the regression suite**

Run: `python3 test_runner.py && python3 evals.py`
Expected: unchanged from Task 7.

- [ ] **Step 5: Commit**

```bash
git add build_llm_cache.py
git commit -m "refactor: swap build_llm_cache.py onto store.py"
```

---

### Task 9: Delete `corpus.json`, `lenders.json`, `scenarios.json`, `parser.py`

**Files:**
- Delete: `corpus/corpus.json`, `corpus/lenders.json`, `corpus/scenarios.json`, `parser.py`
- Modify: `CLAUDE_SETUP.md`, `HOW_TO.md`, `README.md` (remove references to the deleted files and to `parser.py` as an ingestion path)

**Interfaces:**
- Precondition: Task 1's findings confirmed no real lenders are lost by relying solely on `migrate.py`. If Task 1 flagged a genuine gap, that must be fixed in `migrate.py` before this task, not worked around here.
- Precondition: Tasks 2–8 complete — grep confirms zero remaining references to `corpus.json`/`lenders.json`/`scenarios.json`/`parser.py` in any `.py` file except this deletion itself.

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "corpus\.json\|lenders\.json\|scenarios\.json\|parser\.py" --include="*.py" .`
Expected: no output (if anything shows up, fix that file before continuing — do not delete the files it still depends on).

- [ ] **Step 2: Delete the files**

```bash
git rm corpus/corpus.json corpus/lenders.json corpus/scenarios.json parser.py
```

(These may already be gitignored/untracked rather than tracked, depending on when they were created relative to the Task 1 `.gitignore` commit — if `git rm` errors with "did not match any files", use plain `rm` instead and confirm they're gone with `ls corpus/`.)

- [ ] **Step 3: Update documentation references**

In `CLAUDE_SETUP.md`, remove the `parser.py` bullet from the file listing (the "Excel → corpus (only needed if data updates)" line) and change the "Updating Data" section's:
```
python3 parser.py ~/Downloads/NewCreditBox.xlsx
python3 generate_llm_cache.py
```
to:
```
python3 migrate.py --excel ~/Downloads/NewCreditBox.xlsx
python3 build_llm_cache.py
```
(matches the actual current filenames — `generate_llm_cache.py` vs `build_llm_cache.py` naming should be double-checked against what exists in the repo at this point in the plan and corrected to whichever one Task 8 actually touched).

Make the equivalent fix in `HOW_TO.md`'s "Data Pipeline" section and `README.md`'s references to `parser.py`.

- [ ] **Step 4: Full regression run — this is the real gate for the whole data-model-unification workstream**

Run: `python3 -m pytest tests/ -v && python3 test_runner.py && python3 evals.py`
Expected: all `store.py`/`agent_tools.py` pytest tests pass, `test_runner.py` reports `17/19 passed, 2/19 failed` (same two known failures), `evals.py` reports `9 passed, 0 warned, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: delete corpus.json/lenders.json/scenarios.json/parser.py

migrate.py is now the sole ingestion path (Excel -> corpus.db).
store.py is the sole data-access layer. Data model unification complete."
```

---

### Task 10: Build the host-agnostic `mcp_server.py`

**Files:**
- Create: `mcp_server.py`
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `agent_tools.CreditBoxAgent` (all 9 public methods), `migrate.py` (as a subprocess for the new `ingest_excel` tool).
- Produces: an MCP stdio server exposing 10 tools (the existing 9 + `ingest_excel`). This is the single portable core both host adapters (Tasks 11–12) point at — no host-specific logic lives here.

- [ ] **Step 1: Install the MCP SDK**

Run: `pip install mcp`

- [ ] **Step 2: Write the failing test** (tests the plain functions directly, not over the MCP wire protocol — sufficient to verify tool logic; Task 13's smoke test covers the actual protocol handshake)

```python
# tests/test_mcp_server.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server'`

- [ ] **Step 4: Write `mcp_server.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_mcp_server.py -v`
Expected: 4 passed

(If `test_server_registers_all_ten_tools` fails because `FastMCP`'s internal API differs from `_tool_manager.list_tools()` in the installed `mcp` package version, run `python3 -c "import mcp; print(mcp.__version__)"` and adjust the introspection call to match that version's `FastMCP` API — check the installed package's `fastmcp.py` source for the actual tool-registry attribute name.)

- [ ] **Step 6: Commit**

```bash
git add mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add host-agnostic mcp_server.py wrapping the 9 CreditBoxAgent tools + ingest_excel"
```

---

### Task 11: Claude Code adapter

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `skills/loan-pricing-partner/SKILL.md`

**Interfaces:**
- Consumes: `mcp_server.py` (Task 10) — this task only adds configuration, no new Python code.

- [ ] **Step 1: Write the manifest**

```json
{
  "name": "credit-box-rag",
  "displayName": "Loan Pricing Partner",
  "version": "0.1.0",
  "description": "Mortgage lending knowledge system for IP Loan Exchange — routes loan deals to wholesale lenders with cited source data.",
  "author": {
    "name": "IP Loan Exchange"
  },
  "mcpServers": "./mcp_server_config.json"
}
```

- [ ] **Step 2: Write the MCP server config the manifest points at**

```json
{
  "mcpServers": {
    "credit-box-rag": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp_server.py"]
    }
  }
}
```
Save as `mcp_server_config.json` at the plugin root (referenced by `plugin.json`'s `mcpServers` field per the confirmed manifest schema, which accepts a path string).

- [ ] **Step 3: Write the skill**

```markdown
---
description: Loan-pricing partner for IP Loan Exchange. Use when routing a mortgage deal to a wholesale lender, comparing lenders, checking eligibility criteria, or estimating pricing.
---

# Loan Pricing Partner

You have access to a mortgage lending knowledge system covering wholesale lenders
across 9 loan products (DSCR, fix-and-flip, new construction, multifamily, bridge,
blanket, commercial), via the `credit-box-rag` MCP server.

## Setup

If any tool call errors with "Corpus DB not found", ask the user for the path to
their Master Credit Box Excel file, then call `ingest_excel(path)`. This is a
one-time step per machine.

## Tools

- `find_lenders(query, max_loan=None)` — route a deal, get ranked lenders with reasoning
- `get_lender_profile(lender, product=None)` — all attributes for a lender
- `compare_lenders(lender1, lender2, product=None)` — side-by-side attribute diff
- `get_fico_ltv_tiers(lender, product=None)` — structured FICO/LTV tier tables
- `scenario_details(scenario_text)` — full recommendation text for a decision rule
- `get_freshness()` — data age; warn the user if stale (>30 days)
- `check_criteria(lender, product, criteria)` — pass/fail check against specific deal params
- `estimate_pricing(lender, product, ltv=None, fico=None)` — best-guess rate range
- `what_if(params)` — re-route with modified parameters
- `ingest_excel(path)` — first-run setup from a local Excel file

## Rules

1. Never fabricate lender data. Always cite sources returned by the tools.
2. Rate shopping without context → refuse. Ask for product, FICO, LTV, loan amount, property type.
3. "80 cents on the dollar" → ask: 80% of ARV or purchase price?
4. 3+ properties without "blanket" mentioned → ask: one blanket loan or individual loans per property?
5. "Light rehab" or "cosmetic" without scope → ask: what kind of work, and cost as % of ARV?
6. Never surface `user_name`/`password` fields — tool results flag these `sensitive: true`; omit them from your response even if present in raw data.
7. Warn if `get_freshness()` reports `stale` or `critically_stale`.
8. Present top 3 matches with a recommendation, not a full dump. Offer to go deeper on any of them.
```

- [ ] **Step 4: Validate the manifest**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('mcp_server_config.json'))"`
Expected: no output (both files parse as valid JSON).

If `claude` CLI is available locally: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 5: Manual local test**

Run: `claude --plugin-dir .` (from `credit-box-rag/`), then in the session try a query like "route a 640 FICO fix and flip deal in Baltimore."
Expected: the skill loads, the MCP tools are callable, `find_lenders` returns results consistent with `python3 query.py "640 FICO Baltimore fix and flip"`.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/ skills/ mcp_server_config.json
git commit -m "feat: add Claude Code plugin adapter (manifest + skill) on top of mcp_server.py"
```

---

### Task 12: Codex adapter

**Files:**
- Create: `codex/config.toml.example`
- Create: `codex/AGENTS.md.snippet`
- Create: `codex/README.md`

**Interfaces:**
- Consumes: `mcp_server.py` (Task 10). Mirrors the same tool-usage rules as `skills/loan-pricing-partner/SKILL.md` (Task 11) — content parity is manual (Codex has no shared-skill mechanism to enforce it automatically), so any future edit to the rules must be applied to both files.

- [ ] **Step 1: Write the config snippet**

```toml
# codex/config.toml.example
#
# Copy this block into your Codex config (~/.codex/config.toml or your
# project's .codex/config.toml) to register the credit-box-rag MCP server.
# Replace /absolute/path/to/credit-box-rag with your actual checkout path.

[mcp_servers.credit-box-rag]
command = "python3"
args = ["/absolute/path/to/credit-box-rag/mcp_server.py"]
```

- [ ] **Step 2: Write the AGENTS.md snippet (mirrors `skills/loan-pricing-partner/SKILL.md`'s content, Codex's plain-markdown convention)**

```markdown
# codex/AGENTS.md.snippet
#
# Copy this section into your project's AGENTS.md to teach Codex how to
# use the credit-box-rag MCP tools. Keep this in sync with
# skills/loan-pricing-partner/SKILL.md if you edit either one.

## Loan Pricing Partner (credit-box-rag)

You have access to a mortgage lending knowledge system covering wholesale lenders
across 9 loan products (DSCR, fix-and-flip, new construction, multifamily, bridge,
blanket, commercial), via the `credit-box-rag` MCP server.

If any tool call errors with "Corpus DB not found", ask the user for the path to
their Master Credit Box Excel file, then call `ingest_excel(path)`. One-time step
per machine.

Tools: `find_lenders`, `get_lender_profile`, `compare_lenders`, `get_fico_ltv_tiers`,
`scenario_details`, `get_freshness`, `check_criteria`, `estimate_pricing`, `what_if`,
`ingest_excel`.

Rules:
1. Never fabricate lender data. Always cite sources returned by the tools.
2. Rate shopping without context → refuse. Ask for product, FICO, LTV, loan amount, property type.
3. "80 cents on the dollar" → ask: 80% of ARV or purchase price?
4. 3+ properties without "blanket" mentioned → ask: one blanket loan or individual loans per property?
5. "Light rehab" or "cosmetic" without scope → ask: what kind of work, and cost as % of ARV?
6. Never surface user_name/password fields — tool results flag these sensitive: true; omit them.
7. Warn if get_freshness() reports stale or critically_stale.
8. Present top 3 matches with a recommendation, not a full dump.
```

- [ ] **Step 3: Write the setup README**

```markdown
# Codex Setup

1. Copy `config.toml.example`'s `[mcp_servers.credit-box-rag]` block into
   your Codex config, with the correct absolute path to this repo.
2. Copy `AGENTS.md.snippet`'s content into your project's `AGENTS.md`.
3. Run `pip install openpyxl pydantic pyyaml mcp` in this directory.
4. Start Codex. The first time you ask it a lending question, if it reports
   "Corpus DB not found," give it the path to your Master Credit Box Excel
   file — it will call `ingest_excel` to build `corpus.db` locally.
```

- [ ] **Step 4: Validate the TOML parses**

Run: `python3 -c "import tomllib; tomllib.load(open('codex/config.toml.example', 'rb'))"`
Expected: no output (valid TOML). Note: the file has a `command = "python3"` / absolute-path placeholder that a real Codex config would need filled in — that placeholder is intentional (it's an `.example` file meant to be copied and edited), not a plan placeholder violation.

- [ ] **Step 5: Commit**

```bash
git add codex/
git commit -m "feat: add Codex adapter (config.toml + AGENTS.md snippets) on top of mcp_server.py"
```

---

### Task 13: Fresh-clone smoke test

**Files:**
- Create: `scripts/smoke_test.sh`

**Interfaces:**
- Consumes: `mcp_server.py`, `migrate.py`, `query.py` — this is the end-to-end "does this actually work on another machine" check the whole plan has been building toward.

- [ ] **Step 1: Write the smoke test script**

```bash
#!/usr/bin/env bash
# Fresh-clone smoke test: simulates a new machine installing this repo.
# Usage: ./scripts/smoke_test.sh /path/to/sample-credit-box.xlsx
set -euo pipefail

EXCEL_PATH="${1:?Usage: smoke_test.sh <path-to-excel>}"
TMPDIR=$(mktemp -d)
echo "Cloning into $TMPDIR ..."
git clone --quiet "$(git rev-parse --show-toplevel)" "$TMPDIR/credit-box-rag"
cd "$TMPDIR/credit-box-rag"

echo "Installing dependencies ..."
pip install --quiet openpyxl pydantic pyyaml mcp

echo "Building corpus.db from Excel (simulates ingest_excel) ..."
python3 migrate.py --excel "$EXCEL_PATH"

echo "Running a known query ..."
OUTPUT=$(python3 query.py "640 FICO Baltimore fix and flip")
echo "$OUTPUT" | grep -q "Recommendations" || {
  echo "FAIL: no recommendations in query output"
  exit 1
}

echo "Running regression suite ..."
python3 test_runner.py

echo "Verifying mcp_server.py imports and registers tools ..."
python3 -c "
import mcp_server
tool_names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
assert 'find_lenders' in tool_names, tool_names
print('MCP server OK:', sorted(tool_names))
"

echo "PASS: smoke test succeeded in $TMPDIR"
rm -rf "$TMPDIR"
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh ~/Downloads/"Copy of THE Master Credit Box-IPLE 2026 (1).xlsx"
```
Expected: `PASS: smoke test succeeded in /tmp/...`

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test.sh
git commit -m "test: add fresh-clone smoke test simulating install on a new machine"
```

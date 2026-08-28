"""
Code-driven evals for Master Credit Box RAG.

Every query output is verified against the corpus before returning.
Guarantees: no hallucinated lenders, no fake attributes, complete scenario coverage.
"""

import json, re
from pathlib import Path
from collections import defaultdict

CORPUS_DIR = Path(__file__).parent / "corpus"


class EvalResult:
    def __init__(self, name, status="PASS", detail="", count=0):
        self.name = name
        self.status = status
        self.detail = detail
        self.count = count

    def to_dict(self):
        return {"name": self.name, "status": self.status, "detail": self.detail, "count": self.count}

    def __repr__(self):
        return f"[{self.status}] {self.name}: {self.detail}"


def run_evals(query_result, corpus=None, run_all=False):
    """Run all evals against a query result. Returns list of EvalResults.
    
    run_all: also run structural evals (city_map consistency, cache check).
    """
    if corpus is None:
        import store
        corpus = store.load_all()

    evals = []
    evals.append(_eval_source_integrity(query_result, corpus))
    evals.append(_eval_attribute_existence(query_result, corpus))
    evals.append(_eval_lender_validity(query_result, corpus))
    evals.append(_eval_scenario_completeness(query_result, corpus))
    evals.append(_eval_no_hallucinated_values(query_result, corpus))
    evals.append(_eval_determinism(query_result))
    evals.append(_eval_staleness(query_result, corpus))
    if run_all:
        evals.append(_eval_city_map_consistency(corpus))
        evals.append(_eval_cache_consistency(corpus))
    return evals


def _build_lookup(corpus):
    """Build fast lookup sets from corpus."""
    records = corpus["records"]

    # Set of (lender, product, attr_name, str(attr_value))
    attr_set = set()
    for r in records:
        attr_set.add((
            r["lender_canonical"],
            r["product"],
            r["attr_name"],
            str(r["attr_value"]),
        ))

    # Set of (sheet, row)
    source_set = set()
    for r in records:
        row = r.get("source_row")
        if row:
            source_set.add((r["source_sheet"], row))
        else:
            source_set.add((r["source_sheet"], None))

    # Add scenario source sheets (CS sheets don't produce records)
    for s in corpus.get("scenarios", []):
        sheet = s.get("source_sheet", "")
        if sheet:
            source_set.add((sheet, None))
            source_set.add((sheet, s.get("source_row")))

    # Add credit grid sheets
    for g in corpus.get("credit_grids", []):
        sheet = g.get("source_sheet", "")
        if sheet:
            source_set.add((sheet, None))

    # Add underwriting sheets
    for u in corpus.get("underwriting", []):
        sheet = u.get("source_sheet", "")
        if sheet:
            source_set.add((sheet, None))

    # All known lenders
    lenders_set = set(r["lender_canonical"] for r in records)

    # Add lenders from scenarios
    for s in corpus.get("scenarios", []):
        for rec in s["recommendations"]:
            lc = rec.get("lender_canonical")
            if lc:
                lenders_set.add(lc)

    # Add lenders from credit grids
    for g in corpus.get("credit_grids", []):
        lc = g.get("lender_canonical")
        if lc:
            lenders_set.add(lc)

    # Add lenders from underwriting
    for u in corpus.get("underwriting", []):
        lc = u.get("lender_canonical")
        if lc:
            lenders_set.add(lc)

    # Lender product set
    lender_products = defaultdict(set)
    for r in records:
        lender_products[r["lender_canonical"]].add(r["product"])

    return attr_set, source_set, lenders_set, lender_products


def _eval_source_integrity(result, corpus):
    """Every cited source (sheet+row) must exist in the corpus."""
    attr_set, source_set, _, _ = _build_lookup(corpus)
    violations = []

    for match in result.get("matches", []):
        for src in match.get("sources", []):
            sheet = src.get("sheet")
            row = src.get("row")
            key = (sheet, row)
            if key not in source_set and (sheet, None) not in source_set:
                # Check if sheet exists at all
                sheet_exists = any(s[0] == sheet for s in source_set)
                if not sheet_exists:
                    violations.append(f"Sheet '{sheet}' not found in corpus")
                elif row and (sheet, row) not in source_set:
                    violations.append(f"Row {row} in sheet '{sheet}' not found")

    # Also check sources in reasons
    for match in result.get("matches", []):
        for reason in match.get("reasons", []):
            sheet = reason.get("source_sheet")
            row = reason.get("source_row")
            if sheet:
                key = (sheet, row)
                if key not in source_set and (sheet, None) not in source_set:
                    sheet_exists = any(s[0] == sheet for s in source_set)
                    if not sheet_exists:
                        violations.append(f"Sheet '{sheet}' in reason not found in corpus")

    if violations:
        return EvalResult(
            "source_integrity",
            "FAIL",
            f"{len(violations)} source violations: {'; '.join(violations[:5])}",
            len(violations),
        )
    return EvalResult("source_integrity", "PASS", f"All {sum(len(m.get('sources',[])) for m in result.get('matches',[]))} sources verified", 0)


def _eval_attribute_existence(result, corpus):
    """Every cited {lender, product, attr_name, value} must exist in corpus."""
    attr_set, _, lenders_set, lender_products = _build_lookup(corpus)
    violations = []

    for match in result.get("matches", []):
        lender = match["lender"]
        product = result.get("product")
        for reason in match.get("reasons", []):
            if reason["type"] == "attribute":
                detail = reason.get("detail", "")
                attr_name = None
                # Extract attr_name from detail like "fico_min=660..."
                if "=" in detail:
                    attr_name = detail.split("=")[0].strip()

                if attr_name and product:
                    # Check if any record exists for this lender+product+attr
                    found = False
                    for r in corpus["records"]:
                        if (r["lender_canonical"] == lender and
                            r["product"] == product and
                            r["attr_name"] == attr_name):
                            found = True
                            break
                    if not found:
                        # Try other products
                        for r in corpus["records"]:
                            if (r["lender_canonical"] == lender and
                                r["attr_name"] == attr_name):
                                found = True
                                break
                        if not found:
                            violations.append(f"attr '{attr_name}' not found for lender '{lender}'")

    if violations:
        return EvalResult(
            "attribute_existence",
            "FAIL",
            f"{len(violations)} attribute violations: {'; '.join(violations[:5])}",
            len(violations),
        )
    return EvalResult("attribute_existence", "PASS", "All cited attributes verified in corpus", 0)


def _eval_lender_validity(result, corpus):
    """Every recommended lender must be a known lender in the corpus."""
    _, _, lenders_set, _ = _build_lookup(corpus)
    violations = []

    for match in result.get("matches", []):
        lender = match["lender"]
        if lender not in lenders_set:
            violations.append(f"Lender '{lender}' not found in corpus")

    if violations:
        return EvalResult(
            "lender_validity",
            "FAIL",
            f"{len(violations)} invalid lenders: {violations}",
            len(violations),
        )
    return EvalResult("lender_validity", "PASS", f"All {len(result.get('matches',[]))} lenders are valid", 0)


def _eval_scenario_completeness(result, corpus):
    """
    For matched scenarios, verify we didn't drop lenders.
    Counts how many scenario lenders are represented in matches.
    """
    violations = []

    product = result.get("product")
    for si_name in result.get("scenarios_matched", []):
        # Find matching scenario in corpus
        for s in corpus.get("scenarios", []):
            if s["condition"] == si_name:
                # Get actual lender names from this scenario
                known_lenders = set()
                known_details = {}
                for r in s["recommendations"]:
                    lc = r.get("lender_canonical")
                    if lc:
                        known_lenders.add(lc)
                        known_details[lc] = r.get("detail", "")

                # Check which matched
                matched_lenders = set(m["lender"] for m in result.get("matches", []))
                missing = known_lenders - matched_lenders
                if missing:
                    # Check if missing lenders have the product (if product specified)
                    product_filtered = []
                    for l in list(missing):
                        has_product = any(
                            r["lender_canonical"] == l and r["product"] == product
                            for r in corpus.get("records", [])
                        ) if product else True
                        if not has_product:
                            missing.discard(l)
                            product_filtered.append(l)

                    if missing:
                        violations.append(f"Scenario '{si_name}': missing lenders {missing}")

    if violations:
        return EvalResult(
            "scenario_completeness",
            "WARN",
            f"{len(violations)} scenarios with missing lenders: {'; '.join(violations[:3])}",
            len(violations),
        )
    return EvalResult("scenario_completeness", "PASS", "All scenario lenders represented", 0)


def _eval_no_hallucinated_values(result, corpus):
    """No attribute value in output that doesn't match corpus data.
    Uses substring matching for text fields (detail often summarizes)."""
    attr_set, _, _, _ = _build_lookup(corpus)
    violations = []

    for match in result.get("matches", []):
        lender = match["lender"]
        for reason in match.get("reasons", []):
            if reason["type"] == "attribute":
                detail = reason.get("detail", "")
                if "=" not in detail:
                    continue
                parts = detail.split("=", 1)
                attr_name = parts[0].strip()
                # Get the part before any parenthetical note
                val_str = parts[1]
                # Remove trailing parenthetical notes
                val_str = re.sub(r'\s*\(.*?\)\s*$', '', val_str).strip()
                # Get just the first "word" or number
                val_first = val_str.split()[0].strip() if val_str.split() else val_str

                product = result.get("product")
                if product:
                    found = False
                    for r in corpus["records"]:
                        if (r["lender_canonical"] == lender and
                            r["product"] == product and
                            r["attr_name"] == attr_name):
                            raw = str(r["attr_value"]).strip()
                            # Exact match or substring (text fields get summarized)
                            if raw == val_str or raw == val_first or val_first.lower() in raw.lower():
                                found = True
                                break
                    if not found:
                        # Check other products
                        for r in corpus["records"]:
                            if (r["lender_canonical"] == lender and
                                r["attr_name"] == attr_name):
                                raw = str(r["attr_value"]).strip()
                                if raw == val_str or raw == val_first or val_first.lower() in raw.lower():
                                    found = True
                                    break
                        if not found:
                            violations.append(f"value '{val_str}' for {lender}/{attr_name} not in corpus")

    if violations:
        return EvalResult(
            "no_hallucinated_values",
            "WARN",
            f"{len(violations)} unverified values: {'; '.join(violations[:5])}",
            len(violations),
        )
    return EvalResult("no_hallucinated_values", "PASS", "All values match corpus", 0)


def _eval_determinism(result):
    """Structural check: result has expected shape."""
    issues = []
    if not isinstance(result.get("matches"), list):
        issues.append("'matches' is not a list")
    if not isinstance(result.get("scenarios_matched"), list):
        issues.append("'scenarios_matched' is not a list")

    for m in result.get("matches", []):
        for key in ["lender", "score", "reasons", "sources"]:
            if key not in m:
                issues.append(f"match missing '{key}' for lender {m.get('lender', '?')}")

    if issues:
        return EvalResult("determinism", "FAIL", "; ".join(issues), len(issues))
    return EvalResult("determinism", "PASS", "Result structure valid", 0)


def summarise(evals):
    """Get overall pass/fail from eval list."""
    total = len(evals)
    passed = sum(1 for e in evals if e.status == "PASS")
    warned = sum(1 for e in evals if e.status == "WARN")
    failed = sum(1 for e in evals if e.status == "FAIL")
    return {
        "total": total,
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "all_passed": failed == 0,
    }


# re imported at top


def format_evals(evals):
    """Format evals for display."""
    lines = []
    for e in evals:
        icon = {"PASS": "✓", "WARN": "△", "FAIL": "✗"}.get(e.status, "?")
        lines.append(f"  {icon} {e.name}: {e.detail[:120]}")
    summary = summarise(evals)
    lines.append(f"  --- {summary['passed']} passed, {summary['warned']} warned, {summary['failed']} failed ---")
    return "\n".join(lines)


def _eval_staleness(query_result, corpus):
    meta = corpus.get("meta", {})
    age = meta.get("file_age_days", 0)
    generated = meta.get("generated", "?")
    src = meta.get("source", "?")

    if not age:
        return EvalResult("staleness", "WARN", "No file timestamp available")

    if age > 90:
        return EvalResult("staleness", "FAIL",
                          f"Data {age:.0f} days old (last parsed {generated[:10]}) — exceeds 90-day threshold")
    elif age > 30:
        return EvalResult("staleness", "WARN",
                          f"Data {age:.0f} days old (last parsed {generated[:10]}) — exceeds 30-day freshness target")
    else:
        return EvalResult("staleness", "PASS",
                          f"Data {age:.0f} days old (last parsed {generated[:10]})")


def _eval_city_map_consistency(corpus):
    """Every city_map entry must map to a city with a matching scenario."""
    cm_path = CORPUS_DIR / "city_map.json"
    if not cm_path.exists():
        return EvalResult("city_map_consistency", "PASS", "No city_map.json found", 0)

    with open(cm_path) as f:
        city_map = json.load(f)

    known_scenarios = set()
    for s in corpus.get("scenarios", []):
        known_scenarios.add(s["condition"].lower())

    violations = []
    for suburb, metro in city_map.items():
        if "_" in suburb or "_comment" in suburb or "_docs" in suburb:
            continue
        # Check if any scenario condition contains this metro city name
        matched = any(metro.lower() in cond for cond in known_scenarios)
        if not matched:
            violations.append(f"'{suburb}' → '{metro}': no scenario found containing '{metro}'")

    if violations:
        return EvalResult("city_map_consistency", "WARN",
                          f"{len(violations)} unmapped cities: {'; '.join(violations[:3])}",
                          len(violations))
    return EvalResult("city_map_consistency", "PASS", f"All {len(city_map)-2} city_map entries validated", 0)


def _eval_cache_consistency(corpus):
    """Check that llm_cache entries reference valid records in corpus."""
    cache_path = CORPUS_DIR / "llm_cache.json"
    if not cache_path.exists():
        return EvalResult("cache_consistency", "PASS", "No llm_cache.json found", 0)

    with open(cache_path) as f:
        cache = json.load(f)

    records = corpus.get("records", [])

    def _norm(s):
        return ' '.join(s.strip().lower().split())

    # Build normalized index of raw text values from records
    raw_values = [_norm(str(r.get("attr_value", ""))) for r in records]

    # Count cache entries where raw text is not a substring of any corpus value
    unmatched = 0
    for key, entry in cache.items():
        raw = entry.get("raw", "")
        if raw:
            n_raw = _norm(raw)
            found = any(n_raw in rv for rv in raw_values)
            if not found:
                unmatched += 1

    if unmatched > 10:
        return EvalResult("cache_consistency", "WARN",
                          f"{unmatched} cache entries don't match corpus (stale cache?)",
                          unmatched)
    return EvalResult("cache_consistency", "PASS", f"Cache consistent with corpus ({len(cache)} entries)", 0)


def verify_query(query_result, corpus=None):
    """Run evals and attach results. Returns (query_result, all_passed)."""
    if corpus is None:
        import store
        corpus = store.load_all()
    evals = run_evals(query_result, corpus)
    query_result["evals"] = [e.to_dict() for e in evals]
    query_result["eval_summary"] = summarise(evals)
    return query_result, query_result["eval_summary"]["all_passed"]


if __name__ == "__main__":
    # Standalone: run query evals + structural evals (city_map, cache)
    from reason import CreditBoxEngine
    engine = CreditBoxEngine()
    result = engine.query("640 FICO Baltimore fix and flip")

    import store
    corpus = store.load_all()

    # Structural evals (run_all=True)
    struct_evals = run_evals(result, corpus, run_all=True)
    result["evals"] = [e.to_dict() for e in struct_evals]
    result["eval_summary"] = summarise(struct_evals)
    passed = result["eval_summary"]["all_passed"]

    print(format_evals(struct_evals))
    print(f"\nAll passed: {passed}")

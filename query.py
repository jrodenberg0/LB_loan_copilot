"""
Query Master Credit Box corpus with evals-driven verification.

Usage:
  credit-box "640 FICO, $90k Baltimore, 1 prior flip — who?"
  credit-box --list-scenarios
  credit-box --list-lenders
  credit-box --show-lender "Kiavi"
  credit-box --compare "Kiavi" "CV3" --product fix_and_flip

Conversation (stateful):
  credit-box "640 FICO Baltimore"  # initial query
  credit-box !show 1                # show detail for first result
  credit-box !not Conventus         # re-query excluding Conventus
  credit-box !filter "ltv > 75"    # filter results
  credit-box !compare 1 3          # compare first and third results
  credit-box !history               # show recent queries
  credit-box "what about higher LTV"  # refinement (appended to last)
"""

import json, sys, os
from pathlib import Path
from collections import defaultdict

from llm_parse import parse_fico_ltv_tiers
from state import push_query, refine_query, list_history, load_state, clear_state

CORPUS_DIR = Path(__file__).parent / "corpus"


import store


def load_scenarios():
    return {"scenarios": store.get_scenarios()}


def fmt_source(ss, sr):
    s = f"[{ss}]"
    if sr:
        s += f" row {sr}"
    return s


def cmd_query(args):
    query = " ".join(args)
    if not query:
        print("Usage: credit-box <question>")
        return

    from reason import CreditBoxEngine
    from evals import verify_query, EvalResult

    engine = CreditBoxEngine()
    result = engine.query(query)

    # Save state for conversation
    push_query(query, result)

    result, passed = verify_query(result)

    # --- Output ---
    print(f"\n{'='*70}")
    print(f"  Query: {query}")
    print(f"{'='*70}")

    # Criteria detected
    c = result["criteria"]
    parts = []
    if c.get("fico"): parts.append(f"FICO ≥{c['fico']}")
    if c.get("city"): parts.append(f"City: {c['city']}")
    if c.get("state"): parts.append(f"State: {c['state']}")
    if c.get("loan_amount"): parts.append(f"Loan: ${c['loan_amount']:,}")
    if c.get("experience"): parts.append(f"Exp: {c['experience']}+ flips")
    if result.get("product"): parts.append(f"Product: {result['product']}")
    if parts:
        print(f"  Parsed: {' | '.join(parts)}")

    # Scenarios matched
    sm = result.get("scenarios_matched", [])
    if sm:
        print(f"  Scenario match: {', '.join(sm[:3])}")
    print()

    # Lender recommendations
    matches = result.get("matches", [])
    if not matches:
        print("  No lenders matched.")
        print("\n  Next: try !filter <terms> to narrow, or ask a different question.")
        return

    print(f"  Recommendations ({len(matches)} lenders):\n")
    for i, m in enumerate(matches[:10], 1):
        print(f"  {i}. {m['lender']}  (score: {m['score']:.2f})")
        for r in m.get("reasons", []):
            src = ""
            sheet = r.get("source_sheet") or r.get("sheet", "")
            row = r.get("source_row")
            if sheet:
                src = "  " + fmt_source(sheet, row)
            detail = r.get("detail", "") or r.get("scenario", "")
            if r["type"] == "scenario":
                detail = f"Scenario: {r.get('scenario', detail)}"
            print(f"     - {detail}{src}")
        if m.get("sources"):
            pass
        print()

    # Full scenario details
    if sm:
        print(f"  Scenario details:\n")
        scenarios = store.get_scenarios()
        for si_name in sm:
            for s in scenarios:
                if s["condition"] == si_name:
                    print(f"  [{s['source_sheet']}] {s['condition']}")
                    for rec in s["recommendations"][:5]:
                        detail = rec.get("detail", "")
                        if detail and len(detail) > 400:
                            detail = detail[:400] + "..."
                        print(f"    → {rec['lender_canonical']:30s} {detail}")
                    if len(s["recommendations"]) > 5:
                        print(f"    ... and {len(s['recommendations'])-5} more")
                    print()

    # Evals report
    print(f"  Verification:")
    for e in result.get("evals", []):
        icon = {"PASS": "✓", "WARN": "△", "FAIL": "✗"}.get(e["status"], "?")
        print(f"    {icon} {e['name']}: {e['detail'][:100]}")
    es = result.get("eval_summary", {})
    print(f"    --- {es.get('passed',0)} passed, {es.get('warned',0)} warned, {es.get('failed',0)} failed ---")

    if not passed:
        print(f"\n  WARNING: Some evals failed — output may contain errors.")

    # Conversation hints
    state = load_state()
    if len(state.get("history", [])) > 1:
        print("\n  Next: !show <n> | !not <lender> | !compare <n> <m> | !filter <terms> | !history")


def cmd_list_scenarios():
    data = load_scenarios()
    print("Scenarios (decision rules):\n")
    for s in data["scenarios"]:
        lenders = ", ".join(r.get("lender_canonical", r["lender"]) for r in s["recommendations"][:5])
        print(f"  [{s.get('source_sheet','?')}] {s['condition']}")
        print(f"    → {lenders}{'...' if len(s['recommendations']) > 5 else ''}")
        print()


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


def cmd_list_lenders():
    lenders = store.get_lenders_index()
    print("Lenders:\n")
    for name, info in sorted(lenders.items()):
        aliases = f" (aka {', '.join(info['aliases'])})" if info["aliases"] else ""
        prods = ", ".join(info["products"])
        if prods:
            print(f"  {name:30s}{aliases:20s} [{prods}]")


def cmd_show_tiers(args):
    """Show FICO/LTV tier tables for one or more lenders."""
    if not args:
        print("Usage: --show-tiers <lender> [--product <prod>]")
        return

    product = None
    if "--product" in args:
        idx = args.index("--product")
        product = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    name = " ".join(args)
    cache = json.loads((CORPUS_DIR / "llm_cache.json").read_text())

    tier_attrs = ["fico_requirement_at_max_ltv", "fico_qualification", "dscr_range",
                   "max__ltv_purchase", "max__ltv_cash_out_refi"]

    print(f"\n{'='*60}")
    print(f"  FICO/LTV Tiers: {name}" + (f" [{product}]" if product else ""))
    print(f"{'='*60}")

    records = store.get_lender_records(name)
    attrs_found = defaultdict(list)
    for r in records:
        if r["attr_name"] in tier_attrs and (not product or r["product"] == product or not product):
            attrs_found[r["attr_name"]].append(r)

    if not attrs_found:
        print("  No tier data found.")
        return

    for attr_name in tier_attrs:
        if attr_name not in attrs_found:
            continue
        print(f"\n  [{attr_name}]")
        for r in attrs_found[attr_name]:
            raw = str(r["attr_value"]).strip()
            ck = f"fico_ltv::{raw}"
            parsed = cache.get(ck, {})
            tiers = parsed.get("tiers", [])
            note_type = parsed.get("note_type", "")
            notes = parsed.get("notes", "")

            if tiers:
                print(f"    Product: {r['product']}")
                print(f"    Type: {note_type}")
                print(f"    Source: [{r['source_sheet']} row {r['source_row']}]")
                for t in tiers:
                    parts = []
                    if "min_fico" in t: parts.append(f"FICO ≥{t['min_fico']}")
                    if "max_fico" in t: parts.append(f"FICO ≤{t['max_fico']}")
                    if "max_ltv" in t: parts.append(f"LTV ≤{t['max_ltv']}%")
                    if "min_dscr" in t: parts.append(f"DSCR ≥{t['min_dscr']}")
                    if "max_dscr" in t: parts.append(f"DSCR ≤{t['max_dscr']}")
                    if "max_ltc" in t: parts.append(f"LTC ≤{t['max_ltc']}%")
                    if "loan_type" in t: parts.append(f"Type: {t['loan_type']}")
                    if "occupancy" in t: parts.append(f"Occupancy: {t['occupancy']}")
                    if "condition" in t: parts.append(f"Condition: {t['condition']}")
                    if "note" in t: parts.append(f"Note: {t['note']}")
                    print(f"      {' | '.join(parts)}")
            else:
                print(f"    Product: {r['product']}  Raw: {raw[:80]}")
            if notes:
                print(f"    Notes: {notes}")
            print()


def cmd_show_lender(args):
    if not args:
        print("Usage: --show-lender <name>")
        return
    name = " ".join(args)
    records = store.get_lender_records(name)

    if not records:
        print(f"No data for '{name}'. Try --list-lenders")
        return

    print(f"\n{'='*60}")
    print(f"  {records[0]['lender_canonical']}")
    print(f"{'='*60}")

    by_prod = defaultdict(list)
    for r in records:
        by_prod[r["product"]].append(r)

    for prod, attrs in sorted(by_prod.items()):
        print(f"\n  [{prod}]")
        for a in attrs:
            flag = " [SENSITIVE]" if a.get("sensitive") else ""
            print(f"    {a['attr_name']}: {a['attr_value']}{flag}")


def cmd_compare(args):
    if len(args) < 2:
        print("Usage: --compare <lender1> <lender2> [--product <prod>]")
        return

    product = None
    if "--product" in args:
        idx = args.index("--product")
        product = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    l1, l2 = args[0], args[1]
    r1 = store.get_lender_records(l1, product)
    r2 = store.get_lender_records(l2, product)

    if not r1 and not r2:
        print("No data found for either lender.")
        return

    print(f"\n{'='*70}")
    print(f"  {l1} vs {l2}" + (f" [{product}]" if product else ""))
    print(f"{'='*70}")

    a1 = {}
    for r in r1:
        key = r["attr_name"]
        if key not in a1:
            a1[key] = (r["attr_value"], r["source_sheet"], r["source_row"])
    a2 = {}
    for r in r2:
        key = r["attr_name"]
        if key not in a2:
            a2[key] = (r["attr_value"], r["source_sheet"], r["source_row"])

    all_attrs = sorted(set(list(a1.keys()) + list(a2.keys())))

    diffs = 0
    for attr in all_attrs:
        v1, s1_sheet, s1_row = a1.get(attr, ("—", "", ""))
        v2, s2_sheet, s2_row = a2.get(attr, ("—", "", ""))
        if str(v1) != str(v2):
            diffs += 1
            s1 = f"[{s1_sheet} row {s1_row}]" if s1_sheet else ""
            s2 = f"[{s2_sheet} row {s2_row}]" if s2_sheet else ""
            print(f"  {attr:35s}  {l1[:15]:15s} {str(v1)[:50]:50s} {s1}")
            print(f"  {'':35s}  {l2[:15]:15s} {str(v2)[:50]:50s} {s2}")
            print()
    if diffs == 0:
        print("  No differences found.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    args = sys.argv[1:]

    # Conversation commands
    if args[0].startswith("!") or args[0] in ("not", "show", "compare", "filter", "what"):
        state = load_state()
        if not state.get("last_query"):
            print("No prior query context. Start with a full query first.")
            return

        raw_prompt = " ".join(args)

        if raw_prompt.startswith("!history"):
            print(list_history())
            return
        if raw_prompt.startswith("!clear"):
            clear_state()
            print("State cleared.")
            return
        if raw_prompt.startswith("!show ") or raw_prompt.startswith("show "):
            # Resolve lender name and display
            rest = raw_prompt.split(" ", 1)[1]
            try:
                idx = int(rest.split()[0])
                matches = state.get("last_result", {}).get("matches", [])
                if 1 <= idx <= len(matches):
                    lender = matches[idx - 1]["lender"]
                    cmd_show_lender([lender])
                    return
            except ValueError:
                pass

        # Resolve to new query
        new_query = refine_query(raw_prompt)
        if new_query.startswith("--"):
            # Route to appropriate cmd
            parts = new_query.split()
            if "--show-lender" in parts:
                idx = parts.index("--show-lender")
                cmd_show_lender(parts[idx+1:])
            elif "--compare" in parts:
                idx = parts.index("--compare")
                cmd_compare(parts[idx+1:])
            return

        print(f"Refined query: {new_query}")
        cmd_query(new_query.split())
        return

    if args[0] == "--list-scenarios":
        cmd_list_scenarios()
    elif args[0] == "--list-lenders":
        cmd_list_lenders()
    elif args[0] == "--show-lender":
        cmd_show_lender(args[1:])
    elif args[0] == "--show-tiers":
        cmd_show_tiers(args[1:])
    elif args[0] == "--compare":
        cmd_compare(args[1:])
    elif args[0] == "--freshness":
        cmd_freshness()
    elif args[0] == "--clear":
        clear_state()
        print("State cleared.")
    elif args[0] == "--history":
        print(list_history())
    elif args[0].startswith("--"):
        print(f"Unknown flag: {args[0]}")
    else:
        cmd_query(args)


if __name__ == "__main__":
    main()

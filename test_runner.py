"""
Regression test runner for Master Credit Box engine.

Reads tests.json, runs each through the engine + evals, reports results.

Usage:
  python test_runner.py                       # run all tests
  python test_runner.py --verbose              # full per-test output
  python test_runner.py --id baltimore-fnf-640 # single test
"""

import json, sys
from pathlib import Path

ROOT = Path(__file__).parent
TESTS_PATH = ROOT / "tests.json"


def load_tests():
    with open(TESTS_PATH) as f:
        return json.load(f)["tests"]


def find_test(tid):
    tests = load_tests()
    for t in tests:
        if t["id"] == tid:
            return t
    return None


def run_test(test, verbose=False):
    from reason import CreditBoxEngine
    from evals import verify_query

    engine = CreditBoxEngine()
    result = engine.query(test["query"])
    result, all_evals_passed = verify_query(result)

    checks = {"pass": True, "failures": []}

    # Check evals
    if test.get("evals_must_pass", False):
        if not all_evals_passed:
            failed_evals = [e for e in result.get("evals", []) if e["status"] != "PASS"]
            checks["failures"].append(
                f"evals failed: {', '.join(e['name'] for e in failed_evals)}"
            )

    # Check expected lenders
    expected = test.get("expect_lenders", [])
    matched_names = set(m["lender"] for m in result.get("matches", []))
    for lender in expected:
        # Try exact match first, then canonical
        if lender not in matched_names:
            resolved = engine.resolve_name(lender)
            if resolved not in matched_names:
                checks["failures"].append(f"expected lender '{lender}' not in results")
            else:
                matched_names.add(resolved)

    # Check excluded lenders (should NOT appear)
    excluded = test.get("exclude_lenders", [])
    for lender in excluded:
        for m in result.get("matches", []):
            if m["lender"].lower() == lender.lower():
                checks["failures"].append(f"excluded lender '{lender}' appeared in results")

    # Check expected scenarios
    expected_s = test.get("expect_scenarios", [])
    matched_s = set(result.get("scenarios_matched", []))
    for s in expected_s:
        # Fuzzy match
        found = False
        for ms in matched_s:
            if s.lower() in ms.lower() or ms.lower() in s.lower():
                found = True
                break
        if not found:
            checks["failures"].append(f"expected scenario '{s}' not matched")

    checks["pass"] = len(checks["failures"]) == 0

    return {
        "id": test["id"],
        "query": test["query"],
        "pass": checks["pass"],
        "failures": checks["failures"],
        "matched_lenders": [m["lender"] for m in result.get("matches", [])[:10]],
        "matched_scenarios": result.get("scenarios_matched", []),
        "eval_summary": result.get("eval_summary", {}),
    }


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    single_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--id" and i + 1 < len(sys.argv):
            single_id = sys.argv[i + 1]

    if single_id:
        tests = [find_test(single_id)] if find_test(single_id) else []
        if not tests:
            print(f"Test '{single_id}' not found")
            return
    else:
        tests = load_tests()

    results = []
    passed = 0
    failed = 0

    print(f"\nRunning {len(tests)} tests...\n")

    for t in tests:
        r = run_test(t, verbose)
        results.append(r)
        icon = "✓" if r["pass"] else "✗"
        print(f"  {icon} {r['id']:40s}  {'PASS' if r['pass'] else 'FAIL'}")
        if not r["pass"]:
            failed += 1
            for f in r["failures"]:
                print(f"       {f}")
        else:
            passed += 1

        if verbose:
            print(f"       Lenders: {r['matched_lenders'][:5]}")
            print(f"       Scenarios: {r['matched_scenarios'][:3]}")
            print()

    print(f"\n{'='*50}")
    print(f"  {passed}/{len(tests)} passed, {failed}/{len(tests)} failed")
    print(f"{'='*50}")

    return failed == 0


# Monkey-patch: add resolve_name to engine if missing
from reason import CreditBoxEngine
if not hasattr(CreditBoxEngine, "resolve_name"):
    def resolve_name(self, name):
        for l in self.lenders:
            if l.lower() == name.lower():
                return l
        return name
    CreditBoxEngine.resolve_name = resolve_name


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

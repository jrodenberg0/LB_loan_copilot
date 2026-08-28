"""
Agent tools for loan-pricing partner.

Wraps the deterministic engine + LLM cache into tool calls an LLM agent
can use to reason about deals, compare lenders, estimate pricing, and
explain trade-offs.

Usage:
  from agent_tools import CreditBoxAgent
  agent = CreditBoxAgent()
  agent.find_lenders("640 FICO Baltimore")
  agent.estimate_pricing("Kiavi", "fix_and_flip", ltv=75, fico=680)
"""

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

    # --- Tool 1: Find lenders ---

    def find_lenders(self, query: str, max_loan: int = None) -> dict:
        """Route a deal query. Returns ranked lenders with scores + reasoning.
        
        max_loan: filter out lenders with known loan_max below this amount.
                 Lenders without loan_max data are kept (unknown capacity).
        """
        if max_loan:
            query = f"{query} ${max_loan} loan"
        result = self.engine.query(query)
        return {
            "query": query,
            "criteria": result["criteria"],
            "product": result["product"],
            "scenarios_matched": result.get("scenarios_matched", []),
            "matches": [
                {"lender": m["lender"], "score": m["score"],
                 "reasons": [r.get("detail", "") for r in m.get("reasons", [])]}
                for m in result.get("matches", [])[:10]
            ],
            "total_candidates": result.get("total_candidates", 0),
        }

    # --- Tool 2: Lender profile ---

    def get_lender_profile(self, lender: str, product: str = None) -> dict:
        """All attributes for a lender, optionally by product."""
        records = store.get_lender_records(lender, product)
        if not records:
            return {"error": f"Lender '{lender}' not found"}
        by_prod = defaultdict(list)
        for r in records:
            by_prod[r["product"]].append(r)
        profile = {"lender": records[0]["lender_canonical"], "products": {}}
        for prod, attrs in by_prod.items():
            profile["products"][prod] = {
                r["attr_name"]: {
                    "value": r["attr_value"],
                    "sensitive": r.get("sensitive", False),
                    "source": f"[{r['source_sheet']} row {r['source_row']}]",
                }
                for r in attrs
            }
        return profile

    # --- Tool 3: Compare lenders ---

    def compare_lenders(self, lender1: str, lender2: str, product: str = None) -> dict:
        """Side-by-side attribute comparison."""
        p1 = self.get_lender_profile(lender1, product)
        p2 = self.get_lender_profile(lender2, product)
        if "error" in p1 or "error" in p2:
            return {"error": p1.get("error") or p2.get("error")}
        all_prods = set(p1["products"].keys()) | set(p2["products"].keys())
        diffs = []
        for prod in sorted(all_prods):
            a1 = p1["products"].get(prod, {})
            a2 = p2["products"].get(prod, {})
            all_attrs = set(a1.keys()) | set(a2.keys())
            for attr in sorted(all_attrs):
                v1 = a1.get(attr, {})
                v2 = a2.get(attr, {})
                if str(v1.get("value")) != str(v2.get("value")):
                    diffs.append({
                        "product": prod,
                        "attribute": attr,
                        f"{p1['lender']}_value": v1.get("value", "—"),
                        f"{p2['lender']}_value": v2.get("value", "—"),
                    })
        return {"lender1": p1["lender"], "lender2": p2["lender"],
                "product": product or "all", "differences": diffs[:50]}

    # --- Tool 4: FICO/LTV tiers ---

    def get_fico_ltv_tiers(self, lender: str, product: str = None) -> dict:
        """Structured FICO/LTV tier data for a lender."""
        all_records = store.get_lender_records(lender, product)
        records = [
            r for r in all_records
            if r["attr_name"] in ("fico_requirement_at_max_ltv", "fico_qualification",
                                    "dscr__prop_dti_min_max", "max__ltv_purchase", "max__ltv_cash_out_refi")
        ]
        tiers = {}
        for r in records:
            raw = str(r["attr_value"]).strip()
            ck = f"fico_ltv::{raw}"
            parsed = self.cache.get(ck, {})
            tiers[r["attr_name"]] = {
                "note_type": parsed.get("note_type", "unknown"),
                "tiers": parsed.get("tiers", []),
                "notes": parsed.get("notes", ""),
                "source": f"[{r['source_sheet']} row {r['source_row']}]",
                "product": r["product"],
            }
        return {"lender": lender, "product": product, "tiers": tiers}

    # --- Tool 5: Scenario details ---

    def scenario_details(self, scenario_text: str) -> dict:
        """Full recommendation text for a scenario."""
        for s in self.scenarios:
            if scenario_text.lower() in s["condition"].lower():
                return {
                    "scenario": s["condition"],
                    "product_type": s.get("product_type", ""),
                    "source_sheet": s.get("source_sheet", ""),
                    "recommendations": [
                        {"lender": r["lender_canonical"], "detail": r.get("detail", "")[:300]}
                        for r in s.get("recommendations", [])
                    ],
                }
        # Fuzzy match
        for s in self.scenarios:
            if any(w in s["condition"].lower() for w in scenario_text.lower().split()):
                return self.scenario_details(s["condition"])
        return {"error": f"Scenario '{scenario_text}' not found"}

    # --- Tool 6: Freshness ---

    def get_freshness(self) -> dict:
        return store.get_freshness()

    # --- Tool 7: Check criteria ---

    def check_criteria(self, lender: str, product: str, criteria: dict) -> dict:
        """Check if a lender meets specific criteria. Returns passes/fails per condition."""
        results = {"lender": lender, "product": product, "checks": [], "overall": True}

        state = criteria.get("state") or criteria.get("city", "")
        if state:
            st_parsed = self.engine.parsed_states.get((lender, product or ""))
            if not st_parsed:
                st_parsed = parse_state_coverage("Nationwide")  # fallback
            if st_parsed:
                includes, why = state_includes(st_parsed, state)
                results["checks"].append({
                    "criterion": f"state_coverage includes {state}",
                    "pass": includes is True,
                    "detail": why,
                })
                if includes is not True:
                    results["overall"] = False

        fico = criteria.get("fico")
        if fico:
            for attr in ("fico_requirement_at_max_ltv",):
                tp = self.engine.parsed_fico_tiers.get((lender, product or "", attr))
                if tp:
                    matched, why, _ = fico_matches(tp, fico)
                    results["checks"].append({
                        "criterion": f"FICO {fico} matches {attr} tiers",
                        "pass": matched is True,
                        "detail": why,
                    })
                    if matched is not True:
                        results["overall"] = False

        return results

    # --- Tool 8: Estimate pricing ---

    def estimate_pricing(self, lender: str, product: str, **params) -> dict:
        """Estimate rate/pricing for a lender given borrower params.

        Params: ltv (int), fico (int), loan_amount (int), experience (int)
        Returns applicable tier info + rate range.
        """
        profile = self.get_lender_profile(lender, product)
        if "error" in profile:
            return profile

        tiers = self.get_fico_ltv_tiers(lender, product)
        ltv = params.get("ltv")
        fico = params.get("fico")

        # Find applicable LTV tier
        applicable_tier = None
        if fico and "fico_requirement_at_max_ltv" in tiers.get("tiers", {}):
            matched, why, tier = fico_matches(tiers["tiers"]["fico_requirement_at_max_ltv"], fico)
            if tier:
                applicable_tier = tier

        # Get rate range from profile
        rate = None
        rate_fields = ["rate_range", "lowest_rate_at_max_ltv_arv",
                        "lowest_rate_at_max_ltc_arv", "lowest_rate_at_max_ltv",
                        "lowest_rate_**", "floor_rate"]
        for prod_name, attrs in profile.get("products", {}).items():
            if product and prod_name != product:
                continue
            for rf in rate_fields:
                val = attrs.get(rf, {}).get("value", "")
                if val:
                    rate = f"{rf}: {val}" if not rate else f"{rate}, {rf}: {val}"
            break

        result = {"lender": lender, "product": product,
                  "params": params,
                  "applicable_tier": applicable_tier,
                  "rate_range": rate or "not stated",
                  "notes": []}

        # Add tier-based notes
        if fico and "fico_requirement_at_max_ltv" in tiers.get("tiers", {}):
            note = tiers["tiers"]["fico_requirement_at_max_ltv"].get("notes", "")
            if note:
                result["notes"].append(f"FICO condition: {note}")
        if ltv:
            # Check if ltv falls within stated max
            for attr in ("max__ltv_purchase", "max__ltv_cash_out_refi"):
                if attr in tiers.get("tiers", {}):
                    t = tiers["tiers"][attr]
                    for tier in t.get("tiers", []):
                        max_l = tier.get("max_ltv") or tier.get("max_ltc", 0)
                        if max_l and int(max_l) >= ltv:
                            result["notes"].append(f"{attr}: LTV {ltv}% ≤ {max_l}% tier")

        return result

    # --- Tool 9: What-if ---

    def what_if(self, params: dict) -> dict:
        """Re-route with modified parameters. Returns before/after comparison."""
        query_template = params.pop("query", "")
        changes = params
        # Rebuild query with new params
        parts = [query_template]
        for k, v in changes.items():
            parts.append(f"{k}={v}")
        new_query = " ".join(parts)
        return self.find_lenders(new_query)

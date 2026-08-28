"""
Decision engine for Master Credit Box.

Uses structured corpus + LLM-as-judge parsed data for state coverage
and FICO/LTV condition matching. Every output cites sources.
"""

import json, re, sys
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

from llm_parse import parse_state_coverage, parse_fico_ltv_tiers, state_includes, fico_matches
import store

CORPUS_DIR = Path(__file__).parent / "corpus"


def _extract_experience_min(raw: str):
    """Extract numeric minimum experience from freeform text.
    Returns float or None.
    """
    if not raw:
        return None
    s = raw.strip().lower()
    # "None" / "No experience required" / "N/A" → 0
    if s in ("none", "n/a", "na", "", "all", "none required", "no experience required"):
        return 0.0
    # Simple float/int
    try:
        return float(s)
    except ValueError:
        pass
    # "3+" → 3, "5+" → 5
    m = re.search(r'^(\d+)\s*\+', s)
    if m:
        return float(m.group(1))
    # "0-2" → 0, "3-10" → 3
    m = re.search(r'^(\d+)\s*-', s)
    if m:
        return float(m.group(1))
    # "2 in 36" / "3 in last 36" → 2
    m = re.search(r'(\d+)\s+in\s+last?\s+\d+', s)
    if m:
        return float(m.group(1))
    # "5 in 36" → 5
    m = re.search(r'(\d+)\s+in\s+\d+', s)
    if m:
        return float(m.group(1))
    # "min 3" / "minimum 5" → 3
    m = re.search(r'(?:min|minimum)\s*[.:]?\s*(\d+)', s)
    if m:
        return float(m.group(1))
    # "# ever" pattern: "10+ Ever" → 10
    m = re.search(r'(\d+)\s*\+\s*ever', s)
    if m:
        return float(m.group(1))
    return None


class CreditBoxEngine:
    def __init__(self, data=None):
        if data is not None:
            self.data = data
        else:
            self.data = store.load_all()
        self._build_index()

    def _build_index(self):
        records = self.data["records"]

        # Lender canonical name set
        self.lenders = set()
        # Index: (lender_canonical, product) -> {attr_name -> [records]}
        self.attr_index = defaultdict(lambda: defaultdict(list))
        # Index: lender_canonical -> set of products
        self.lender_products = defaultdict(set)
        # Index: attr_name -> set of lender_canonical
        self.attr_to_lenders = defaultdict(set)

        for r in records:
            lc = r["lender_canonical"]
            prod = r["product"]
            self.lenders.add(lc)
            key = (lc, prod)
            self.attr_index[key][r["attr_name"]].append(r)
            self.lender_products[lc].add(prod)
            self.attr_to_lenders[r["attr_name"]].add(lc)

        # Add lenders from scenarios (lenders that only appear in CS sheets)
        for s in self.data.get("scenarios", []):
            for rec in s["recommendations"]:
                lc = rec["lender_canonical"]
                if lc and lc not in self.lenders:
                    self.lenders.add(lc)

        # Add lenders from credit grids
        for grid in self.data.get("credit_grids", []):
            lc = grid.get("lender_canonical")
            if lc and lc not in self.lenders:
                self.lenders.add(lc)

        # Build known lender names (sorted by length desc for greedy matching)
        self.known_lenders = sorted(self.lenders, key=len, reverse=True)

        # Index scenarios by condition text for fuzzy matching
        scenarios = self.data.get("scenarios", [])
        self.scenarios = scenarios
        self.scenario_index = []
        for s in scenarios:
            self.scenario_index.append({
                "id": s["scenario_id"],
                "condition": s["condition"],
                "condition_lower": s["condition"].lower().strip(),
                "product_type": s["product_type"],
                "recommendations": s["recommendations"],
                "source_sheet": s["source_sheet"],
            })

        # Extract actual lenders from scenario recommendations
        for si in self.scenario_index:
            lenders_direct = []
            lenders_in_detail = []
            for rec in si["recommendations"]:
                lc = rec["lender_canonical"]
                # Check if this is actually a lender name
                if lc in self.lenders:
                    lenders_direct.append(lc)
                # Also extract from detail text
                detail = rec.get("detail", "")
                for kl in self.known_lenders:
                    if kl.lower() in detail.lower() and kl not in lenders_direct and kl not in lenders_in_detail:
                        lenders_in_detail.append(kl)
            si["lenders_direct"] = lenders_direct
            si["lenders_in_detail"] = lenders_in_detail
            si["lenders_all"] = list(dict.fromkeys(lenders_direct + lenders_in_detail))

        # Pre-parse state_coverage and FICO data — prefer DB cache, fall back to live parse
        self.parsed_states = {}
        self.parsed_fico_tiers = {}
        for key, attr_map in self.attr_index.items():
            lc, prod = key
            for attr_name, recs in attr_map.items():
                if attr_name == "state_coverage":
                    raw = str(recs[0]["attr_value"]).strip()
                    self.parsed_states[(lc, prod)] = parse_state_coverage(raw)
                elif attr_name in ("fico_requirement_at_max_ltv", "fico_qualification", "dscr__prop_dti_min_max",
                                    "max__ltv_purchase", "max__ltv_cash_out_refi"):
                    raw = str(recs[0]["attr_value"]).strip()
                    self.parsed_fico_tiers[(lc, prod, attr_name)] = parse_fico_ltv_tiers(raw, attr_name)

        # Experience index
        # Note: substring match here is already tolerant of the
        # experience_minimum_(see_experience_cheat_sheet) vs
        # experience_minimum_see_experience_cheat_sheet naming difference.
        self.exp_index = {}
        for key, attr_map in self.attr_index.items():
            lc, prod = key
            for attr_name, recs in attr_map.items():
                no_under = attr_name.lower().replace('_', '').replace(' ', '')
                if 'experienceminimum' in no_under or 'minexperience' in no_under:
                    raw = str(recs[0]["attr_value"]).strip()
                    num = _extract_experience_min(raw)
                    if num is not None:
                        self.exp_index[(lc, prod, attr_name)] = {"min": num, "raw": raw}

        # Credit grid index
        self.credit_grids_by_lender = defaultdict(list)
        for grid in self.data.get("credit_grids", []):
            lc = grid.get("lender_canonical", "")
            if lc:
                self.credit_grids_by_lender[lc].append(grid)

    def get_lender_attr(self, lender, product, attr):
        """Get attribute value for a lender+product. Returns list of matching records."""
        key = (lender, product)
        if key in self.attr_index:
            return self.attr_index[key].get(attr, [])
        return []

    def get_all_attrs(self, lender, product=None):
        """Get all attributes for a lender, optionally filtered by product."""
        results = []
        for (lc, prod), attrs in self.attr_index.items():
            if lc == lender and (product is None or prod == product):
                for attr_name, recs in attrs.items():
                    results.extend(recs)
        return results

    def match_scenarios(self, query_text, threshold=0.4):
        """Fuzzy match scenario conditions against query text."""
        query_lower = query_text.lower().strip()
        query_tokens = set(query_lower.split())

        scored = []
        for si in self.scenario_index:
            cond = si["condition_lower"]

            # Token overlap score
            cond_tokens = set(cond.split())
            overlap = len(query_tokens & cond_tokens)
            union = len(query_tokens | cond_tokens)
            token_score = overlap / union if union > 0 else 0

            # Substring score
            sub_score = 1.0 if cond in query_lower or query_lower in cond else 0.0

            # Sequence match
            seq_score = SequenceMatcher(None, cond, query_lower).ratio()

            score = max(token_score, sub_score, seq_score)
            if score >= threshold:
                scored.append((score, si))

        scored.sort(key=lambda x: -x[0])
        return [si for _, si in scored]

    def filter_by_attr(self, lenders, product, criteria):
        """Filter lenders by attribute criteria. Returns (lender, matched_attrs)."""
        results = []
        for lender in lenders:
            matched = []
            for attr, condition in criteria.items():
                recs = self.get_lender_attr(lender, product, attr)
                for rec in recs:
                    val = rec["attr_value"]
                    if condition(val):
                        matched.append({
                            "attr": attr,
                            "value": val,
                            "match_reason": condition.__doc__ or f"matched {attr}={val}",
                            "source_sheet": rec["source_sheet"],
                            "source_row": rec["source_row"],
                        })
            if matched:
                results.append((len(matched), lender, matched))
        results.sort(key=lambda x: -x[0])
        return results

    def _get_city_map(self):
        if not hasattr(self, '_city_map'):
            cm_path = CORPUS_DIR / "city_map.json"
            self._city_map = json.loads(cm_path.read_text()) if cm_path.exists() else {}
        return self._city_map

    def parse_criteria(self, query_text):
        """Extract structured criteria from natural language query."""
        q = query_text.lower()
        criteria = {}
        product = None

        # Product detection
        product_map = {
            "dscr": "sfr_dscr", "sfr dscr": "sfr_dscr",
            "fix and flip": "fix_and_flip", "fnf": "fix_and_flip", "fix & flip": "fix_and_flip", "rehab": "fix_and_flip",
            "new construction": "new_construction", "ground up": "new_construction",
            "multifamily long term": "multifamily_lt", "multifamily lt": "multifamily_lt", "multi": "multifamily_lt",
            "bridge": "sfr_bridge", "sfr bridge": "sfr_bridge",
            "blanket": "sfr_blanket", "sfr blanket": "sfr_blanket",
            "multifamily rehab": "multifamily_rehab",
            "multi comm bridge": "multi_comm_bridge", "commercial bridge": "multi_comm_bridge",
            "sb commercial": "sb_commercial_lt", "small balance commercial": "sb_commercial_lt",
        }
        for phrase, prod in product_map.items():
            if phrase in q:
                product = prod
                break

        # FICO extraction
        fico_match = re.search(r'(\d{3})\s*(fico|credit|fako|score)', q)
        if not fico_match:
            fico_match = re.search(r'fico\s*[=:>]?\s*(\d{3})', q)
        if fico_match:
            criteria["fico"] = int(fico_match.group(1))

        # Loan amount extraction
        amt_match = re.search(r'\$?(\d{1,6})\s*([kmb])', q)
        if amt_match:
            val = int(amt_match.group(1))
            suffix = amt_match.group(2).lower()
            multiplier = {'k': 1000, 'm': 1000000, 'b': 1000000000}
            criteria["loan_amount"] = val * multiplier[suffix]
        else:
            amt_match = re.search(r'\$(\d{4,})', q)
            if amt_match:
                criteria["loan_amount"] = int(amt_match.group(1))

        # City/state extraction
        us_states = ["al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
                     "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
                     "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
                     "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy"]
        # 0. Try "City, ST" pattern first (e.g., "Springfield, MO", "Kansas City, MO")
        city_st = re.search(r'([A-Za-z\s]+),\s*([A-Za-z]{2})\b', q)
        if city_st:
            raw_city = city_st.group(1).strip().title()
            raw_st = city_st.group(2).upper()
            if raw_st.lower() in us_states:
                criteria["city"] = raw_city
                criteria["state"] = raw_st
                criteria["city_raw"] = raw_city
        # 1. Check city_map for suburb → metro mapping (e.g. Towson → Baltimore)
        if "city" not in criteria:
            city_map = self._get_city_map()
            for suburb, metro in city_map.items():
                if suburb.lower() in q:
                    criteria["city"] = metro
                    criteria["city_raw"] = suburb
                    break
        # 2. Fall back to known city list
        if "city" not in criteria:
            us_cities = ["baltimore", "chicago", "detroit", "cleveland", "philadelphia", "memphis",
                         "st louis", "kansas city", "springfield", "columbia", "jefferson city",
                         "denver", "dallas", "houston", "atlanta", "miami", "seattle", "portland",
                         "los angeles", "san francisco", "san diego", "phoenix", "nashville",
                         "charlotte", "orlando", "tampa", "indianapolis", "columbus", "milwaukee",
                         "minneapolis", "pittsburgh", "cincinnati", "richmond", "norfolk",
                         "boston", "new york", "brooklyn", "queens", "bronx", "staten island",
                         "newark", "buffalo", "rochester", "albany", "hartford", "new haven",
                         "providence", "portland"]
            for city in us_cities:
                if city in q:
                    criteria["city"] = city.title()
                    break
        # 3. State extraction (independent of city — state and city both useful)
        # Skip common English words that collide with state abbreviations
        skip_words = {"in", "al", "hi", "ok", "pa", "co", "la", "me", "ga", "or", "nv", "mt", "ma"}
        for state in us_states:
            if state in skip_words:
                continue
            pattern = r'\b' + state + r'\b'
            if re.search(pattern, q):
                criteria["state"] = state.upper()
                break
        if "state" not in criteria:
            # Try uppercase state abbreviations only (e.g., "MO", "IL")
            for state in us_states:
                if state in skip_words:
                    continue
                pattern = r'\b' + state.upper() + r'\b'
                if re.search(pattern, q):
                    criteria["state"] = state.upper()
                    break
        if "state" not in criteria and "city" in criteria:
            # City → state mapping for known cities
            city_state_map = {
                "baltimore": "MD", "annapolis": "MD", "rockville": "MD",
                "chicago": "IL", "springfield": "IL", "peoria": "IL",
                "detroit": "MI", "flint": "MI", "ann arbor": "MI",
                "cleveland": "OH", "columbus": "OH", "cincinnati": "OH",
                "philadelphia": "PA", "pittsburgh": "PA",
                "st louis": "MO", "kansas city": "MO",
                "indianapolis": "IN",
                "milwaukee": "WI",
                "minneapolis": "MN",
                "denver": "CO",
                "phoenix": "AZ",
                "atlanta": "GA",
                "miami": "FL", "tampa": "FL", "orlando": "FL",
                "seattle": "WA",
                "portland": "OR",
                "dallas": "TX", "houston": "TX", "austin": "TX", "san antonio": "TX",
                "los angeles": "CA", "san francisco": "CA", "san diego": "CA",
                "boston": "MA",
                "new york": "NY",
                "memphis": "TN", "nashville": "TN",
                "charlotte": "NC",
                "richmond": "VA",
                "norfolk": "VA",
                "newark": "NJ",
                "hartford": "CT",
                "providence": "RI",
            }
            city_key = criteria["city"].lower().strip()
            if city_key in city_state_map:
                criteria["state"] = city_state_map[city_key]
        if "state" not in criteria:
            # Full state name → abbreviation
            full_states = {
                "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
                "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
                "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
                "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
                "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
                "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
                "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
                "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
                "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
                "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
                "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
                "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
                "wisconsin": "WI", "wyoming": "WY",
            }
            for full_name, abbr in full_states.items():
                if full_name in q:
                    criteria["state"] = abbr
                    break

        # Experience extraction
        exp_match = re.search(r'(\d+)\s*(prior flip|flip|experience|deals|rehabs)', q)
        if exp_match:
            criteria["experience"] = int(exp_match.group(1))

        # Property count extraction (for blanket detection)
        # First try direct match: "6 properties", "3 units"
        prop_match = re.search(r'(\d+)\s*(properties|units|doors|buildings)', q)
        if not prop_match:
            # Try with intervening word: "6 Texas properties"
            prop_match = re.search(r'(\d+)\s+\w+\s+(properties|units)', q)
        if not prop_match:
            # Try "six properties" (word number)
            word_nums = {'one':1, 'two':2, 'three':3, 'four':4, 'five':5,
                         'six':6, 'seven':7, 'eight':8, 'nine':9, 'ten':10}
            for wn, n in word_nums.items():
                if re.search(rf'\b{wn}\s+(properties|units|doors|buildings)', q):
                    prop_match = (n, wn)
                    break
        if prop_match:
            if isinstance(prop_match, tuple):
                criteria["property_count"] = prop_match[0]
            else:
                criteria["property_count"] = int(prop_match.group(1))

        # Property value
        val_match = re.search(r'\$?(\d{2,6})\s*[kkm]?\s*(property|home|house|value)', q)
        if val_match:
            val = int(val_match.group(1))
            suffix = val_match.group(0)
            if 'k' in suffix.lower() or 'm' in suffix.lower() or val < 200:
                criteria["property_value"] = val * 1000
            else:
                criteria["property_value"] = val

        # Excluded lenders
        exclude_match = re.search(r'exclud(?:e|ing)\s+(.+?)(?:$|\.)', q)
        if exclude_match:
            excluded_raw = exclude_match.group(1)
            criteria["exclude"] = [x.strip().lower() for x in excluded_raw.split(",") if x.strip()]

        return criteria, product

    def query(self, query_text):
        """Main query: parse criteria, match scenarios, filter lenders, score, cite sources."""
        criteria, product = self.parse_criteria(query_text)

        # 1. Match scenarios
        matched_scenarios = self.match_scenarios(query_text)

        # 1a. Also try to match city/state-specific scenarios from criteria
        city_state = (criteria.get("city", "") or criteria.get("state", "")).lower()
        if city_state:
            for si in self.scenario_index:
                if city_state in si["condition_lower"] and si not in matched_scenarios:
                    matched_scenarios.append(si)

        # 2. Collect candidate lenders from scenarios + attributes
        candidate_lenders = set()
        scenario_evidence = defaultdict(list)

        for si in matched_scenarios:
            for lender in si["lenders_all"]:
                # Filter scenario lenders by product compatibility
                if product and product not in self.lender_products.get(lender, set()):
                    continue
                candidate_lenders.add(lender)
                scenario_evidence[lender].append({
                    "type": "scenario",
                    "scenario": si["condition"],
                    "product_type": si["product_type"],
                    "source_sheet": si["source_sheet"],
                })

        # If no scenario matched, fall back to attribute-based
        if not candidate_lenders and product:
            candidate_lenders = self.attr_to_lenders.get("fico_min", set()) | \
                                self.attr_to_lenders.get("max__ltv_purchase", set())
        elif not candidate_lenders:
            # All lenders
            candidate_lenders = self.lenders.copy()

        # 3. Filter by product (also covers fallback lenders)
        if product:
            candidate_lenders = {l for l in candidate_lenders
                                 if product in self.lender_products.get(l, set())}

        # 3a. Filter by experience minimum
        if "experience" in criteria:
            exp_val = criteria["experience"]
            filtered = set()
            for lender in candidate_lenders:
                meets_min = True
                reasons = []
                prod = product or "fix_and_flip"
                for (lc, lp, attr_name), info in self.exp_index.items():
                    if lc == lender and lp == prod:
                        if info["min"] > 100:
                            continue  # skip date values parsed as numbers
                        # 'experience_minimum' attr = hard floor for eligibility
                        if 'experience_minimum' in attr_name and info["min"] > exp_val:
                            meets_min = False
                            reasons.append(f"requires {info['min']:.0f}+ exp (has {exp_val})")
                        # 'min_experience_for_max_ltc' attr = best-terms threshold (note only)
                        elif 'min_experience_for_max_ltc' in attr_name and info["min"] > exp_val:
                            reasons.append(f"best terms need {info['min']:.0f}+ exp (has {exp_val})")
                if meets_min:
                    filtered.add(lender)
                for r in reasons:
                    scenario_evidence[lender].append({
                        "type": "experience",
                        "detail": r,
                    })
            candidate_lenders = filtered

        # 4. Score lenders
        scored = []
        for lender in candidate_lenders:
            reasons = list(scenario_evidence.get(lender, []))
            score = 0.0

            # Check product match
            if product and product in self.lender_products.get(lender, set()):
                score += 0.3
                if not any(r["type"] == "scenario" for r in reasons):
                    reasons.append({
                        "type": "product_match",
                        "detail": f"Offers {product}",
                    })

            # Check FICO — uses LLM-parsed structured tiers
            if "fico" in criteria:
                fico_val = criteria["fico"]
                tier_parsed = None
                # Try fico_requirement_at_max_ltv → fico_qualification → max__ltv_purchase → max__ltv_cash_out_refi
                for attr in ("fico_requirement_at_max_ltv", "fico_qualification", "max__ltv_purchase", "max__ltv_cash_out_refi"):
                    tier_parsed = self.parsed_fico_tiers.get((lender, product or "", attr))
                    if tier_parsed:
                        # Check if it has actual FICO tiers
                        if any("min_fico" in t for t in tier_parsed.get("tiers", [])):
                            break
                        tier_parsed = None
                    # Try other products
                    if not tier_parsed:
                        for other_prod in self.lender_products.get(lender, []):
                            tp = self.parsed_fico_tiers.get((lender, other_prod, attr))
                            if tp and any("min_fico" in t for t in tp.get("tiers", [])):
                                tier_parsed = tp
                                break
                    if tier_parsed:
                        break
                if tier_parsed:
                    matched, why, _ = fico_matches(tier_parsed, fico_val)
                    if matched is True:
                        score += 0.4
                        reasons.append({
                            "type": "attribute",
                            "detail": f"FICO check: {why}",
                            "source": tier_parsed.get("notes", "") or tier_parsed.get("raw", "")[:80],
                        })
                    elif matched == "close":
                        score += 0.2
                        reasons.append({
                            "type": "attribute",
                            "detail": f"FICO check: {why}",
                        })
                    elif matched is None:
                        # No structured data — fall back to raw lookup
                        reasons.append({
                            "type": "attribute",
                            "detail": f"FICO check: {why}",
                        })

                # Credit grid FICO→LTV lookup (CS-CREDIT sheet)
                fico_val = criteria["fico"]
                # Try exact match first, then case-insensitive
                cg_match = None
                for cg_lc, grids in self.credit_grids_by_lender.items():
                    if cg_lc.lower() == lender.lower():
                        for grid in grids:
                            buckets = grid.get("grid", {})
                            # Find the highest FICO bucket the borrower qualifies for
                            best_ltv = None
                            best_fico_min = 0
                            for fico_str, ltv_note in buckets.items():
                                try:
                                    fico_min = int(fico_str)
                                except ValueError:
                                    continue
                                if fico_val >= fico_min and fico_min >= best_fico_min:
                                    best_fico_min = fico_min
                                    best_ltv = ltv_note
                            if best_ltv:
                                score += 0.2
                                cg_match = best_ltv
                                reasons.append({
                                    "type": "credit_grid",
                                    "detail": f"FICO {fico_val} ≥ {best_fico_min} → LTV up to {best_ltv[:60]}",
                                    "source_sheet": grid.get("source_sheet", "CS-CREDIT"),
                                })
                                break
                if not cg_match:
                    # If FICO < lender's min_fico in grid, note it
                    for cg_lc, grids in self.credit_grids_by_lender.items():
                        if cg_lc.lower() == lender.lower():
                            for grid in grids:
                                min_f = grid.get("min_fico")
                                if min_f is not None and fico_val < min_f:
                                    reasons.append({
                                        "type": "credit_grid",
                                        "detail": f"FICO {fico_val} below lender minimum {min_f}",
                                        "source_sheet": grid.get("source_sheet", "CS-CREDIT"),
                                    })
                                break

            # Check city/state — uses LLM-parsed structured data
            if "city" in criteria or "state" in criteria:
                st_parsed = self.parsed_states.get((lender, product or ""))
                if not st_parsed:
                    for other_prod in self.lender_products.get(lender, []):
                        st_parsed = self.parsed_states.get((lender, other_prod))
                        if st_parsed:
                            break
                if st_parsed:
                    # Check city exclusions first (e.g., "No Baltimore", "No Cook County")
                    if "city" in criteria:
                        includes_city, why_city = state_includes(st_parsed, criteria["city"])
                        if includes_city is False:
                            reasons.append({
                                "type": "attribute",
                                "detail": f"city exclusion: {criteria['city']} — {why_city}",
                                "source": st_parsed.get("raw", "")[:100],
                            })
                            # Don't add state bonus
                        else:
                            score += 0.2
                            reasons.append({
                                "type": "attribute",
                                "detail": f"city '{criteria['city']}' OK: {why_city}",
                                "source": st_parsed.get("raw", "")[:100],
                            })
                    # Check state
                    if "state" in criteria:
                        includes_st, why_st = state_includes(st_parsed, criteria["state"])
                        if includes_st is True:
                            score += 0.3
                            reasons.append({
                                "type": "attribute",
                                "detail": f"state_coverage: {why_st}",
                                "source": st_parsed.get("raw", "")[:100],
                            })
                        elif includes_st is False:
                            reasons.append({
                                "type": "attribute",
                                "detail": f"state_coverage excludes {criteria['state']}: {why_st}",
                            })

            # Check loan amount
            if "loan_amount" in criteria:
                la = criteria["loan_amount"]

                def _get_max_numeric(recs):
                    m = None
                    for r in recs:
                        v = r["attr_value"]
                        if isinstance(v, (int, float)):
                            if m is None or v > m:
                                m = v
                    return m

                # loan_min check
                min_recs = self.get_lender_attr(lender, product or "fix_and_flip", "min_loan_amount")
                if min_recs:
                    min_val = _get_max_numeric(min_recs)
                    if min_val is not None and min_val <= la:
                        score += 0.2
                        reasons.append({
                            "type": "attribute",
                            "detail": f"loan_min={min_val} ≤ ${la} loan",
                            "source_sheet": min_recs[0]["source_sheet"],
                            "source_row": min_recs[0]["source_row"],
                        })

                # loan_max check: penalize if known max < requested
                max_recs = self.get_lender_attr(lender, product or "fix_and_flip", "max_loan_amount")
                if not max_recs and product:
                    for p in self.lender_products.get(lender, []):
                        max_recs = self.get_lender_attr(lender, p, "max_loan_amount")
                        if max_recs:
                            break
                if max_recs:
                    max_val = _get_max_numeric(max_recs)
                    if max_val is not None:
                        if max_val >= la:
                            score += 0.2
                            reasons.append({
                                "type": "attribute",
                                "detail": f"loan_max=${max_val:,.0f} ≥ ${la} loan",
                                "source_sheet": max_recs[0]["source_sheet"],
                                "source_row": max_recs[0]["source_row"],
                            })
                        else:
                            score -= 1.0
                            reasons.append({
                                "type": "attribute",
                                "detail": f"loan_max=${max_val:,.0f} < requested ${la} (insufficient capacity)",
                            })

            # Check experience
            if "experience" in criteria:
                exp = criteria["experience"]
                exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                                "experience_minimum_see_experience_cheat_sheet")
                if not exp_recs:
                    exp_recs = self.get_lender_attr(lender, product or "fix_and_flip",
                                                    "min_experience_for_max_ltcarv")
                if exp_recs:
                    attr_name = exp_recs[0]["attr_name"]
                    reasons.append({
                        "type": "attribute",
                        "detail": f"{attr_name}={exp_recs[0]['attr_value']} (query: {exp} flips)",
                        "source_sheet": exp_recs[0]["source_sheet"],
                        "source_row": exp_recs[0]["source_row"],
                    })

            if reasons:
                scored.append((score, lender, reasons))

        # 5. Sort by score descending
        scored.sort(key=lambda x: -x[0])

        # 5a. Apply exclusions
        excluded = set(criteria.get("exclude", []))
        if excluded:
            scored = [(s, l, r) for s, l, r in scored
                      if l.lower() not in excluded and not any(x in l.lower() for x in excluded)]

        # 6. Build output
        matches = []
        for score, lender, reasons in scored:
            reasons_deduped = []
            seen = set()
            for r in reasons:
                key = (r["type"], r.get("detail", ""), r.get("scenario", ""))
                if key not in seen:
                    seen.add(key)
                    reasons_deduped.append(r)

            # Gather sources
            sources = []
            for r in reasons_deduped:
                if "source_sheet" in r:
                    sources.append({
                        "sheet": r["source_sheet"],
                        "row": r.get("source_row"),
                    })

            matches.append({
                "lender": lender,
                "score": round(score, 2),
                "reasons": reasons_deduped,
                "sources": sources,
            })

        return {
            "query": query_text,
            "criteria": criteria,
            "product": product,
            "scenarios_matched": [si["condition"] for si in matched_scenarios],
            "matches": matches,
            "total_candidates": len(scored),
        }


if __name__ == "__main__":
    engine = CreditBoxEngine()
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "640 FICO Baltimore fix and flip 1 flip"
    result = engine.query(query)
    print(json.dumps(result, indent=2, default=str))

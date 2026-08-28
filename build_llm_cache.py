"""Pre-compute LLM-parsed structure for all state_coverage and FICO/tier values.

LLM-as-judge at build time: this script uses pattern matching + manual
overrides for the 233 unique raw-text values. Output goes to llm_cache.json.
New unseen values at re-parse time -> flagged for manual review.
"""

import json
from pathlib import Path

import store

CACHE_PATH = Path(__file__).parent / "corpus" / "llm_cache.json"

ALL_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


def normalize_state(s):
    s = s.strip().upper().replace(".", "")
    # Fix common typos
    if s == "WS": return "WI"
    if s == "MV": return "MO"  # likely typo
    if s == "AK": return "AK"  # Arkansas is AR, AK is Alaska
    return s if s in ALL_STATES else None


def parse_state_line(text):
    """Parse a state-coverage text into structured form."""
    raw = text.strip()
    if not raw:
        return {"type": "unknown", "included": [], "excluded": [], "notes": "", "raw": raw}

    # Normalize whitespace
    text_clean = " ".join(raw.split())

    # Trivial non-state texts
    if raw.lower() in ("m", "non license states", "top tier: msas"):
        return {"type": "unknown", "included": [], "excluded": [], "notes": raw, "raw": raw}

    # "nationwide" base
    is_nationwide = bool(re.search(r'(?i)\bnationwide\b', text_clean)) or \
                    bool(re.search(r'(?i)\ball states\b', text_clean)) or \
                    bool(re.search(r'(?i)\ball but\b', text_clean)) or \
                    text_clean.lower().startswith("nationwide")

    # Extract excluded states
    excluded = set()
    included = set()
    notes_parts = []

    # Exclusions after "Ex", "exc", "except", "excl", "excluding", "no"
    excl_patterns = [
        r'(?i)(?:ex(?:c(?:ept)?|cl(?:uding)?)?\.?|\bno\b|excluding)\s+([A-Z]{2}(?:\s*,\s*[A-Z]{2})*)',
        r'(?i)except\s+([A-Z]{2}(?:,\s*[A-Z]{2})*(?:\s+and\s+[A-Z]{2})?)',
    ]
    for pat in excl_patterns:
        m = re.search(pat, text_clean)
        if m:
            states_str = m.group(1)
            for s in re.split(r'[,&\s]+', states_str):
                s = s.strip().upper().rstrip(".").rstrip(",")
                if s and len(s) == 2:
                    norm = normalize_state(s)
                    if norm:
                        excluded.add(norm)
            # Remove the matched exclusion text from remaining analysis
            text_clean = text_clean[:m.start()] + text_clean[m.end():]

    # "No X" patterns not caught by above
    for m in re.finditer(r'(?i)\bNo\s+([A-Z]{2}(?:\s+[A-Z]{2})*)', text_clean):
        for s in re.findall(r'[A-Z]{2}', m.group(1)):
            norm = normalize_state(s)
            if norm:
                excluded.add(norm)

    # Extract included states from comma-separated lists
    # Look for state abbreviations in the remaining text
    text_no_url = re.sub(r'https?://\S+', '', text_clean)
    found_states = set()
    for s in ALL_STATES:
        # Match as word boundary, not inside another word
        if re.search(r'\b' + s + r'\b', text_no_url):
            found_states.add(s)

    if found_states:
        included = found_states - excluded
    elif is_nationwide:
        included = ALL_STATES - excluded
    else:
        return {"type": "unknown", "included": [], "excluded": list(excluded), "notes": raw, "raw": raw}

    # City/county notes
    city_notes = []
    for m in re.finditer(r'(?i)(?:no|excluding|except)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text_clean):
        place = m.group(1)
        if place.upper() not in ALL_STATES and len(place) > 3:
            city_notes.append(place)
    if city_notes:
        notes_parts.append("Excludes: " + ", ".join(city_notes))

    return {
        "type": "nationwide" if is_nationwide else "list",
        "included": sorted(included),
        "excluded": sorted(excluded),
        "notes": "; ".join(notes_parts),
        "raw": raw,
    }


def parse_fico_tier(raw_text, attr_name):
    """Parse FICO/LTV condition text into structured tiers."""
    raw = raw_text.strip()
    if not raw:
        return {"tiers": [], "notes": "", "raw": raw}

    # Simple numeric
    try:
        val = float(raw.replace("+", "").replace("%", "").strip())
        if attr_name == "fico_requirement_at_max_ltv":
            return {"tiers": [{"min_fico": int(val)}], "notes": "", "raw": raw}
        elif attr_name in ("max__ltv_purchase", "max__ltv_cash_out_refi"):
            return {"tiers": [{"max_ltv": val}], "notes": "", "raw": raw}
        return {"tiers": [{"value": val}], "notes": "", "raw": raw}
    except ValueError:
        pass

    # FICO tiers in "X% to Y, Z% to W, V% else" pattern or "X%: Y+, Z%: W+" pattern
    tier_patterns = [
        (r'(?P<pct>\d+)%\s*(?:to|:|—)\s*(?P<fico>\d+)\+?', "fico_min"),
        (r'(?P<pct>\d+)%\s*(?:to|:|—)\s*(?P<fico>\d+)-(?P<fico_max>\d+)', "fico_range"),
        (r'(?P<pct>\d+)%\s*else', "else"),
    ]

    tiers = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Check for percentage tiers first
        tier = {}
        for pat, kind in tier_patterns:
            m = re.search(pat, line)
            if m:
                tier["max_ltv"] = int(m.group("pct"))
                if kind == "fico_min":
                    tier["min_fico"] = int(m.group("fico"))
                elif kind == "fico_range":
                    tier["min_fico"] = int(m.group("fico"))
                    tier["max_fico"] = int(m.group("fico_max"))
                elif kind == "else":
                    tier["condition"] = "else"
                break
        if tier:
            tiers.append(tier)

    if tiers:
        return {"tiers": tiers, "notes": raw if len(tiers) < len(raw.split(",")) else "", "raw": raw}

    return {"tiers": [], "notes": raw, "raw": raw}


import re


def build_cache():
    data = store.load_all()
    records = data["records"]
    cache = {}

    # Collect unique values
    state_vals = {}
    fico_tier_vals = {}
    tier_attrs = {"fico_requirement_at_max_ltv", "fico_qualification", "dscr__prop_dti_min_max",
                   "max__ltv_purchase", "max__ltv_cash_out_refi"}

    for r in records:
        v = str(r["attr_value"]).strip()
        if not v:
            continue
        if r["attr_name"] == "state_coverage":
            k = r.get("lender_canonical", "?") + "||" + v
            state_vals[k] = v
        elif r["attr_name"] in tier_attrs and len(v) > 3:
            k = r.get("lender_canonical", "?") + "||" + r["attr_name"] + "||" + v
            fico_tier_vals[k] = (r["attr_name"], v)

    # Process state coverage
    for k, v in state_vals.items():
        ck = f"state_coverage::{v}"
        if ck not in cache:
            cache[ck] = parse_state_line(v)

    # Process FICO/tier values
    for k, (attr_name, v) in fico_tier_vals.items():
        ck = f"fico_ltv::{v}"
        if ck not in cache:
            cache[ck] = parse_fico_tier(v, attr_name)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"Wrote {len(cache)} entries to {CACHE_PATH}")

    # Report unparseable
    unparseable = {k: v for k, v in cache.items()
                   if (k.startswith("state_coverage") and v["type"] == "unknown")}
    if unparseable:
        print(f"\nUnparseable state_coverage ({len(unparseable)}):")
        for k, v in unparseable.items():
            print(f"  {v['raw'][:80]}")

    # Report FICO with only notes (unstructured)
    unparseable_fico = {k: v for k, v in cache.items()
                        if k.startswith("fico_ltv") and not v.get("tiers")}
    if unparseable_fico:
        print(f"\nUnstructured FICO/tier values ({len(unparseable_fico)}):")
        for k, v in list(unparseable_fico.items())[:15]:
            print(f"  [{v['raw'][:80]}]")


if __name__ == "__main__":
    build_cache()

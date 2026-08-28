"""
LLM-as-judge module for credit box data.

Two modes:
  1. Parse-time enrichment: structure freeform text → JSON (state lists, FICO/LTV tiers)
  2. Query-time judgment: LLM resolves ambiguous questions against raw text

Design: structured data queried first; LLM judge invoked for edge cases
and unparseable text. Results cached in llm_cache.json.

The pre_compute=False path uses basic pattern matching for common cases
and LLM judgment for the rest. Set PRE_COMPUTE=True to generate full cache.
"""

import json, re, os
from pathlib import Path
from typing import Optional

CACHE_PATH = Path(__file__).parent / "corpus" / "llm_cache.json"
PRE_COMPUTE = False  # set True to re-generate full cache from corpus

ALL_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

# Manual overrides for text that pattern matching cannot handle
STATE_OVERRIDES = {}

FICO_OVERRIDES = {}


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, default=str))


def _normalize(s):
    return s.strip().upper().replace(".", "")


def _fix_state(s):
    norm = _normalize(s)
    if norm == "WS": return "WI"
    if norm == "MV": return "MO"
    if norm in ALL_STATES:
        return norm
    return None


def parse_state_coverage(raw_text) -> dict:
    """Parse state coverage text → structured dict.

    Returns:
      {"type": "nationwide"|"list"|"unknown",
       "included": ["AL",...] or "ALL",
       "excluded": ["AK",...],
       "notes": "city exclusions",
       "raw": raw_text}
    """
    cache = load_cache()
    key = f"state_coverage::{raw_text.strip()}"
    if key in cache:
        return cache[key]

    if raw_text.strip() in STATE_OVERRIDES:
        result = STATE_OVERRIDES[raw_text.strip()]
        cache[key] = result
        save_cache(cache)
        return result

    result = _parse_state_internal(raw_text)
    if PRE_COMPUTE or result["type"] != "unknown":
        cache[key] = result
        save_cache(cache)
    return result


def _parse_state_internal(raw_text):
    raw = raw_text.strip()
    if not raw:
        return {"type": "unknown", "included": [], "excluded": [], "city_excluded": [], "notes": "", "raw": raw}

    clean = raw.replace("\n", " ").replace("|", ",")
    clean = re.sub(r'\s+', ' ', clean)
    clean_lower = clean.lower()

    # URLs — remove
    clean_no_url = re.sub(r'https?://\S+', '', clean)

    # Trivial non-state texts
    no_match_triggers = ["about crebrid", "non license", "top tier", "see map", "m$"]
    if any(t in clean_lower for t in no_match_triggers) or clean_lower.strip() in ("m",):
        return {"type": "unknown", "included": [], "excluded": [], "city_excluded": [], "notes": raw, "raw": raw}

    is_nationwide = bool(re.search(r'\bnationwide\b', clean_lower)) or \
                    bool(re.search(r'\ball states\b', clean_lower)) or \
                    bool(re.search(r'\ball but\b', clean_lower))

    excluded = set()
    included = set()
    notes = []
    city_excluded = []

    # === Extract explicit exclusions ===
    # "Ex: X, Y, Z" / "Excluding X, Y" / "No X"
    excl_phrases = [
        r'ex(?:cl(?:uding|usive)?)?\.?\s*:?\s*([A-Z]{2}(?:\s*[,;&\s]+[A-Z]{2})*)',
        r'except\s+([A-Z]{2}(?:\s*[,;&\s]+[A-Z]{2})*(?:\s+and\s+[A-Z]{2})?)',
        r'excluding\s+([A-Z]{2}(?:\s*[,;&\s]+[A-Z]{2})*)',
        r'\bno\s+([A-Z]{2}(?:\s*[,;&\s]+[A-Z]{2})*)',
        r'doesn\'?t\s+like\s+([A-Za-z]+)',
    ]
    for pat in excl_phrases:
        for m in re.finditer(pat, clean):
            group = m.group(1)
            for tok in re.split(r'[,;&\s]+', group):
                tok = tok.strip().upper().rstrip(".").rstrip(",")
                if len(tok) == 2:
                    fixed = _fix_state(tok)
                    if fixed:
                        excluded.add(fixed)
                elif len(tok) > 2:
                    notes.append(f"Excludes: {tok}")

    # City/region exclusions: "No Baltimore" / "No Detroit or Flint" / "No Cook County"
    for m in re.finditer(r'(?i)(?:no|excluding|ex)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)', clean):
        place = m.group(1).strip()
        if len(place) > 3:
            notes.append(f"Excludes: {place}")
            city_excluded.append(place)
    # Parenthesized city exclusions: "(Ex Baltimore)", "(No Baltimore)", "(Ex Cook County)"
    for m in re.finditer(r'\((?:Ex|No|Excluding)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\)', clean, re.IGNORECASE):
        place = m.group(1).strip()
        if len(place) > 3:
            notes.append(f"Excludes: {place}")
            city_excluded.append(place)

    # "Restrictions apply" notes
    rest_match = re.search(r'(?i)(?:restrictions?\s+apply|restrictions?\s+in)\s*:?\s*([A-Z, ]+)', clean)
    if rest_match:
        notes.append(f"Restrictions: {rest_match.group(1).strip()}")

    # "Exception needed" / "Exception only states" notes
    exc_match = re.search(r'(?i)(?:exception\s+(?:needed|only))\s*:?\s*([^\.]+)', clean)
    if exc_match:
        notes.append(f"Exception: {exc_match.group(1).strip()}")

    # === Extract included states from comma-separated lists ===
    found_states = set()
    for s in ALL_STATES:
        if re.search(r'\b' + s + r'\b', clean_no_url):
            found_states.add(s)

    # Exclude states mentioned in exclusion phrases from included
    found_included = found_states - excluded

    # Detect "All states except X" — set included to ALL
    if is_nationwide or found_included == ALL_STATES or \
       (is_nationwide and not found_included):
        return {
            "type": "nationwide",
            "included": "ALL",
            "excluded": sorted(excluded),
            "city_excluded": city_excluded,
            "notes": "; ".join(notes) if notes else "",
            "raw": raw,
        }
    elif found_included:
        return {
            "type": "list",
            "included": sorted(found_included),
            "excluded": sorted(excluded),
            "city_excluded": city_excluded,
            "notes": "; ".join(notes) if notes else "",
            "raw": raw,
        }
    else:
        return {"type": "unknown", "included": [], "excluded": [], "city_excluded": [], "notes": raw, "raw": raw}


def parse_fico_ltv_tiers(raw_text, attr_name=None) -> dict:
    """Parse FICO/LTV condition text into structured tiers.

    Returns:
      {"tiers": [{"min_fico": 720, "max_ltv": 90, "condition": None}, ...],
       "note_type": "single_value"|"tiered"|"text"|"unparseable",
       "notes": "human-readable summary",
       "raw": raw_text}
    """
    cache = load_cache()
    key = f"fico_ltv::{raw_text.strip()}"
    if key in cache:
        return cache[key]

    if raw_text.strip() in FICO_OVERRIDES:
        result = FICO_OVERRIDES[raw_text.strip()]
        cache[key] = result
        save_cache(cache)
        return result

    result = _parse_fico_internal(raw_text, attr_name)
    if PRE_COMPUTE or result["note_type"] != "unparseable":
        cache[key] = result
        save_cache(cache)
    return result


def _parse_fico_internal(raw_text, attr_name=None):
    raw = raw_text.strip()
    if not raw:
        return {"tiers": [], "note_type": "unparseable", "notes": "", "raw": raw}

    clean = " ".join(raw.replace("\n", " ").split())

    # Simple numeric
    try:
        stripped = clean.replace("+", "").replace("%", "").strip()
        val = float(stripped)
        if attr_name == "fico_requirement_at_max_ltv":
            return {"tiers": [{"min_fico": int(val)}], "note_type": "single_value", "notes": f"FICO ≥{int(val)}", "raw": raw}
        elif attr_name in ("max__ltv_purchase", "max__ltv_cash_out_refi"):
            return {"tiers": [{"max_ltv": int(val)}], "note_type": "single_value", "notes": f"LTV ≤{int(val)}%", "raw": raw}
        return {"tiers": [{"value": val}], "note_type": "single_value", "notes": str(val), "raw": raw}
    except ValueError:
        pass

    # Tier patterns: "X% to Y, Z% to W" or "X%: Y+, Z%: W+" or "X% for Y, Z% else"
    tiers = []

    # Pattern 1: "X% to Y, Z% to W, V% else" — LTV to FICO
    tier_pattern = re.findall(r'(\d+)%\s*(?:to|:|=)\s*(\d+)(?:\+?)\s*(?:fico|FICO)?', raw)
    else_pattern = re.findall(r'(\d+)%\s*else', raw)

    if tier_pattern:
        for pct, fico in tier_pattern:
            tiers.append({"max_ltv": int(pct), "min_fico": int(fico)})
        if else_pattern:
            for pct in else_pattern:
                tiers.append({"max_ltv": int(pct), "condition": "else"})
        if tiers:
            return {"tiers": tiers, "note_type": "tiered", "notes": f"{len(tiers)} tiers", "raw": raw}

    # Pattern 2: FICO-conditioned DSCR values
    # "1.10 for 720+ FICO" / "1.20 for <720 FICO"
    dscr_tiers = re.findall(r'(\d+\.?\d*)\s*(?:x\s*)?(?:\bmin\b)?\s+(?:for|with)\s+(?:\$.*)?(?:FICO\s*)?(\d{3})(?:\+|\s*-\s*\d{3})?', raw, re.IGNORECASE)
    if dscr_tiers:
        for dscr, fico in dscr_tiers:
            tiers.append({"min_dscr": float(dscr), "min_fico": int(fico)})
        if tiers:
            return {"tiers": tiers, "note_type": "tiered", "notes": f"{len(tiers)} DSCR/FICO tiers", "raw": raw}

    # Pattern 3: "X% LTV" with FICO conditions mixed in
    ltv_fico = re.findall(r'(\d+)%LTV\s*(?:to|:|=)\s*(\d+)', raw, re.IGNORECASE)
    if not ltv_fico:
        ltv_fico = re.findall(r'(\d+)%\s*(?:LTV|ltv)\s+(?:\w+\s+)?(\d{3})', raw)
    if not ltv_fico:
        ltv_fico = re.findall(r'(\d+)%\s+LTV\s+(?:to\s+)?(?:get\s+)?(\d{3})', raw)
    if ltv_fico:
        for pct, fico in ltv_fico:
            tiers.append({"max_ltv": int(pct), "min_fico": int(fico)})
        return {"tiers": tiers, "note_type": "tiered", "notes": f"{len(tiers)} LTV/FICO tiers", "raw": raw}

    # Pattern 4: FICO multi-value
    fico_multi = re.findall(r'(\d{3})\s*(?:\(([^)]+)\))?', raw)
    if len(fico_multi) >= 2 and all(int(f) >= 600 for f, _ in fico_multi if f.isdigit()):
        for fico, note in fico_multi:
            if fico.isdigit() and int(fico) >= 600:
                t = {"min_fico": int(fico)}
                if note:
                    t["note"] = note.strip()
                tiers.append(t)
        if tiers:
            return {"tiers": tiers, "note_type": "tiered", "notes": f"{len(tiers)} FICO tiers", "raw": raw}

    # Pattern 5: DSCR values
    dscr_match = re.search(r'(\d+\.?\d*)\s*(?:x\s*)?DSCR', raw, re.IGNORECASE)
    if dscr_match:
        return {"tiers": [{"min_dscr": float(dscr_match.group(1))}], "note_type": "single_value", "notes": f"DSCR ≥{dscr_match.group(1)}", "raw": raw}

    # Single DSCR number
    dscr_num = re.findall(r'(\d\.\d+)', raw)
    if len(dscr_num) == 1:
        return {"tiers": [{"min_dscr": float(dscr_num[0])}], "note_type": "single_value", "notes": f"DSCR ≥{dscr_num[0]}", "raw": raw}

    # Common text aliases
    low_texts = {
        "no min": "no_min", "no ratio": "no_ratio", "none stated": "no_stated",
        "no credit check": "no_credit_check", "case by case": "case_by_case",
    }
    ct = clean.lower().strip().rstrip(".").strip()
    if ct in low_texts:
        return {"tiers": [{"qualifier": low_texts[ct]}], "note_type": "text", "notes": ct, "raw": raw}

    return {"tiers": [], "note_type": "unparseable", "notes": raw, "raw": raw}


def parse_text(raw_text: str, attr_name: str = None) -> dict:
    """Parse any freeform text using the appropriate parser."""
    if attr_name == "state_coverage":
        return parse_state_coverage(raw_text)
    if attr_name in ("fico_requirement_at_max_ltv", "fico_qualification", "dscr__prop_dti_min_max",
                      "max__ltv_purchase", "max__ltv_cash_out_refi"):
        return parse_fico_ltv_tiers(raw_text, attr_name)
    return {"type": "text", "raw": raw_text, "notes": ""}


def state_includes(st_parsed: dict, place: str) -> tuple:
    """Check if a parsed state_coverage includes a given place.

    Returns (bool, source: str).
    """
    place_lower = place.lower().strip()
    place_upper = place_lower.upper()

    # City check from structured city_excluded list
    city_excluded = st_parsed.get("city_excluded", [])
    for ce in city_excluded:
        if place_lower in ce.lower() or ce.lower() in place_lower:
            return (False, f"city/region '{ce}' excluded in state_coverage")
    # City check from notes (backup)
    if st_parsed.get("notes"):
        if place_lower in st_parsed["notes"].lower():
            return (False, f"city/region explicitly excluded in notes")

    # State check
    if place_upper in ALL_STATES:
        included = st_parsed.get("included", [])
        excluded = st_parsed.get("excluded", [])
        if place_upper in excluded:
            return (False, f"state {place_upper} in exclusion list")
        if included == "ALL":
            return (True, "nationwide coverage")
        if place_upper in included:
            return (True, f"state {place_upper} in inclusion list")
        if st_parsed.get("type") == "unknown":
            return (None, "coverage text unparseable — use LLM judge")
        return (False, f"state {place_upper} not in coverage list")

    # City not in state list — check raw text
    raw_lower = st_parsed.get("raw", "").lower()
    if "nationwide" in raw_lower and place_lower not in raw_lower:
        # Check exclusion text
        ex_match = re.search(r'ex(?:cl(?:ude|usive)?)?[:\s]*([^\.]+)', raw_lower)
        if ex_match and place_lower in ex_match.group(1).lower():
            return (False, f"city/state mentioned in exclusions")
        return (True, "nationwide coverage, not excluded")

    return (None, f"ambiguous — use LLM judge for {place}")


def fico_matches(tier_parsed: dict, fico: int) -> tuple:
    """Check if a parsed FICO tier matches given FICO score.

    Only considers tiers with explicit min_fico values.
    Returns (bool, detail: str, matched_tier: dict|None).
    """
    tiers = [t for t in tier_parsed.get("tiers", []) if "min_fico" in t]
    if not tiers:
        return (None, f"no FICO tiers — use LLM judge", None)

    best = (False, f"no matching tier for FICO {fico}", None)
    best_min_f = 0
    for t in tiers:
        min_f = t["min_fico"]
        max_f = t.get("max_fico", 999)
        condition = t.get("condition")
        if condition == "else":
            if best[0] is False:
                best = ("possible", f"else tier (default)", t)
            continue
        if min_f <= fico <= max_f:
            ltv = t.get("max_ltv", "?")
            return (True, f"FICO {fico} meets ≥ {min_f} (LTV {ltv}%)", t)
        if min_f > fico and (best[0] is False or min_f < best_min_f or best_min_f == 0):
            ltv = t.get("max_ltv", "?")
            best = ("close", f"needs FICO {min_f} (has {fico}, LTV {ltv}%)", t)
            best_min_f = min_f

    return best


def judge_llm(question: str, context_text: str, format_hint: str = "brief answer") -> dict:
    """Query-time LLM judgment.

    In production, this would call an LLM API. In the CLI/openmode context,
    it prints the prompt for interactive input and caches the result.
    """
    cache = load_cache()
    key = f"judge::{hash(question + context_text)}"
    if key in cache:
        return cache[key]

    print(f"\n[LLM Judge Needed]")
    print(f"  Question: {question}")
    print(f"  Context: {context_text[:300]}")
    resp = input("  >> ").strip()

    result = {"answer": resp, "confidence": "low", "reasoning": "interactive"}
    cache[key] = result
    save_cache(cache)
    return result

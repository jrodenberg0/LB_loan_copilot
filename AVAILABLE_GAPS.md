# Available Gaps — Not Yet Built

## Parsing Gaps

### P1 — Duplex/triplex → 2-4 unit filtering
| Component | Impact |
|-----------|--------|
| What: "duplex," "triplex," "2-flat," "3-flat" not parsed as structured criteria. Engine routes to fix_and_flip or sfr_dscr but doesn't leverage `2_4_units` attribute (25 lenders have it) for filtering/scoring |
| Effort: ~20 min. Add regex patterns to `parse_criteria()` → `criteria["units"]`. Add unit-type check to scoring loop. |
| Value: Medium. Prevents showing SFR-only lenders for multi-unit properties. |

### P2 — DSCR value not extracted
| Component | Impact |
|-----------|--------|
| What: "1.2 DSCR," "0.75 DSCR" common in queries. Parser extracts FICO, loan amount, city, state — but not DSCR. Engine has 76 `dscr_range` records with rich data. |
| Effort: ~30 min. Add `r'(\d+\.?\d*)\s*dscr'` regex. Add DSCR matching logic in scoring (similar to FICO tier matching). |
| Value: High. DSCR is a primary deal parameter. Currently invisible to engine. |

### P3 — Multiple products per query
| Component | Impact |
|-----------|--------|
| What: Borrower says "show me both DSCR and fix-and-flip for this." Engine picks one product. Can't compare products side-by-side. |
| Effort: ~1hr. Need multi-product query mode in engine + agent tool. |
| Value: Low-Medium. Common ask but workaround exists (two queries). |

## Tool Gaps

### T1 — "Best rates" comparison
| Component | Impact |
|-----------|--------|
| What: No tool answers "who has the best rates for 720 FICO 75% LTV DSCR?" `estimate_pricing` works per-lender but there's no aggregate rank-by-rate. |
| Effort: ~1hr. New tool `best_rates(product, fico, ltv)` that iterates all lenders, calls `estimate_pricing`, returns sorted. |
| Value: High. Direct answer to most common question. |

### T2 — City→state restriction inheritance
| Component | Impact |
|-----------|--------|
| What: city_map.json only maps suburbs → Baltimore. But "Memphis" should trigger TN state restrictions, "Portland" should trigger OR restrictions. |
| Effort: ~15 min. Add city→state lookup table. Inject state into criteria when city is found. |
| Value: Low-Medium. State restrictions exist but rarely triggered because queries usually include state name. |

## Update Gap

### U1 — LLM cache staleness undetected
| Component | Impact |
|-----------|--------|
| What: If Excel updates and corpus is re-parsed without rebuilding `llm_cache.json`, FICO/LTV tier lookups use stale LLM-parsed data. No warning. |
| Effort: ~30 min. Stamp corpus.json with a hash of llm_cache.json. Check on load. Warn if mismatch. |
| Value: Medium. Silent incorrectness is dangerous. Currently manual rebuild needed. |

## Summary

**Build next (high value, low effort):** P2 (DSCR extraction) + T1 (best_rates tool) + P1 (unit-type parsing)

**Skip for now:** P3 (multi-product — workaround easy), T2 (rarely triggered), U1 (manual rebuild acceptable for now)

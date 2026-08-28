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

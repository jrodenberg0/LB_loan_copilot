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

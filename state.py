"""Conversation state for query sessions.

Persists last query, results, and refinement context between CLI calls.
"""

import json, os, time
from pathlib import Path

STATE_DIR = Path.home() / ".credit-box"
STATE_PATH = STATE_DIR / "state.json"


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {"version": 1, "history": [], "context": {}}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def push_query(query_text, result):
    """Save query + result to state history."""
    state = load_state()
    state["last_query"] = query_text
    state["last_result"] = result
    state["context"] = {
        "product": result.get("product"),
        "criteria": result.get("criteria"),
        "matches": [{"lender": m["lender"], "score": m["score"]} for m in result.get("matches", [])],
    }
    state["history"].append({
        "query": query_text,
        "timestamp": time.time(),
        "n_matches": len(result.get("matches", [])),
    })
    # Keep last 20
    state["history"] = state["history"][-20:]
    save_state(state)


def refine_query(prompt):
    """Interpret a refinement prompt against last context.
    
    Returns the new query text to run.
    """
    state = load_state()
    last = state.get("last_query", "")
    context = state.get("context", {})

    prompt = prompt.strip()

    # Commands
    if prompt.startswith("not ") or prompt.startswith("!not ") or prompt.startswith("exclude "):
        lender = prompt.split(" ", 1)[1].strip()
        # Avoid duplicate exclusion
        if f"exclude {lender}" in last.lower() or f"excluding {lender}" in last.lower():
            return last
        return f"{last} exclude {lender}"

    if prompt.startswith("show ") or prompt.startswith("!show "):
        idx = prompt.split(" ", 1)[1].strip()
        try:
            n = int(idx.split()[0])
        except ValueError:
            n = 1
        matches = state.get("last_result", {}).get("matches", [])
        if 1 <= n <= len(matches):
            lender = matches[n - 1]["lender"]
            return f"--show-lender {lender}"
        return last

    if prompt.startswith("filter ") or prompt.startswith("!filter "):
        # filter <attr> <op> <val> 
        parts = prompt.split(" ", 2)
        if len(parts) >= 3:
            filter_text = parts[2].strip()
            return f"{last} {filter_text}"
        return last

    if prompt.startswith("compare ") or prompt.startswith("!compare "):
        parts = prompt.split(" ", 2)
        if len(parts) >= 3:
            idx1, idx2 = parts[1], parts[2].strip()
            matches = state.get("last_result", {}).get("matches", [])
            try:
                n1 = int(idx1) - 1
                n2 = int(idx2) - 1
                if 0 <= n1 < len(matches) and 0 <= n2 < len(matches):
                    l1 = matches[n1]["lender"]
                    l2 = matches[n2]["lender"]
                    return f"--compare {l1} {l2}"
            except ValueError:
                pass
        return f"--compare {parts[1:]}"

    if prompt.startswith("!what") or prompt.startswith("what about"):
        # Ask about a specific attribute or lender in context
        return f"{prompt} (in context of: {last})"

    # Natural language refinement — append to last query for re-query
    return f"{last} {prompt}"


def list_history():
    """Show recent query history."""
    state = load_state()
    history = state.get("history", [])
    if not history:
        return "No prior queries."
    lines = []
    for i, h in enumerate(history[-10:], 1):
        lines.append(f"  {i}. [{h['n_matches']} matches] {h['query'][:60]}")
    return "\n".join(lines)


def clear_state():
    """Reset state."""
    save_state({"version": 1, "history": [], "context": {}})

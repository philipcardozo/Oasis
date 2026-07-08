"""Graph-aware comparables (prompt 11): peer set = 1-hop same-type graph neighbors
∪ same-group members (graph neighbors ranked first, capped), each valued from SEC
company facts. Reuses dcf_export's extraction — TAGS imported, never duplicated.

Facts are fetched on demand via dcf_export.load_facts (SEC), so a real call touches
the network; max_attempts bounds how many peers it will pull.
"""
from __future__ import annotations

import json
from functools import lru_cache

from dcf_export import DATA, TAGS, get_latest_filed_annual, load_facts, load_node

UNIVERSE = DATA / "universe.json"


def _latest(series: dict) -> float | None:
    return series[max(series)] if series else None


@lru_cache(maxsize=1)
def _graph(_mtime: float):
    d = json.loads(UNIVERSE.read_text("utf-8"))
    return {n["id"]: n for n in d["nodes"]}, d.get("links", [])


def _peer_metrics(p: dict) -> dict | None:
    if not str(p.get("cik") or "").strip().isdigit():
        return None
    try:
        facts, _ = load_facts(p)
    except Exception:
        return None
    rev = _latest(get_latest_filed_annual(facts, TAGS["revenue"]))
    ebit = _latest(get_latest_filed_annual(facts, TAGS["ebit"]))
    shares = _latest(get_latest_filed_annual(facts, TAGS["shares"]))
    price = (p.get("price") or {}).get("price")
    if not (rev and ebit and shares and price):
        return None
    cash = _latest(get_latest_filed_annual(facts, TAGS["cash"])) or 0.0
    debt = _latest(get_latest_filed_annual(facts, TAGS["debt"])) or 0.0
    pretax = _latest(get_latest_filed_annual(facts, TAGS["pretax"]))
    tax = _latest(get_latest_filed_annual(facts, TAGS["tax"]))
    mcap = price * shares
    ev = mcap + debt - cash
    ni = (pretax - tax) if (pretax is not None and tax is not None) else None
    return {
        "revenue": rev, "ebit_margin": ebit / rev,
        "ev_ebit": ev / ebit if ebit > 0 else None,
        "pe": mcap / ni if (ni and ni > 0) else None, "market_cap": mcap,
    }


def comps(entity_id: str, cap: int = 12, max_attempts: int = 18) -> dict:
    try:
        node = load_node(entity_id)
    except ValueError as e:
        return {"available": False, "reason": str(e)}
    if not str(node.get("cik") or "").strip().isdigit():  # '—' placeholder / blank -> no facts
        return {"available": False, "reason": "no SEC CIK"}

    by_id, links = _graph(UNIVERSE.stat().st_mtime)
    nid, ntype, group = node["id"], node.get("node_type"), node.get("group")
    nbrs = set()
    for l in links:
        if l["from"] == nid:
            nbrs.add(l["to"])
        elif l["to"] == nid:
            nbrs.add(l["from"])
    graph_peers = [p for p in nbrs if p != nid and by_id.get(p) and by_id[p].get("node_type") == ntype]
    graph_set = set(graph_peers)
    group_peers = [n["id"] for n in by_id.values()
                   if n["id"] != nid and n["id"] not in graph_set and group and n.get("group") == group]

    rows, attempts = [], 0
    for pid in graph_peers + group_peers:  # graph neighbors ranked first
        if len(rows) >= cap or attempts >= max_attempts:
            break
        p = by_id[pid]
        if not p.get("cik"):
            continue
        attempts += 1
        m = _peer_metrics(p)
        if not m:
            continue
        rows.append({"id": pid, "name": p.get("n"), "ticker": p.get("t"),
                     "peer_source": "graph" if pid in graph_set else "sector", **m})
    if not rows:
        return {"available": False, "reason": "no peers with usable SEC facts"}
    return {"available": True, "entity_id": nid, "name": node.get("n"), "peers": rows}


if __name__ == "__main__":
    import sys
    print(json.dumps(comps(sys.argv[1] if len(sys.argv) > 1 else "NVDA", cap=5), indent=2))

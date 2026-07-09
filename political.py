"""Company political-exposure context (prompt 14): committee overlap + contract
context. Neutral framing — overlap and provenance only, never causal claims.

NOTE: disclosed per-issuer trades + POL_->company TRADED edges are not included —
that ticker-level data is unavailable (see refresh_pol_trades.py). This surfaces the
committee-relevance overlap and USAspending contract context that we do have.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import duckdb

from dcf_export import load_node

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "data" / "store"
DATA = ROOT / "graph" / "data"
LEGIS_SRC = "https://github.com/unitedstates/congress-legislators"


@lru_cache(maxsize=1)
def _committee_map() -> dict:
    return json.loads((DATA / "committee_policy_map.json").read_text("utf-8"))["map"]


@lru_cache(maxsize=1)
def _committee_stats() -> dict:
    """committee_id -> {name, members, filer_members} from the store."""
    p = STORE / "pol_members.parquet"
    if not p.exists():
        return {}
    con = duckdb.connect()
    filers = {r[0] for r in con.execute(
        f"select distinct politician_id from '{(STORE / 'pol_trades.parquet').as_posix()}' "
        f"where politician_id is not null").fetchall()} if (STORE / "pol_trades.parquet").exists() else set()
    stats: dict = {}
    for pid, committees in con.execute(f"select id, committees from '{p.as_posix()}'").fetchall():
        is_filer = pid in filers
        for c in json.loads(committees):
            e = stats.setdefault(c["id"], {"name": c["name"], "members": 0, "filer_members": 0})
            e["members"] += 1
            if is_filer:
                e["filer_members"] += 1
    return stats


@lru_cache(maxsize=1)
def _contracts_by_recipient() -> tuple[dict, str]:
    path = DATA / "gov_contracts.json"
    if not path.exists():
        return {}, ""
    gc = json.loads(path.read_text("utf-8"))
    by_to: dict = {}
    for l in gc.get("links", []):
        by_to.setdefault(l["to"], []).append(l)
    return by_to, str(gc.get("fiscal_year", ""))


def political_context(entity_id: str) -> dict:
    try:
        node = load_node(entity_id)
    except Exception:
        return {"available": False, "reason": "unknown entity"}
    group = node.get("group")
    stats = _committee_stats()
    committees = []
    for cid, groups in _committee_map().items():
        if group in groups and cid in stats:
            s = stats[cid]
            committees.append({"id": cid, "name": s["name"], "members": s["members"],
                               "filer_members": s["filer_members"], "source_url": LEGIS_SRC})
    committees.sort(key=lambda c: -c["members"])

    by_to, fy = _contracts_by_recipient()
    contracts = [{"agency": l.get("from"), "obligations_bn": l.get("val"), "detail": l.get("detail"),
                  "source_url": l.get("source_url"), "fiscal_year": fy} for l in by_to.get(node["id"], [])]

    if not committees and not contracts:
        return {"available": False, "reason": "no committee overlap or federal contracts"}
    return {"available": True, "entity_id": node["id"], "name": node.get("n"), "group": group,
            "committees": committees, "contracts": contracts}


if __name__ == "__main__":
    import sys
    print(json.dumps(political_context(sys.argv[1] if len(sys.argv) > 1 else "LMT"), indent=2))

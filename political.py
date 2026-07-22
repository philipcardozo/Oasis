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

from dcf_export import load_node

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "data" / "store"
DATA = ROOT / "graph" / "data"
LEGIS_SRC = "https://github.com/unitedstates/congress-legislators"


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0


def committee_map() -> dict:
    return _committee_map(_mtime(DATA / "committee_policy_map.json"))


@lru_cache(maxsize=1)
def _committee_map(mtime: float) -> dict:
    return json.loads((DATA / "committee_policy_map.json").read_text("utf-8"))["map"]


def committee_stats() -> dict:
    return _committee_stats(_mtime(STORE / "pol_members.parquet"), _mtime(STORE / "pol_trades.parquet"))


@lru_cache(maxsize=1)
def _committee_stats(members_mtime: float, trades_mtime: float) -> dict:
    """committee_id -> {name, members, filer_members} from the store."""
    p = STORE / "pol_members.parquet"
    if not p.exists():
        return {}
    import duckdb

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


def contracts_by_recipient() -> tuple[dict, str]:
    return _contracts_by_recipient(_mtime(DATA / "gov_contracts.json"))


@lru_cache(maxsize=1)
def _contracts_by_recipient(mtime: float) -> tuple[dict, str]:
    path = DATA / "gov_contracts.json"
    if not path.exists():
        return {}, ""
    gc = json.loads(path.read_text("utf-8"))
    by_to: dict = {}
    for l in gc.get("links", []):
        by_to.setdefault(l["to"], []).append(l)
    return by_to, str(gc.get("fiscal_year", ""))


def intel_only_entity_ids() -> set[str]:
    return _intel_only_entity_ids(_mtime(DATA / "map_intelligence.json"), _mtime(DATA / "universe_core.json"))


@lru_cache(maxsize=1)
def _intel_only_entity_ids(intel_mtime: float, universe_mtime: float) -> set[str]:
    intel_path = DATA / "map_intelligence.json"
    universe_path = DATA / "universe_core.json"
    if not intel_path.exists() or not universe_path.exists():
        return set()
    intel = json.loads(intel_path.read_text("utf-8"))
    universe = json.loads(universe_path.read_text("utf-8"))
    graph_ids = {str(row.get("id", "")).upper() for row in universe.get("nodes", [])}
    return {
        str(row.get("id", "")).upper()
        for row in intel.get("entities", [])
        if row.get("id") and str(row.get("id")).upper() not in graph_ids
    }


def political_context(entity_id: str) -> dict:
    if entity_id.upper() in intel_only_entity_ids():
        return {"available": False, "reason": "unknown entity"}
    try:
        node = load_node(entity_id)
    except Exception:
        return {"available": False, "reason": "unknown entity"}
    group = node.get("group")
    committees = []
    relevant_committees = [
        cid for cid, groups in committee_map().items()
        if group and group in groups
    ]
    if relevant_committees:
        stats = committee_stats()
        for cid in relevant_committees:
            if cid not in stats:
                continue
            s = stats[cid]
            committees.append({"id": cid, "name": s["name"], "members": s["members"],
                               "filer_members": s["filer_members"], "source_url": LEGIS_SRC})
    committees.sort(key=lambda c: -c["members"])

    by_to, fy = contracts_by_recipient()
    contracts = [{"agency": l.get("from"), "obligations_bn": l.get("val"), "detail": l.get("detail"),
                  "source_url": l.get("source_url"), "fiscal_year": fy} for l in by_to.get(node["id"], [])]

    if not committees and not contracts:
        return {"available": False, "reason": "no committee overlap or federal contracts"}
    return {"available": True, "entity_id": node["id"], "name": node.get("n"), "group": group,
            "committees": committees, "contracts": contracts}


if __name__ == "__main__":
    import sys
    print(json.dumps(political_context(sys.argv[1] if len(sys.argv) > 1 else "LMT"), indent=2))

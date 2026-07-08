"""Prompt 13: schema + provenance checks for the political-exposure tables."""
import json
import re
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent


def _need(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} not built (run refresh_politicians.py / refresh_pol_trades.py)")
    return p.as_posix()


def test_pol_members_schema() -> None:
    path = _need("data/store/pol_members.parquet")
    rows = duckdb.execute(f"select id, node_type, name, chamber, committees from '{path}'").fetchall()
    assert len(rows) >= 500
    for pid, ntype, name, chamber, committees in rows:
        assert re.fullmatch(r"POL_[A-Z]\d+", pid), pid           # ID scheme POL_<bioguide>
        assert ntype == "person" and name and chamber in ("House", "Senate")
        json.loads(committees)  # committees column is valid JSON


def test_pol_trades_provenance() -> None:
    path = _need("data/store/pol_trades.parquet")
    con = duckdb.connect()
    # Every filing row must carry a source_url and a disclosure date (the guardrail:
    # no political row without provenance).
    bad = con.execute(f"select count(*) from '{path}' where coalesce(source_url,'')='' "
                      f"or coalesce(disclosure_date,'')=''").fetchone()[0]
    assert bad == 0
    ids = con.execute(f"select distinct politician_id from '{path}' where politician_id is not null").fetchall()
    assert ids and all(i[0].startswith("POL_") for i in ids)


def test_committee_policy_map_valid() -> None:
    cmap = json.loads((ROOT / "graph/data/committee_policy_map.json").read_text())["map"]
    uni = json.loads((ROOT / "graph/data/universe.json").read_text())
    groups = {n.get("group") for n in uni["nodes"]}
    assert len(cmap) >= 15
    for cid, gs in cmap.items():
        for g in gs:
            assert g in groups, f"committee {cid} -> unknown group '{g}'"


def test_political_context_company() -> None:
    # Prompt 14: defense contractor -> committee overlap + contract context, all sourced.
    _need("data/store/pol_members.parquet")
    _need("graph/data/gov_contracts.json")
    from political import political_context
    d = political_context("LMT")
    assert d["available"], d
    assert d["committees"] and all(c["source_url"].startswith("http") and c["members"] > 0 for c in d["committees"])
    assert d["contracts"] and all(c["source_url"].startswith("http") for c in d["contracts"])


def test_political_wording_neutral() -> None:
    # No loaded/accusatory terms in the political module, map, or the drawer block.
    main = (ROOT / "graph/js/main.js").read_text()
    block = main[main.index("function politicalBlock"):main.index("function companyAssetsBlock")]
    corpus = ((ROOT / "political.py").read_text() + (ROOT / "graph/data/committee_policy_map.json").read_text() + block).lower()
    for term in ("insider", "corrupt", "suspicious"):
        assert term not in corpus, term


if __name__ == "__main__":
    test_pol_members_schema()
    test_pol_trades_provenance()
    test_committee_policy_map_valid()
    test_political_context_company()
    test_political_wording_neutral()
    print("political ok")

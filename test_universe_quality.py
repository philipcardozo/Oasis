import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_lei_quality() -> None:
    universe_path = ROOT / "graph" / "data" / "universe.json"
    if not universe_path.exists():
        pytest.skip("universe.json does not exist")
        
    data = json.loads(universe_path.read_text("utf-8"))
    nodes = data.get("nodes", [])
    
    # Genuine CIK-holding nodes
    cik_nodes = [
        n for n in nodes
        if n.get("kind") in ("public", "security") and n.get("cik") and n["cik"] != "—"
    ]
    assert len(cik_nodes) > 0, "No public nodes with CIK found"
    
    # Spot-checks
    nvda = [n for n in cik_nodes if n.get("t") == "NVDA"]
    aapl = [n for n in cik_nodes if n.get("t") == "AAPL"]
    
    assert nvda, "NVDA not found in public nodes"
    assert aapl, "AAPL not found in public nodes"
    
    assert nvda[0].get("lei") == "549300S4KLFTLO7GSQ80", f"NVDA LEI wrong: {nvda[0].get('lei')}"
    assert aapl[0].get("lei") == "HWUPKR0MPOU8FGXBT394", f"AAPL LEI wrong: {aapl[0].get('lei')}"
    
    # LEI structure verification (all set LEIs must be exactly 20 chars)
    for n in nodes:
        lei = n.get("lei")
        if lei:
            assert len(lei) == 20, f"Node {n.get('id')} has invalid LEI length: {lei}"
            
    # Verify entity_model replication
    for n in nodes:
        lei = n.get("lei")
        if lei:
            em = n.get("entity_model")
            assert isinstance(em, dict), f"Node {n.get('id')} has no entity_model"
            assert em.get("lei") == lei, f"Node {n.get('id')} entity_model LEI mismatch"
            
    # Coverage verification (at least 35% of all CIK nodes have LEI)
    ratio = sum(1 for n in cik_nodes if n.get("lei")) / len(cik_nodes)
    print(f"LEI/CIK Coverage ratio: {ratio:.2%}")
    assert ratio >= 0.35, f"LEI coverage ratio too low: {ratio:.2%}"


def test_hq_address_quality() -> None:
    universe_path = ROOT / "graph" / "data" / "universe.json"
    if not universe_path.exists():
        pytest.skip("universe.json does not exist")
        
    data = json.loads(universe_path.read_text("utf-8"))
    nodes = data.get("nodes", [])
    
    placeholders = {"NYSE", "Nasdaq", "NYSE American", "NYSE Arca", "OTC", "Cboe BZX", "CBOE", "—", "", "-", "N/A"}
    
    # Assert exchange-placeholder HQ count == 0 in rebuilt universe.json
    placeholder_nodes = [
        n for n in nodes
        if str(n.get("hq") or "").strip() in placeholders
    ]
    assert len(placeholder_nodes) == 0, f"Found {len(placeholder_nodes)} nodes with exchange placeholder HQs"
    
    # Assert city-level located entities > 10,000
    located_nodes = [
        n for n in nodes
        if n.get("hq") and n["hq"] != "Unknown"
    ]
    print(f"Total located entities: {len(located_nodes)}")
    assert len(located_nodes) > 10000, f"Too few located entities: {len(located_nodes)}"
    
    # Assert NVDA details
    nvda = [n for n in nodes if n.get("t") == "NVDA"][0]
    assert "Santa Clara" in nvda.get("hq", ""), f"NVDA HQ wrong: {nvda.get('hq')}"
    
    em = nvda.get("entity_model")
    assert isinstance(em, dict), "NVDA has no entity_model"
    assert em.get("location", {}).get("country") == "US", f"NVDA country wrong: {em.get('location', {}).get('country')}"
    assert em.get("location", {}).get("confidence") >= 0.9, f"NVDA location confidence too low: {em.get('location', {}).get('confidence')}"


def test_universe_split_counts() -> None:
    universe_path = ROOT / "graph" / "data" / "universe.json"
    core_path = ROOT / "graph" / "data" / "universe_core.json"
    bulk_path = ROOT / "graph" / "data" / "universe_bulk.json"
    
    if not universe_path.exists() or not core_path.exists() or not bulk_path.exists():
        pytest.skip("Universe files not fully built")
        
    u = json.loads(universe_path.read_text("utf-8"))
    c = json.loads(core_path.read_text("utf-8"))
    b = json.loads(bulk_path.read_text("utf-8"))
    
    assert len(c["nodes"]) + len(b["nodes"]) == len(u["nodes"]), "universe split node count mismatch"


def test_link_attributes() -> None:
    universe_path = ROOT / "graph" / "data" / "universe.json"
    if not universe_path.exists():
        pytest.skip("universe.json not found")
        
    data = json.loads(universe_path.read_text("utf-8"))
    links = data.get("links", [])
    
    for l in links:
        assert l.get("from"), "Link has no from node"
        assert l.get("to"), "Link has no to node"
        assert l.get("rel"), "Link has no rel"
        assert l.get("source_url") and l["source_url"].startswith("http"), f"Link {l} missing source_url or invalid URL"
        assert l.get("as_of"), f"Link {l} missing as_of date"


def test_no_duplicate_canonical_ids() -> None:
    universe_path = ROOT / "graph" / "data" / "universe.json"
    if not universe_path.exists():
        pytest.skip("universe.json not found")
        
    data = json.loads(universe_path.read_text("utf-8"))
    seen = {}
    collisions = {}
    for node in data["nodes"]:
        cid = node.get("canonical_id")
        assert cid
        if cid in seen:
            collisions.setdefault(cid, [seen[cid]]).append(node["id"])
        seen[cid] = node["id"]
    assert not collisions, f"Duplicate canonical IDs found: {collisions}"


def test_main() -> None:
    test_lei_quality()
    test_hq_address_quality()
    test_universe_split_counts()
    test_link_attributes()
    test_no_duplicate_canonical_ids()
    print("All quality checks (LEI, HQ, split, links, canonical IDs) passed successfully!")


if __name__ == "__main__":
    test_main()

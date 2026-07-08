"""Prompt 11: graph-aware comps returns >=3 peers for NVDA (fetches SEC facts)."""
from comps import comps


def test_comps_nvda_has_peers() -> None:
    r = comps("NVDA", cap=6, max_attempts=10)  # bounded so the test pulls only a few peers
    assert r["available"], r
    assert len(r["peers"]) >= 3, r
    p = r["peers"][0]
    assert p["peer_source"] in ("graph", "sector")
    assert p["ebit_margin"] is not None and p["revenue"] > 0


def test_comps_no_cik_degrades() -> None:
    assert comps("PVT_OPENAI") == {"available": False, "reason": "no SEC CIK"}


if __name__ == "__main__":
    test_comps_nvda_has_peers()
    test_comps_no_cik_degrades()
    print("comps ok")

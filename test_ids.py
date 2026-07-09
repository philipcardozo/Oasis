from expand_us import resolve_id
from store import aliases, load_nodes


def test_main() -> None:
    nodes = load_nodes()
    alias_map = aliases()
    seen = {}
    collisions = {}
    for node in nodes:
        cid = node.get("canonical_id")
        assert cid
        if node.get("kind") in {"public", "security"}:
            assert node["id"] == cid
        if cid in seen:
            collisions.setdefault(cid, [seen[cid]]).append(node["id"])
        seen[cid] = node["id"]
    assert not collisions
    assert alias_map["XETR:NVD"] == "NVDA"
    assert resolve_id("XETR:NVD") == "NVDA"
    assert not (set(alias_map.values()) - set(seen))
    print("canonical_id collisions: 0")


if __name__ == "__main__":
    test_main()

import json

from expand_us import resolve_id


def main() -> None:
    data = json.load(open("graph/data/universe.json"))
    aliases = json.load(open("graph/data/aliases.json"))
    seen = {}
    collisions = {}
    for node in data["nodes"]:
        cid = node.get("canonical_id")
        assert cid
        if node.get("kind") in {"public", "security"}:
            assert node["id"] == cid
        if cid in seen:
            collisions.setdefault(cid, [seen[cid]]).append(node["id"])
        seen[cid] = node["id"]
    assert not collisions
    assert aliases["XETR:NVD"] == "NVDA"
    assert resolve_id("XETR:NVD") == "NVDA"
    assert not (set(aliases.values()) - set(seen))
    print("canonical_id collisions: 0")


if __name__ == "__main__":
    main()

from store import load_edges, load_nodes


def test_main() -> None:
    nodes = {n["id"]: n for n in load_nodes()}
    securities = [n for n in nodes.values() if n.get("kind") == "security"]
    assert securities, "expected security nodes in canonical universe"

    for node in nodes.values():
        assert node.get("node_type") in {"company", "security", "fund", "warrant", "counterparty"}
        assert isinstance(node.get("entity_model"), dict)
        assert 0 <= float(node.get("source_confidence", -1)) <= 1
        assert 0 <= float(node.get("location_confidence", -1)) <= 1

    for node in securities:
        assert node.get("node_type") != "company"
        assert node.get("security_type")
        assert node.get("security_type_group")

    issuer_edges = [l for l in load_edges() if l["rel"] == "same_issuer"]
    for edge in issuer_edges:
        left, right = nodes[edge["from"]], nodes[edge["to"]]
        assert {left.get("kind"), right.get("kind")} <= {"public", "security"}
        assert "security" in {left.get("kind"), right.get("kind")}

    print(f"entity model ok: {len(nodes)} nodes, {len(securities)} securities")


if __name__ == "__main__":
    test_main()

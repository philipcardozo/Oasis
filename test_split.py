from expand_us import split_graph


def main() -> None:
    graph = {
        "meta": {"built_at": "2026-01-01", "companies": 2},
        "nodes": [{"id": "A", "deg": 1}, {"id": "B", "deg": 0}],
        "links": [{"from": "A", "to": "C"}],
    }
    core, bulk = split_graph(graph)
    assert [n["id"] for n in core["nodes"]] == ["A"]
    assert [n["id"] for n in bulk["nodes"]] == ["B"]
    assert len(core["nodes"]) + len(bulk["nodes"]) == len(graph["nodes"])
    assert core["links"] == graph["links"]


if __name__ == "__main__":
    main()

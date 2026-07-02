from refresh_edge_candidates import infer_rel, make_candidates, name_hit
from expand_us import has_edge_evidence


def main() -> None:
    graph = {
        "nodes": [
            {"id": "MSFT", "n": "Microsoft Corporation", "t": "MSFT", "deg": 1},
            {"id": "NVDA", "n": "NVIDIA CORP", "t": "NVDA", "deg": 1},
        ],
        "links": [],
    }
    news = {"items_by_node": {"MSFT": [{"title": "Microsoft partners with NVIDIA on AI infrastructure", "url": "https://example.com/a", "source": "Example", "published": "2026-01-01"}]}}
    assert infer_rel("Company wins contract award") == "contracts"
    candidates = make_candidates(graph, news, [], [])
    assert len(candidates) == 1
    assert candidates[0]["from"] == "MSFT"
    assert candidates[0]["to"] == "NVDA"
    assert candidates[0]["rel"] == "partners"
    assert candidates[0]["status"] == "candidate"
    assert has_edge_evidence({**candidates[0], "status": "confirmed"})
    assert not has_edge_evidence({**candidates[0], "source_url": ""})
    assert not name_hit("NASA announces public-private partnership", {"n": "OpenAI", "t": "private"})


if __name__ == "__main__":
    main()

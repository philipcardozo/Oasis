import json
from pathlib import Path


DATA = Path("graph/data")


def load(name):
    return json.load((DATA / name).open())


def test_main() -> None:
    companies = load("companies.geojson")
    securities = load("securities.geojson")
    relationships = load("relationships.geojson")
    graph_index = load("graph-index.json")
    unknown = load("location_unknown.json")

    assert companies["features"], "expected company map features"
    assert securities["features"], "expected security map features"
    assert unknown, "expected unknown-location queue"

    plotted = {}
    for feature in companies["features"] + securities["features"]:
        coords = feature["geometry"]["coordinates"]
        props = feature["properties"]
        assert coords != [0, 0], feature["id"]
        assert props["location_quality"] in {"exact_hq", "country_centroid"}
        plotted[props["id"]] = feature

    assert all(f["properties"]["entity_type"] == "Security" for f in securities["features"])
    assert all(f["properties"]["entity_type"] != "Security" for f in companies["features"])
    if {"JPM", "PFE"} <= set(plotted):
        assert plotted["JPM"]["geometry"]["coordinates"] != plotted["PFE"]["geometry"]["coordinates"]
        assert plotted["JPM"]["properties"]["source_lat"] == plotted["PFE"]["properties"]["source_lat"]
        assert plotted["JPM"]["properties"]["location_offset"] == "same_coordinate_jitter"

    edge_ids = set()
    for feature in relationships["features"]:
        props = feature["properties"]
        edge_ids.add(props["id"])
        assert props["from"] in plotted
        assert props["to"] in plotted

    for node_id, focus in graph_index.items():
        assert node_id in plotted
        assert set(focus["edges"]) <= edge_ids

    print(f"map geojson ok: {len(companies['features'])} companies, {len(securities['features'])} securities, {len(relationships['features'])} relationships")


if __name__ == "__main__":
    test_main()

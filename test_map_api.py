from map_api import map_entities, map_relationships, neighborhood, parse_bbox


def main() -> None:
    bbox = parse_bbox({"bbox": ["-180,-90,180,90"]})
    entities = map_entities(bbox)
    relationships = map_relationships(bbox)
    assert entities["features"]
    assert relationships["features"]

    node_id = entities["features"][0]["properties"]["id"]
    focus = neighborhood(node_id, 1)
    assert focus["center"]["id"] == node_id
    assert focus["nodes"]
    assert "risk_summary" in focus
    print(f"map api ok: {len(entities['features'])} entities, {len(relationships['features'])} relationships")


if __name__ == "__main__":
    main()

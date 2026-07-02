from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).parent
DATA = ROOT / "graph" / "data"
OVERRIDES = DATA / "location_overrides.json"


def load_json(name: str, fallback):
    path = DATA / name
    return json.load(path.open()) if path.exists() else fallback


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def in_bbox(coords: list[float], bbox: list[float] | None) -> bool:
    if not bbox:
        return True
    lng, lat = coords
    return bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]


def parse_bbox(query: dict) -> list[float] | None:
    raw = (query.get("bbox") or [""])[0]
    if not raw:
        return None
    nums = [float(x) for x in raw.split(",")]
    if len(nums) != 4:
        raise ValueError("bbox must be minLng,minLat,maxLng,maxLat")
    return nums


def map_entities(bbox: list[float] | None = None) -> dict:
    features = []
    for name in ("companies.geojson", "securities.geojson"):
        features.extend(load_json(name, feature_collection([]))["features"])
    return feature_collection([f for f in features if in_bbox(f["geometry"]["coordinates"], bbox)])


def map_relationships(bbox: list[float] | None = None) -> dict:
    features = load_json("relationships.geojson", feature_collection([]))["features"]
    if bbox:
        features = [f for f in features if any(in_bbox(c, bbox) for c in f["geometry"]["coordinates"])]
    return feature_collection(features)


def universe_nodes() -> dict[str, dict]:
    return {n["id"]: n for n in load_json("universe.json", {"nodes": []})["nodes"]}


def risk_summary(entity_id: str, node_ids: set[str]) -> dict:
    nodes = universe_nodes()
    countries = sorted({nodes[i].get("country") for i in node_ids if nodes.get(i, {}).get("country")})
    confidences = [float(nodes[i].get("source_confidence", 0.5)) for i in node_ids if i in nodes]
    return {
        "supplier_concentration": "unknown",
        "country_exposure": countries,
        "data_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0,
    }


def neighborhood(entity_id: str, depth: int = 1) -> dict:
    index = load_json("graph-index.json", {})
    nodes = universe_nodes()
    edge_features = {f["properties"]["id"]: f for f in map_relationships()["features"]}
    seen_nodes, seen_edges, frontier = {entity_id}, set(), {entity_id}
    for _ in range(max(1, min(depth, 2))):
        next_frontier = set()
        for node_id in frontier:
            focus = index.get(node_id, {})
            next_frontier.update(focus.get("neighbors", []))
            seen_edges.update(focus.get("edges", []))
        next_frontier -= seen_nodes
        seen_nodes |= next_frontier
        frontier = next_frontier
    return {
        "center": {"id": entity_id, "name": nodes.get(entity_id, {}).get("n", entity_id)},
        "nodes": [nodes[i] for i in sorted(seen_nodes) if i in nodes],
        "edges": [edge_features[i] for i in sorted(seen_edges) if i in edge_features],
        "risk_summary": risk_summary(entity_id, seen_nodes),
    }


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def json_response(self, data, status: int = 200):
        raw = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/api/map/entities.geojson":
                return self.json_response(map_entities(parse_bbox(query)))
            if url.path == "/api/map/relationships.geojson":
                return self.json_response(map_relationships(parse_bbox(query)))
            if url.path == "/api/location/unknown":
                return self.json_response(load_json("location_unknown.json", []))
            if url.path.startswith("/api/entity/"):
                parts = [unquote(p) for p in url.path.split("/") if p]
                entity_id = parts[2] if len(parts) >= 3 else ""
                if len(parts) == 3:
                    node = universe_nodes().get(entity_id)
                    return self.json_response(node or {"error": "not found"}, 200 if node else 404)
                if len(parts) == 4 and parts[3] == "neighborhood":
                    return self.json_response(neighborhood(entity_id, int((query.get("depth") or ["1"])[0])))
                if len(parts) == 4 and parts[3] == "risk":
                    focus = load_json("graph-index.json", {}).get(entity_id, {})
                    return self.json_response(risk_summary(entity_id, {entity_id, *focus.get("neighbors", [])}))
        except Exception as exc:
            return self.json_response({"error": str(exc)}, 400)
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/location/override":
            return self.json_response({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not payload.get("id") or not isinstance(payload.get("lat"), (int, float)) or not isinstance(payload.get("lng"), (int, float)):
            return self.json_response({"error": "id, lat, lng required"}, 400)
        rows = load_json(OVERRIDES.name, {})
        rows[payload["id"]] = payload
        OVERRIDES.write_text(json.dumps(rows, indent=2) + "\n")
        self.json_response({"ok": True, "id": payload["id"]})


def main() -> None:
    ThreadingHTTPServer(("127.0.0.1", 8788), Handler).serve_forever()


if __name__ == "__main__":
    main()

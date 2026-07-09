from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "graph" / "data"
UNIVERSE = DATA / "universe.json"
HQ_COORDS = DATA / "hq_coords.json"
COMPANIES_GEO = DATA / "companies.geojson"
SECURITIES_GEO = DATA / "securities.geojson"
RELATIONSHIPS_GEO = DATA / "relationships.geojson"
GRAPH_INDEX = DATA / "graph-index.json"
LOCATION_UNKNOWN = DATA / "location_unknown.json"

BAD_HQ_VALUES = {"nasdaq", "nyse", "otc", "cboe", "-", "—", "none", "null", "n/a", "na", ""}
COUNTRY_CODES = {
    "AE": "United Arab Emirates", "CA": "Canada", "CH": "Switzerland", "CN": "China", "DC": "United States",
    "ES": "Spain", "IL": "Israel", "PT": "Portugal", "SA": "Saudi Arabia", "UK": "United Kingdom",
    "US": "United States",
}
COUNTRY_COORDS = {
    "Argentina": [-38.4161, -63.6167], "Australia": [-25.2744, 133.7751], "Benin": [9.3077, 2.3158],
    "Bolivia": [-16.2902, -63.5887], "Brazil": [-14.235, -51.9253], "Burkina Faso": [12.2383, -1.5616],
    "Canada": [56.1304, -106.3468], "Cayman Islands": [19.3133, -81.2546], "Chile": [-35.6751, -71.543],
    "China": [35.8617, 104.1954], "Colombia": [4.5709, -74.2973], "Cote d'Ivoire": [7.54, -5.5471],
    "Ecuador": [-1.8312, -78.1834], "Ghana": [7.9465, -1.0232], "Guyana": [4.8604, -58.9302],
    "Germany": [51.1657, 10.4515], "Sweden": [60.1282, 18.6435], "France": [46.2276, 2.2137],
    "Finland": [61.9241, 25.7482], "Denmark": [56.2639, 9.5018], "Liechtenstein": [47.166, 9.5554],
    "Italy": [41.8719, 12.5674], "Cyprus": [35.1264, 33.4299], "Luxembourg": [49.8153, 6.1296],
    "Iceland": [64.9631, -19.0208], "Ireland": [53.4129, -8.2439], "Ukraine": [48.3794, 31.1656],
    "Georgia": [42.3154, 43.3569],
    "Indonesia": [-0.7893, 113.9213], "Israel": [31.0461, 34.8516], "Japan": [36.2048, 138.2529],
    "Kenya": [-0.0236, 37.9062], "Mali": [17.5707, -3.9962], "Morocco": [31.7917, -7.0926],
    "Netherlands": [52.1326, 5.2913], "New Zealand": [-40.9006, 174.886], "Niger": [17.6078, 8.0817],
    "Norway": [60.472, 8.4689], "Paraguay": [-23.4425, -58.4438], "Peru": [-9.19, -75.0152],
    "Portugal": [39.3999, -8.2245], "Saudi Arabia": [23.8859, 45.0792], "Senegal": [14.4974, -14.4524],
    "South Africa": [-30.5595, 22.9375], "South Korea": [35.9078, 127.7669], "Spain": [40.4637, -3.7492],
    "Suriname": [3.9193, -56.0278], "Switzerland": [46.8182, 8.2275], "Taiwan": [23.6978, 120.9605],
    "Togo": [8.6195, 0.8248], "United Arab Emirates": [23.4241, 53.8478],
    "United Kingdom": [55.3781, -3.436], "United States": [39.8283, -98.5795],
    "Uruguay": [-32.5228, -55.7658], "Venezuela": [6.4238, -66.5897],
}
RELATIONSHIP_LABELS = {
    "acquired": "ACQUIRED", "contracts": "CONTRACTS", "funds": "FINANCES", "government_action": "GOVERNMENT_ACTION",
    "owns": "OWNS", "partners": "PARTNERS_WITH", "same_issuer": "SAME_ISSUER", "supplies": "SUPPLIES",
}


def clean(text: object) -> str:
    return " ".join(str(text or "").replace("[", " ").replace("]", " ").split()).strip()


def key(text: object) -> str:
    normalized = unicodedata.normalize("NFKD", clean(text).lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.replace(".", "").replace(" ,", ",").strip()


def loc_country(node: dict, hq: str) -> str:
    if node.get("country"):
        return str(node["country"])
    last = clean(hq).split(",")[-1].strip().upper()
    return COUNTRY_CODES.get(last, "")


def coord_compatible(row: list, node: dict, hq: str) -> bool:
    country = key(loc_country(node, hq))
    hq_key = key(hq)
    region = key(row[3] if len(row) > 3 else "")
    row_country = key(row[4] if len(row) > 4 else "")
    if country and row_country:
        return country == row_country
    return bool((region and region in hq_key) or (row_country and row_country in hq_key) or "," not in hq_key)


def coord_row(node: dict, coords: dict) -> list | None:
    hq = clean(node.get("hq"))
    hq_key = key(hq)
    country = loc_country(node, hq)
    country_key = key(country)
    full_key = hq_key if country_key and hq_key.endswith(f", {country_key}") else f"{hq_key}, {country_key}".strip(", ")
    if full_key in coords:
        return coords[full_key]
    if hq_key in coords:
        return coords[hq_key]
    city = hq_key.split(",")[0]
    row = coords.get(city) if city != hq_key else None
    return row if row and coord_compatible(row, node, hq) else None


def jittered_country_point(node_id: str, country: str) -> tuple[float, float] | None:
    base = COUNTRY_COORDS.get(country)
    if not base:
        return None
    h = int(hashlib.sha1(node_id.encode("utf-8")).hexdigest()[:10], 16)
    angle = (h % 3600) / 3600 * math.tau
    radius = 0.18 + ((h // 3600) % 1000) / 1000 * 0.42
    return round(base[0] + math.sin(angle) * radius, 6), round(base[1] + math.cos(angle) * radius, 6)


def location_for(node: dict, coords: dict) -> dict | None:
    hq = clean(node.get("hq"))
    row = None if key(hq) in BAD_HQ_VALUES else coord_row(node, coords)
    if row:
        return {
            "lat": float(row[0]), "lng": float(row[1]), "city": row[2] if len(row) > 2 else hq.split(",")[0],
            "region": row[3] if len(row) > 3 else "", "country": row[4] if len(row) > 4 else loc_country(node, hq),
            "location_quality": "exact_hq", "location_source": row[5] if len(row) > 5 else "hq_coords",
            "location_confidence": float(row[6]) if len(row) > 6 else 0.9,
        }
    country = loc_country(node, hq)
    fallback_country = COUNTRY_CODES.get(country, country)
    fallback = jittered_country_point(node["id"], fallback_country)
    if fallback:
        return {
            "lat": fallback[0], "lng": fallback[1], "city": "", "region": "", "country": fallback_country,
            "location_quality": "country_centroid", "location_source": "country_fallback", "location_confidence": 0.35,
        }
    return None


def spread_duplicate_locations(rows: list[tuple[dict, dict]]) -> None:
    groups: dict[tuple[float, float], list[tuple[dict, dict]]] = {}
    for node, loc in rows:
        groups.setdefault((round(loc["lat"], 5), round(loc["lng"], 5)), []).append((node, loc))
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda item: str(item[0].get("id", "")))
        for i, (_node, loc) in enumerate(items):
            angle = i * math.pi * (3 - math.sqrt(5))
            radius = min(0.08, 0.006 * math.sqrt(i + 1))
            lat_rad = math.radians(loc["lat"])
            loc["source_lat"] = loc["lat"]
            loc["source_lng"] = loc["lng"]
            loc["lat"] = round(loc["lat"] + math.sin(angle) * radius, 6)
            loc["lng"] = round(loc["lng"] + math.cos(angle) * radius / max(abs(math.cos(lat_rad)), 0.25), 6)
            loc["location_offset"] = "same_coordinate_jitter"


def entity_type(node: dict) -> str:
    if node.get("kind") == "security":
        return "Security"
    if node.get("kind") == "government":
        return "Government"
    if node.get("kind") == "private":
        return "Private"
    if node.get("kind") == "legacy":
        return "Historical"
    return "Public"


def point_feature(node: dict, loc: dict) -> dict:
    return {
        "type": "Feature",
        "id": node["id"],
        "geometry": {"type": "Point", "coordinates": [loc["lng"], loc["lat"]]},
        "properties": {
            "id": node["id"], "name": node.get("n", ""), "ticker": node.get("t", ""),
            "entity_type": entity_type(node), "node_type": node.get("node_type", ""), "kind": node.get("kind", ""),
            "sector": node.get("sector", ""), "sector_key": node.get("sec", ""), "group": node.get("group", ""),
            "group_key": node.get("grp", ""), "degree": int(node.get("deg") or 0), "market_value": node.get("tot", 0),
            "country": loc["country"], "hq_city": loc["city"], "location_quality": loc["location_quality"],
            "location_source": loc["location_source"], "location_confidence": loc["location_confidence"],
            "location_offset": loc.get("location_offset", ""), "source_lat": loc.get("source_lat", loc["lat"]),
            "source_lng": loc.get("source_lng", loc["lng"]),
            "issuer_id": node.get("issuer_id", ""),
        },
    }


def write_map_geojson(graph: dict | None = None) -> None:
    graph = graph or json.load(UNIVERSE.open())
    coords = json.load(HQ_COORDS.open()) if HQ_COORDS.exists() else {}
    by_id = {n["id"]: n for n in graph["nodes"]}
    located: dict[str, dict] = {}
    companies, securities, unknown = [], [], []
    pending: list[tuple[dict, dict]] = []

    for node in graph["nodes"]:
        loc = location_for(node, coords)
        if not loc:
            unknown.append({k: node.get(k, "") for k in ("id", "n", "t", "kind", "node_type", "hq", "country")})
            continue
        pending.append((node, loc))

    spread_duplicate_locations(pending)
    for node, loc in pending:
        located[node["id"]] = loc
        feature = point_feature(node, loc)
        (securities if node.get("kind") == "security" else companies).append(feature)

    rel_features, graph_index = [], {node_id: {"neighbors": [], "edges": []} for node_id in located}
    for i, edge in enumerate(graph["links"]):
        a, b = edge.get("from"), edge.get("to")
        if a not in located or b not in located:
            continue
        edge_id = f"edge:{a}:{edge.get('rel')}:{b}:{i}"
        rel_features.append({
            "type": "Feature",
            "id": edge_id,
            "geometry": {
                "type": "LineString",
                "coordinates": [[located[a]["lng"], located[a]["lat"]], [located[b]["lng"], located[b]["lat"]]],
            },
            "properties": {
                "id": edge_id, "from": a, "to": b, "source": a, "target": b,
                "relationship": RELATIONSHIP_LABELS.get(edge.get("rel"), str(edge.get("rel", "")).upper()),
                "rel": edge.get("rel", ""), "confidence": edge.get("confidence", 0.5), "value_usd": edge.get("val"),
                "source_name": edge.get("src", ""), "as_of": edge.get("as_of", edge.get("start", "")),
                "start": edge.get("start", ""), "end": edge.get("end", ""),
            },
        })
        for left, right in ((a, b), (b, a)):
            if left in graph_index:
                graph_index[left]["neighbors"].append(right)
                graph_index[left]["edges"].append(edge_id)

    for path, features in ((COMPANIES_GEO, companies), (SECURITIES_GEO, securities), (RELATIONSHIPS_GEO, rel_features)):
        path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")) + "\n")
    GRAPH_INDEX.write_text(json.dumps(graph_index, separators=(",", ":")) + "\n")
    LOCATION_UNKNOWN.write_text(json.dumps(unknown, indent=2) + "\n")


def main() -> None:
    write_map_geojson()


if __name__ == "__main__":
    main()

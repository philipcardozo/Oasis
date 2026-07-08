from __future__ import annotations

import json
import csv
import re
import os
from contextlib import suppress
from datetime import date, datetime, timezone
from functools import lru_cache
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dcf_export import build_dcf_workbook
from data_sources import dem_tilejson, terrain_coverage_registry, validation_status

ROOT = Path(__file__).parent
DATA = ROOT / "graph" / "data"
INTEL = DATA / "map_intelligence.json"
OVERRIDES = DATA / "location_overrides.json"
VALUATION_ASSUMPTIONS = DATA / "valuation_assumptions.json"
USER_OVERRIDES = DATA / "user_overrides.json"
REPORTS_DIR = DATA / "reports"
RAW_DATA_ROOT = Path(os.environ.get("OASIS_RAW_DATA_ROOT", "/data/raw"))
RAW_FEEDS = {
    "usgs_3dep": {"source_layer": "relief_features", "default_layer": "relief-terrain"},
    "eia": {"source_layer": "industrial_assets", "default_layer": "industrial-energy"},
    "fbi_crime": {"source_layer": "relief_features", "default_layer": "relief-crime"},
}


app = FastAPI(title="Oasis Map Intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)


STATIC_JSON = {"companies.geojson", "securities.geojson", "relationships.geojson", "universe.json", "graph-index.json", "map_intelligence.json"}


@lru_cache(maxsize=16)
def _load_json_cached(path: str, mtime: float):
    return json.load(Path(path).open())


def load_static_json(path: str):
    """Load JSON with mtime-based cache invalidation."""
    p = Path(path)
    mtime = p.stat().st_mtime if p.exists() else 0
    return _load_json_cached(path, mtime)


def load_json(name: str | Path, fallback):
    path = name if isinstance(name, Path) else DATA / name
    if path.name in STATIC_JSON and path.exists():
        return load_static_json(str(path))
    return json.load(path.open()) if path.exists() else fallback



def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def raw_layer_type(feed: str, path: Path, row: dict | None = None) -> str:
    text = f"{path.stem} {(row or {}).get('name', '')} {(row or {}).get('title', '')} {(row or {}).get('type', '')}".lower()
    if feed == "usgs_3dep":
        if any(k in text for k in ("hillshade", "shade")):
            return "relief-hillshade"
        if any(k in text for k in ("mount", "slope")):
            return "relief-mountains"
        if any(k in text for k in ("water", "river", "hydro")):
            return "relief-water"
        if any(k in text for k in ("veg", "vegetation", "landcover", "cdl")):
            return "relief-vegetation"
        return "relief-terrain"
    if feed == "eia":
        if "substation" in text:
            return "industrial-substations"
        if any(k in text for k in ("transmission", "line", "grid")):
            return "industrial-transmission"
        if "hydro" in text:
            return "industrial-hydro"
        if any(k in text for k in ("plant", "power", "generation")):
            return "industrial-power-plants"
        return "industrial-energy"
    return "relief-crime"


def raw_point_from_row(row: dict) -> list[float] | None:
    lower = {str(k).lower(): v for k, v in row.items()}
    for lat_key, lng_key in (("latitude", "longitude"), ("lat", "lng"), ("lat", "lon"), ("y", "x")):
        lat = as_float(lower.get(lat_key))
        lng = as_float(lower.get(lng_key))
        if lat is not None and lng is not None:
            return [lng, lat]
    geom = row.get("geometry")
    if isinstance(geom, dict) and geom.get("type") == "Point":
        coords = geom.get("coordinates") or []
        if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
            return [float(coords[0]), float(coords[1])]
    if isinstance(geom, str):
        with suppress(Exception):
            parsed = json.loads(geom)
            if isinstance(parsed, dict) and parsed.get("type") == "Point":
                coords = parsed.get("coordinates") or []
                if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
                    return [float(coords[0]), float(coords[1])]
    return None


def raw_feature_from_row(feed: str, path: Path, row: dict, index: int) -> dict | None:
    geometry = row.get("geometry") if isinstance(row.get("geometry"), dict) else None
    if not geometry:
        point = raw_point_from_row(row)
        if point:
            geometry = {"type": "Point", "coordinates": point}
    if not geometry:
        return None
    props = {k: v for k, v in row.items() if k != "geometry"}
    layer = str(props.get("layer_type") or props.get("layer") or raw_layer_type(feed, path, row))
    props.update(
        {
            "id": props.get("id") or f"{feed}:{path.stem}:{index}",
            "name": props.get("name") or props.get("title") or props.get("facility_name") or path.stem,
            "layer": layer,
            "layer_type": layer,
            "source_layer": RAW_FEEDS[feed]["source_layer"],
            "kind": props.get("kind") or "layer_feature",
            "source": props.get("source") or feed,
            "confidence": as_float(props.get("confidence") or props.get("source_confidence")) or 0.5,
            "updated_at": props.get("updated_at") or props.get("as_of") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
        }
    )
    return {"type": "Feature", "id": props["id"], "geometry": geometry, "properties": props}


def raw_features_from_file(feed: str, path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    text = path.read_text(errors="ignore")
    rows: list[dict] = []
    if suffix in {".geojson", ".json"}:
        with suppress(Exception):
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
                rows = [f for f in payload.get("features", []) if isinstance(f, dict)]
            elif isinstance(payload, dict) and payload.get("type") == "Feature":
                rows = [payload]
            elif isinstance(payload, list):
                rows = [r for r in payload if isinstance(r, dict)]
            elif isinstance(payload, dict):
                rows = [payload]
    elif suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
        rows = list(reader)
    features: list[dict] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("type") == "Feature" and row.get("geometry"):
            feat = dict(row)
            props = dict(feat.get("properties") or {})
            layer = str(props.get("layer_type") or props.get("layer") or raw_layer_type(feed, path, props))
            props.update(
                {
                    "id": props.get("id") or f"{feed}:{path.stem}:{i}",
                    "name": props.get("name") or props.get("title") or path.stem,
                    "layer": layer,
                    "layer_type": layer,
                    "source_layer": RAW_FEEDS[feed]["source_layer"],
                    "kind": props.get("kind") or "layer_feature",
                    "source": props.get("source") or feed,
                    "confidence": as_float(props.get("confidence") or props.get("source_confidence")) or 0.5,
                    "updated_at": props.get("updated_at") or props.get("as_of") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
                }
            )
            feat["id"] = props["id"]
            feat["properties"] = props
            features.append(feat)
            continue
        feat = raw_feature_from_row(feed, path, row, i)
        if feat:
            features.append(feat)
    return features


@lru_cache(maxsize=4)
def raw_layer_features(root: str | None = None) -> tuple[dict, ...]:
    base = Path(root) if root else RAW_DATA_ROOT
    features: list[dict] = []
    for feed in RAW_FEEDS:
        feed_dir = base / feed
        if not feed_dir.exists():
            continue
        # ponytail: optional raw feeds stay lazy; absent folders just yield no features.
        for path in sorted(p for p in feed_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".geojson", ".json", ".csv", ".tsv"}):
            features.extend(raw_features_from_file(feed, path))
    return tuple(features)


def in_bbox(coords: list[float], bbox: list[float] | None) -> bool:
    if not bbox:
        return True
    lng, lat = coords[:2]
    return bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]


def parse_bbox(query_or_bbox: dict | str | None) -> list[float] | None:
    raw = query_or_bbox
    if isinstance(query_or_bbox, dict):
        raw = (query_or_bbox.get("bbox") or [""])[0]
    if not raw:
        return None
    nums = [float(x) for x in str(raw).split(",")]
    if len(nums) != 4:
        raise ValueError("bbox must be minLng,minLat,maxLng,maxLat")
    if nums[0] > nums[2] or nums[1] > nums[3]:
        raise ValueError("bbox min values must be <= max values")
    return nums


def bbox_or_400(raw: str | None) -> list[float] | None:
    try:
        return parse_bbox(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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


def intel() -> dict[str, list[dict]]:
    data = load_json(INTEL, {
        "entities": [], "assets": [], "permits": [], "farm_profiles": [], "industrial_profiles": [],
        "cameras": [], "asset_listings": [], "asset_relationships": [], "layer_features": [], "needs_location": [],
    })
    raw = list(raw_layer_features())
    if raw:
        data = {**data, "layer_features": [*data.get("layer_features", []), *raw]}
    return data


def valid_point(row: dict) -> list[float] | None:
    lat, lon = row.get("latitude"), row.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return [float(lon), float(lat)]
    return None


def geom(row: dict) -> dict | None:
    if row.get("geometry"):
        return row["geometry"]
    coords = valid_point(row)
    return {"type": "Point", "coordinates": coords} if coords else None


def centroid(geometry: dict) -> list[float] | None:
    if geometry.get("type") == "Point":
        return geometry.get("coordinates")
    coords = geometry.get("coordinates") or []
    flat = []

    def walk(v):
        if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
            flat.append(v[:2])
        elif isinstance(v, list):
            for child in v:
                walk(child)

    walk(coords)
    if not flat:
        return None
    return [sum(p[0] for p in flat) / len(flat), sum(p[1] for p in flat) / len(flat)]


def entity(entity_id: str | None) -> dict | None:
    if not entity_id:
        return None
    rows = {r["id"]: r for r in intel()["entities"]}
    if entity_id in rows:
        return rows[entity_id]
    n = universe_nodes().get(entity_id)
    if not n:
        return None
    return {
        "id": n["id"],
        "name": n.get("n"),
        "entity_type": n.get("kind"),
        "ticker": n.get("t"),
        "lei": n.get("lei"),
        "cik": n.get("cik"),
        "country": n.get("country"),
        "sector": n.get("sector"),
        "source": "universe.json",
        "confidence": n.get("source_confidence"),
        "updated_at": n.get("as_of"),
    }


def asset_layers(asset: dict) -> list[str]:
    t = asset.get("asset_type")
    gov_layers = ["government-facilities", "government-agencies"]
    if asset.get("facility_type") == "city_hall":
        gov_layers.append("government-city-halls")
    if asset.get("facility_type") == "courthouse":
        gov_layers.append("government-courthouses")
    return {
        "data_center": ["industrial-data-centers", "industrial-project-cost", "industrial-growth", "industrial-demand", "industrial-owner"],
        "factory": ["industrial-factories", "industrial-project-cost", "industrial-growth", "industrial-demand", "industrial-owner"],
        "farm": ["farm-boundaries", "farm-complexes", "farm-crop-history", "farm-soil-quality", "farm-vegetation", "farm-water-access", "farm-acres", "farm-for-sale", "farm-yield", "farm-purchase-price", "farm-current-value", "farm-risk"],
        "agricultural_complex": ["farm-complexes", "farm-vegetation"],
        "power_plant": ["industrial-energy", "industrial-power-plants", "industrial-project-cost", "industrial-growth", "industrial-demand", "industrial-owner"],
        "hydro_facility": ["industrial-energy", "industrial-hydro", "industrial-project-cost", "industrial-growth", "industrial-demand", "industrial-owner"],
        "industrial_complex": ["industrial-complexes", "industrial-project-cost", "industrial-growth", "industrial-demand", "industrial-owner"],
        "government_facility": gov_layers,
        "parcel": ["farm-boundaries"],
        "house": [],
        "franchise_location": [],
    }.get(t, [])


def asset_source(asset: dict) -> str | None:
    if asset.get("asset_type") in {"farm", "agricultural_complex", "parcel"}:
        return "farm_parcels"
    if asset.get("asset_type") == "government_facility":
        return "government_facilities"
    if asset_layers(asset):
        return "industrial_assets"
    return None


def geo_feature(row: dict, layer: str, kind: str, geometry: dict | None = None) -> dict | None:
    g = geometry or geom(row)
    if not g:
        return None
    props = {k: v for k, v in row.items() if k not in {"geometry", "latitude", "longitude"}}
    props.update({"id": row.get("id"), "layer": layer, "kind": kind})
    return {"type": "Feature", "id": f"{row.get('id')}:{layer}", "geometry": g, "properties": props}


def permit_feature(row: dict, assets: dict[str, dict], layer: str) -> dict | None:
    asset = assets.get(row.get("asset_id"))
    if not asset:
        return None
    feature = geo_feature({**row, "name": row.get("permit_type")}, layer, "permit", geom(asset))
    if feature:
        feature["properties"]["asset_type"] = asset.get("asset_type")
    return feature


MARKETPLACE_LAYER_BY_TYPE = {
    "farm": "marketplace-farms",
    "agricultural_land": "marketplace-ag-land",
    "house": "marketplace-houses",
    "commercial_property": "marketplace-commercial",
    "industrial_parcel": "marketplace-industrial-parcels",
    "franchise_location": "marketplace-franchises",
    "data_center_site": "marketplace-data-center-sites",
    "warehouse": "marketplace-warehouses",
    "mixed_use_property": "marketplace-mixed-use",
}


def listing_geometry(row: dict) -> dict | None:
    return row.get("geometry") or geom(row)


def listing_feature(row: dict) -> dict | None:
    g = listing_geometry(row)
    if not g:
        return None
    layer = MARKETPLACE_LAYER_BY_TYPE.get(row.get("asset_type"), "marketplace-other")
    props = {k: v for k, v in row.items() if k not in {"geometry", "latitude", "longitude"}}
    props.update({"id": row.get("id"), "layer": layer, "kind": "asset_listing"})
    return {"type": "Feature", "id": row.get("id"), "geometry": g, "properties": props}


def as_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def listing_matches(row: dict, filters: dict, bbox: list[float] | None = None) -> bool:
    if bbox and (not (g := listing_geometry(row)) or not (pt := centroid(g)) or not in_bbox(pt, bbox)):
        return False
    for key in ("asset_type", "zoning", "listing_status", "owner_type"):
        val = filters.get(key)
        if val and row.get(key) != val:
            return False
    ranges = [
        ("price", "min_price", "max_price"),
        ("acreage", "min_acres", "max_acres"),
        ("square_feet", "min_square_feet", "max_square_feet"),
    ]
    for field, lo_key, hi_key in ranges:
        value = as_float(row.get(field))
        lo, hi = as_float(filters.get(lo_key)), as_float(filters.get(hi_key))
        if lo is not None and (value is None or value < lo):
            return False
        if hi is not None and (value is None or value > hi):
            return False
    risk_max = as_float(filters.get("risk_max"))
    if risk_max is not None and as_float(row.get("risk_score")) is not None and as_float(row.get("risk_score")) > risk_max:
        return False
    infra_max = as_float(filters.get("infrastructure_distance_max"))
    if infra_max is not None:
        distances = [as_float(row.get(k)) for k in ("distance_to_roads_miles", "distance_to_power_miles", "distance_to_water_miles")]
        if not any(d is not None and d <= infra_max for d in distances):
            return False
    soil_min = filters.get("soil_quality_min")
    if soil_min and row.get("soil_quality") and str(row.get("soil_quality")) < soil_min:
        return False
    return True


def listing_rows(filters: dict | None = None, bbox: list[float] | None = None) -> list[dict]:
    filters = filters or {}
    rows = [r for r in intel().get("asset_listings", []) if listing_matches(r, filters, bbox)]
    q = str(filters.get("location") or "").strip().lower()
    if q:
        rows = [r for r in rows if q in str(r.get("address", "")).lower()]
    return rows


def asset_relationships(asset_id: str | None = None, entity_id: str | None = None) -> list[dict]:
    rows = intel().get("asset_relationships", [])
    if asset_id:
        rows = [r for r in rows if r.get("target_id") == asset_id or r.get("source_id") == asset_id]
    if entity_id:
        rows = [r for r in rows if r.get("source_id") == entity_id or r.get("target_id") == entity_id]
    return rows


def asset_entities(asset_id: str) -> dict:
    data = intel()
    asset = next((a for a in data["assets"] if a["id"] == asset_id), {}) or {}
    out: dict[str, list[dict] | dict | None] = {
        "owner": entity(asset.get("owner_entity_id")),
        "operator": entity(asset.get("operator_entity_id")),
        "financiers": [],
        "suppliers": [],
        "builders": [],
        "regulators": [],
        "permit_authorities": [],
        "relationships": [],
    }
    buckets = {
        "OWNS": "owner",
        "OPERATES": "operator",
        "FINANCES": "financiers",
        "SUPPLIES": "suppliers",
        "BUILDS": "builders",
        "REGULATES": "regulators",
        "PERMITS": "permit_authorities",
    }
    for rel in asset_relationships(asset_id=asset_id):
        rel_type = rel.get("relationship_type")
        row = {**rel, "entity": entity(rel.get("source_id"))}
        out["relationships"].append(row)
        bucket = buckets.get(rel_type)
        if not bucket:
            continue
        if bucket in {"owner", "operator"}:
            out[bucket] = row.get("entity") or out.get(bucket)
        else:
            out[bucket].append(row)
    return out


def entity_asset_rows(entity_id: str) -> list[dict]:
    data = intel()
    assets = {a["id"]: a for a in data["assets"]}
    rows = []
    direct = []
    for a in data["assets"]:
        if a.get("owner_entity_id") == entity_id:
            direct.append({"id": f"direct:{entity_id}:owns:{a['id']}", "source_id": entity_id, "target_id": a["id"], "relationship_type": "OWNS", "source": a.get("source"), "confidence": a.get("confidence"), "updated_at": a.get("updated_at"), "status": "inferred"})
        if a.get("operator_entity_id") == entity_id:
            direct.append({"id": f"direct:{entity_id}:operates:{a['id']}", "source_id": entity_id, "target_id": a["id"], "relationship_type": "OPERATES", "source": a.get("source"), "confidence": a.get("confidence"), "updated_at": a.get("updated_at"), "status": "inferred"})
    seen = set()
    for rel in [*asset_relationships(entity_id=entity_id), *direct]:
        asset = assets.get(rel.get("target_id")) or assets.get(rel.get("source_id"))
        if not asset or not geom(asset):
            continue
        key = (asset["id"], rel.get("relationship_type"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({**asset, "asset_relationship": rel})
    return rows


LAYER_GROUPS = [
    {"id": "reliefs", "label": "Reliefs", "source": "relief_features"},
    {"id": "industrial", "label": "Industrial Complex", "source": "industrial_assets"},
    {"id": "farms", "label": "Farms", "source": "farm_parcels"},
    {"id": "government", "label": "Government", "source": "government_facilities"},
    {"id": "cameras", "label": "Public Cameras", "source": "public_cameras"},
    {"id": "weather", "label": "Weather", "source": "weather_overlays"},
    {"id": "infrastructure", "label": "Infrastructure", "source": "infrastructure_lines"},
    {"id": "marketplace", "label": "Marketplace", "source": "marketplace_listings"},
]


def features_for_layer(layer: str, bbox: list[float] | None = None) -> dict:
    data = intel()
    assets = {a["id"]: a for a in data["assets"]}
    features: list[dict] = []
    aliases = {
        "reliefs": {"relief_features"},
        "industrial": {"industrial_assets"},
        "industrial_assets": {"industrial_assets"},
        "data_centers": {"industrial_assets"},
        "energy_facilities": {"industrial_assets"},
        "power_plants": {"industrial_assets"},
        "substations": {"infrastructure_lines"},
        "roads_rail_ports": {"infrastructure_lines"},
        "industrial_permits": {"industrial_assets"},
        "farms": {"farm_parcels"},
        "farm_parcels": {"farm_parcels"},
        "soil_quality": {"farm_parcels"},
        "crop_history": {"farm_parcels"},
        "government": {"government_facilities"},
        "government_facilities": {"government_facilities"},
        "regulatory_zones": {"government_facilities"},
        "government_permits": {"government_facilities"},
        "weather": {"weather_overlays"},
        "infrastructure": {"infrastructure_lines"},
        "transmission_lines": {"infrastructure_lines"},
        "marketplace": {"marketplace_listings"},
        "marketplace_listings": {"marketplace_listings"},
        "cameras": {"public_cameras"},
    }
    only_layers = {
        "data_centers": {"industrial-data-centers"},
        "energy_facilities": {"industrial-energy", "industrial-power-plants", "industrial-hydro"},
        "power_plants": {"industrial-power-plants"},
        "substations": {"industrial-substations"},
        "roads_rail_ports": {"industrial-logistics"},
        "industrial_permits": {"industrial-permits"},
        "transmission_lines": {"industrial-transmission"},
        "regulatory_zones": {"government-regulatory-zones"},
        "government_permits": {"government-permits"},
    }.get(layer)
    wanted = aliases.get(layer, {layer})

    if "public_cameras" in wanted:
        return public_cameras_geojson(bbox)
    if "marketplace_listings" in wanted:
        return feature_collection([f for row in listing_rows({}, bbox) if (f := listing_feature(row))])

    for asset in data["assets"]:
        if asset_source(asset) not in wanted:
            continue
        farm = next((p for p in data["farm_profiles"] if p["asset_id"] == asset["id"]), None)
        industrial = next((p for p in data["industrial_profiles"] if p["asset_id"] == asset["id"]), None)
        permits = [p for p in data["permits"] if p.get("asset_id") == asset["id"]]
        for layer_id in asset_layers(asset):
            if only_layers and layer_id not in only_layers:
                continue
            if layer == "soil_quality" and layer_id != "farm-soil-quality":
                continue
            if layer == "crop_history" and layer_id != "farm-crop-history":
                continue
            feature = geo_feature(asset, layer_id, "asset")
            if feature:
                feature["properties"].update({
                    "owner_name": (entity(asset.get("owner_entity_id")) or {}).get("name") or asset.get("owner_entity_id"),
                    "operator_name": (entity(asset.get("operator_entity_id")) or {}).get("name") or asset.get("operator_entity_id"),
                    "permit_status": permits[0].get("approval_status") if permits else "not loaded",
                })
                if farm:
                    feature["properties"].update({
                        "farm_type": farm.get("farm_type"),
                        "crop_history": farm.get("crop_history", []),
                        "estimated_yield": farm.get("estimated_yield"),
                        "annual_revenue_estimate": farm.get("annual_revenue_estimate"),
                        "annual_cost_estimate": farm.get("annual_cost_estimate"),
                        "yearly_estimated_gain": farm.get("yearly_estimated_gain"),
                        "past_activities": farm.get("past_activities", []),
                        "last_sale_price": farm.get("last_sale_price"),
                        "current_estimated_value": farm.get("current_estimated_value"),
                        "risk_score": farm.get("risk_score"),
                    })
                if industrial:
                    feature["properties"].update({
                        "industrial_type": industrial.get("industrial_type"),
                        "estimated_project_cost": industrial.get("estimated_project_cost"),
                        "power_capacity_mw": industrial.get("power_capacity_mw"),
                        "annual_growth": industrial.get("annual_growth"),
                        "demand_score": industrial.get("demand_score"),
                        "revenue_estimate": industrial.get("revenue_estimate"),
                        "operating_cost_estimate": industrial.get("operating_cost_estimate"),
                        "permits_cost": industrial.get("permits_cost"),
                        "owner_gain_loss_estimate": industrial.get("owner_gain_loss_estimate"),
                        "risk_score": industrial.get("risk_score"),
                    })
                features.append(feature)

    for permit in data["permits"]:
        asset = assets.get(permit.get("asset_id"), {})
        source = asset_source(asset)
        if source not in wanted:
            continue
        layer_id = "government-permits" if source == "government_facilities" else "industrial-permits"
        if only_layers and layer_id not in only_layers:
            continue
        feature = permit_feature(permit, assets, layer_id)
        if feature:
            feature["properties"]["permit_status"] = permit.get("approval_status")
            features.append(feature)

    for row in data["layer_features"]:
        source = row.get("source_layer")
        if source in wanted or row.get("layer_type") in wanted:
            if only_layers and row.get("layer_type") not in only_layers:
                continue
            feature = geo_feature(row, row.get("layer_type", source), "layer_feature", row.get("geometry"))
            if feature:
                feature["properties"].update(row.get("properties_json") or {})
                features.append(feature)

    if bbox:
        features = [f for f in features if (pt := centroid(f["geometry"])) and in_bbox(pt, bbox)]
    return feature_collection(features)


def public_cameras_geojson(bbox: list[float] | None = None) -> dict:
    rows = [r for r in intel()["cameras"] if r.get("legal_public_access") is True and valid_point(r)]
    rows = [r for r in rows if in_bbox(valid_point(r), bbox)]
    return feature_collection([geo_feature(r, "relief-cameras", "camera") for r in rows])


def public_permits(bbox: list[float] | None = None, permit_type: str | None = None) -> list[dict]:
    data = intel()
    assets = {a["id"]: a for a in data["assets"]}
    rows = []
    for permit in data["permits"]:
        if permit_type and permit.get("permit_type") != permit_type:
            continue
        asset = assets.get(permit.get("asset_id"))
        if not asset or not (coords := valid_point(asset)) or not in_bbox(coords, bbox):
            continue
        rows.append({**permit, "asset": asset})
    return rows


def asset_profile(asset_id: str) -> dict:
    data = intel()
    asset = next((a for a in data["assets"] if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(404, "asset not found")
    farm = next((p for p in data["farm_profiles"] if p["asset_id"] == asset_id), None)
    industrial = next((p for p in data["industrial_profiles"] if p["asset_id"] == asset_id), None)
    permits = [p for p in data["permits"] if p.get("asset_id") == asset_id]
    listings = [p for p in data.get("asset_listings", []) if p.get("asset_id") == asset_id]
    relationships = asset_relationships(asset_id=asset_id)
    return {
        **asset,
        "owner": entity(asset.get("owner_entity_id")),
        "operator": entity(asset.get("operator_entity_id")),
        "permits": permits,
        "listings": listings,
        "asset_relationships": relationships,
        "connected_entities": asset_entities(asset_id),
        "farm_profile": farm,
        "industrial_profile": industrial,
    }


def num(v, default: float | None = None) -> float | None:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def first_listing(profile: dict) -> dict:
    return (profile.get("listings") or [{}])[0] or {}


def valuation_overrides() -> dict:
    return load_json(VALUATION_ASSUMPTIONS, {})


def save_valuation_overrides(rows: dict) -> None:
    VALUATION_ASSUMPTIONS.write_text(json.dumps(rows, indent=2) + "\n")


def parse_yield_per_acre(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", str(v or ""))
    return float(m.group(1)) if m else None


def model_kind(profile: dict) -> str:
    listing = first_listing(profile)
    t = listing.get("asset_type") or profile.get("asset_type")
    if t in {"farm", "agricultural_land", "agricultural_complex", "parcel"}:
        return "farm"
    if t in {"data_center", "data_center_site"}:
        return "data_center"
    if t in {"industrial_complex", "factory", "power_plant", "hydro_facility", "industrial_parcel", "warehouse"}:
        return "industrial"
    if t in {"house", "commercial_property", "mixed_use_property"}:
        return "property"
    if t == "franchise_location":
        return "franchise"
    if t == "government_facility":
        return "government_project"
    return "generic"


def default_assumptions(profile: dict) -> dict:
    listing, farm, industrial = first_listing(profile), profile.get("farm_profile") or {}, profile.get("industrial_profile") or {}
    acres = num(listing.get("acreage") or farm.get("acres") or profile.get("area_acres"), 0) or 0
    project_cost = num(industrial.get("estimated_project_cost") or listing.get("price"), 0) or 0
    power_mw = num(industrial.get("power_capacity_mw"), 0) or 0
    revenue = num(farm.get("annual_revenue_estimate") or industrial.get("revenue_estimate"), None)
    cost = num(farm.get("annual_cost_estimate") or industrial.get("operating_cost_estimate"), None)
    return {
        "revenue": revenue if revenue is not None else (acres * 900 if acres else (power_mw * 1_200_000 if power_mw else num(listing.get("price"), 0) * 0.08)),
        "cost": cost if cost is not None else (acres * 650 if acres else (power_mw * 620_000 if power_mw else num(listing.get("price"), 0) * 0.045)),
        "growth": 0.02,
        "discount_rate": 0.1,
        "utilization": 0.72,
        "yield": parse_yield_per_acre(farm.get("estimated_yield") or listing.get("expected_yield")) or 150,
        "capex": project_cost,
        "tax_incentives": 0,
        "risk_adjustment": num((first_listing(profile)).get("risk_score"), 0.35) or 0.35,
        "crop_price": 4.5,
        "operating_cost_per_acre": 650,
        "property_tax_rate": 0.012,
        "electricity_cost_per_mwh": 55,
        "revenue_per_mw": 1_200_000,
        "construction_cost": project_cost,
        "financing_cost": 0.08,
    }


def asset_assumptions(asset_id: str, case: str = "base") -> dict:
    profile = asset_profile(asset_id)
    assumptions = default_assumptions(profile)
    overrides = valuation_overrides().get(asset_id, {})
    assumptions.update(overrides.get("custom", {}))
    assumptions.update(overrides.get(case, {}))
    mult = {"bear": 0.82, "base": 1.0, "bull": 1.18}.get(case, 1.0)
    if case in {"bear", "bull"}:
        assumptions["revenue"] = num(assumptions.get("revenue"), 0) * mult
        assumptions["cost"] = num(assumptions.get("cost"), 0) * (1.12 if case == "bear" else 0.96)
        assumptions["utilization"] = clamp(num(assumptions.get("utilization"), 0.72) * mult, 0, 1)
        assumptions["risk_adjustment"] = clamp(num(assumptions.get("risk_adjustment"), 0.35) * (1.25 if case == "bear" else 0.82), 0, 1)
    return assumptions


def missing_fields(profile: dict, assumptions: dict) -> list[str]:
    listing, farm, industrial = first_listing(profile), profile.get("farm_profile") or {}, profile.get("industrial_profile") or {}
    checks = {
        "listing/current acquisition price": listing.get("price"),
        "last known sale price": listing.get("last_sale_price") or farm.get("last_sale_price"),
        "acreage or square feet": listing.get("acreage") or listing.get("square_feet") or profile.get("area_acres"),
        "revenue assumption": assumptions.get("revenue"),
        "cost assumption": assumptions.get("cost"),
        "risk score": listing.get("risk_score") or farm.get("risk_score") or industrial.get("risk_score"),
        "permit status": (profile.get("permits") or [{}])[0].get("approval_status"),
    }
    return [k for k, v in checks.items() if v in (None, "", [])]


def npv(cash: float, growth: float, discount: float, years: int = 10, capex: float = 0) -> float:
    total = -capex
    for year in range(1, years + 1):
        total += cash * ((1 + growth) ** (year - 1)) / ((1 + discount) ** year)
    return total


def valuation_label(score: float, good: str = "buy", mid: str = "watch", bad: str = "avoid") -> str:
    return good if score >= 70 else mid if score >= 45 else bad


def valuation_model(asset_id: str, case: str = "base") -> dict:
    profile = asset_profile(asset_id)
    listing, farm, industrial = first_listing(profile), profile.get("farm_profile") or {}, profile.get("industrial_profile") or {}
    assumptions = asset_assumptions(asset_id, case)
    kind = model_kind(profile)
    acquisition = num(listing.get("price"), None)
    acres = num(listing.get("acreage") or farm.get("acres") or profile.get("area_acres"), 0) or 0
    sqft = num(listing.get("square_feet"), 0) or 0
    revenue = num(assumptions.get("revenue"), 0) or 0
    cost = num(assumptions.get("cost"), 0) or 0
    yearly_gain = revenue - cost
    current_value = num(listing.get("current_estimated_value") or farm.get("current_estimated_value"), None)
    if current_value is None:
        current_value = max(acquisition or 0, yearly_gain / max(num(assumptions.get("discount_rate"), 0.1) or 0.1, 0.01)) if yearly_gain > 0 else acquisition
    last_sale = num(listing.get("last_sale_price") or farm.get("last_sale_price"), None)
    capex = num(assumptions.get("capex"), 0) or (acquisition or 0)
    payback = round(capex / yearly_gain, 1) if yearly_gain > 0 and capex else None
    risk = num(listing.get("risk_score") or farm.get("risk_score") or industrial.get("risk_score") or assumptions.get("risk_adjustment"), 0.5) or 0.5
    confidence = num(listing.get("confidence") or profile.get("confidence"), 0.25) or 0.25
    breakdown = []
    score = 50

    if kind == "farm":
        soil = str(farm.get("soil_quality") or listing.get("soil_quality") or "")
        soil_pts = 18 if soil.startswith("A") else 12 if soil.startswith("B") else 5 if soil else 0
        water_pts = 12 if (farm.get("water_access") or "water" in str(listing.get("nearby_infrastructure", "")).lower()) else 0
        flood_penalty = -12 if str(listing.get("flood_risk") or profile.get("flood_drought_risk")).lower() in {"high", "medium"} else -4
        price_per_acre = (acquisition / acres) if acquisition and acres else None
        price_pts = -8 if price_per_acre and price_per_acre > 9000 else 8 if price_per_acre else 0
        road_pts = 9 if num(listing.get("distance_to_roads_miles"), 99) <= 1 else 2
        crop_pts = 14 if farm.get("crop_history") or listing.get("expected_yield") else 0
        for name, pts in [("soil quality", soil_pts), ("water access", water_pts), ("flood/drought risk", flood_penalty), ("price per acre", price_pts), ("road access", road_pts), ("crop history", crop_pts)]:
            breakdown.append({"factor": name, "points": pts})
            score += pts
        estimated_yield = acres * num(assumptions.get("yield"), 0)
        soil_adjusted_value = (price_per_acre or 7500) * acres * (1 + soil_pts / 100) if acres else current_value
        extra = {"estimated_annual_yield": estimated_yield, "price_per_acre": price_per_acre, "soil_adjusted_land_value": soil_adjusted_value, "value_vs_county_median": "placeholder"}
        label = valuation_label(score)
    elif kind == "data_center":
        power = num(industrial.get("power_capacity_mw"), 0) or 0
        infra_pts = 18 if profile.get("nearby_transmission") else 6
        demand_pts = 15 if industrial.get("demand_score") else 8
        energy_penalty = -12 if num(assumptions.get("electricity_cost_per_mwh"), 55) > 70 else -4
        water_penalty = -8 if not profile.get("nearby_water_access") else -2
        reg_penalty = -8 if not profile.get("permits") else 4
        for name, pts in [("grid proximity", infra_pts), ("demand", demand_pts), ("energy cost risk", energy_penalty), ("water risk", water_penalty), ("regulatory/permit status", reg_penalty)]:
            breakdown.append({"factor": name, "points": pts})
            score += pts
        extra = {"cost_per_mw": capex / power if power else None, "revenue_per_mw": revenue / power if power else None, "estimated_ebitda": yearly_gain, "irr_placeholder": None, "energy_risk_score": abs(energy_penalty), "water_risk_score": abs(water_penalty), "regulatory_risk_score": abs(reg_penalty)}
        label = valuation_label(score, "good deal", "uncertain", "bad deal")
    elif kind == "industrial":
        infra_pts = 18 if profile.get("nearby_logistics") or profile.get("nearby_transmission") else 6
        permit_pts = 14 if profile.get("permits") else -6
        demand_pts = 12 if industrial.get("demand_score") else 6
        env_penalty = -10 if str(listing.get("environmental_risk")).lower() == "medium" else -4
        for name, pts in [("infrastructure", infra_pts), ("permits", permit_pts), ("demand", demand_pts), ("environmental risk", env_penalty)]:
            breakdown.append({"factor": name, "points": pts})
            score += pts
        extra = {"project_attractiveness_score": clamp(score), "infrastructure_score": infra_pts, "permit_score": permit_pts, "demand_score": demand_pts, "risk_adjusted_value_score": clamp(score - risk * 20)}
        label = valuation_label(score, "good deal", "uncertain", "bad deal")
    elif kind == "franchise":
        demand_pts = 14 if listing.get("expected_yield") else 6
        zoning_pts = 10 if listing.get("zoning") == "commercial" else 0
        crime_penalty = -12 if num(listing.get("crime_aggregate_score"), 0) > 0.45 else -4
        payback_pts = 10 if payback and payback < 7 else 0
        for name, pts in [("local demand", demand_pts), ("zoning", zoning_pts), ("crime aggregate", crime_penalty), ("payback", payback_pts)]:
            breakdown.append({"factor": name, "points": pts})
            score += pts
        extra = {"franchise_fit_score": clamp(score), "location_risk": abs(crime_penalty), "demand_score": demand_pts}
        label = valuation_label(score)
    else:
        crime_penalty = -12 if num(listing.get("crime_aggregate_score"), 0) > 0.45 else -4
        flood_penalty = -10 if str(listing.get("flood_risk")).lower() in {"medium", "high"} else -2
        affordability = 16 if acquisition and current_value and acquisition <= current_value else 6
        location = 12 if num(listing.get("distance_to_roads_miles"), 99) <= 1 else 5
        for name, pts in [("affordability", affordability), ("location quality", location), ("crime aggregate", crime_penalty), ("flood/weather risk", flood_penalty)]:
            breakdown.append({"factor": name, "points": pts})
            score += pts
        extra = {"affordability_score": affordability, "location_quality_score": location, "estimated_fair_value_placeholder": current_value}
        label = valuation_label(score)

    score = clamp(score - risk * 12)
    out = {
        "asset_id": asset_id,
        "case": case,
        "model_type": kind,
        "headline_recommendation": label,
        "estimated_current_value": round(current_value, 2) if current_value is not None else None,
        "last_known_sale_price": last_sale,
        "acquisition_price": acquisition,
        "estimated_annual_revenue": round(revenue, 2),
        "estimated_annual_operating_cost": round(cost, 2),
        "estimated_yearly_gain_loss": round(yearly_gain, 2),
        "payback_period": payback,
        "npv": round(npv(yearly_gain, num(assumptions.get("growth"), 0.02), num(assumptions.get("discount_rate"), 0.1), capex=capex), 2),
        "risk_score": round(risk, 3),
        "confidence_score": round(confidence, 3),
        "source_list": sorted({x for x in [profile.get("source"), listing.get("source"), farm.get("source"), industrial.get("source"), *(p.get("source") for p in profile.get("permits", []))] if x}),
        "missing_data_fields": missing_fields(profile, assumptions),
        "assumptions": assumptions,
        "score": round(score, 1),
        "score_breakdown": breakdown,
        "extra": extra,
        "disclaimer": "Deterministic estimate from public/mock fields and user assumptions; not financial advice or a guarantee.",
    }
    return out


@app.get("/api/map/layers")
def api_layers():
    return {
        "groups": LAYER_GROUPS,
        "sources": ["relief_features", "industrial_assets", "farm_parcels", "government_facilities", "public_cameras", "weather_overlays", "infrastructure_lines", "marketplace_listings", "usgs_3dep", "eia", "fbi_crime"],
    }


@app.get("/api/map/entities.geojson")
def api_map_entities(bbox: str | None = None):
    return map_entities(bbox_or_400(bbox))


@app.get("/api/map/relationships.geojson")
def api_map_relationships(bbox: str | None = None):
    return map_relationships(bbox_or_400(bbox))


@app.get("/api/map/features.geojson")
def api_map_features(layer: str = Query(...), bbox: str | None = None):
    return features_for_layer(layer, bbox_or_400(bbox))


@app.get("/api/assets/search")
def api_assets_search(
    asset_type: str | None = None,
    bbox: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_acres: float | None = None,
    max_acres: float | None = None,
    zoning: str | None = None,
    listing_status: str | None = None,
    risk_max: float | None = None,
    soil_quality_min: str | None = None,
    infrastructure_distance_max: float | None = None,
):
    box = bbox_or_400(bbox)
    filters = {k: v for k, v in {
        "asset_type": asset_type, "min_price": min_price, "max_price": max_price, "min_acres": min_acres,
        "max_acres": max_acres, "zoning": zoning, "listing_status": listing_status, "risk_max": risk_max,
        "soil_quality_min": soil_quality_min, "infrastructure_distance_max": infrastructure_distance_max,
    }.items() if v not in (None, "")}
    listing_asset_ids = {r.get("asset_id") for r in listing_rows(filters, box)} if any(k in filters for k in ("min_price", "max_price", "min_acres", "max_acres", "zoning", "listing_status", "risk_max", "soil_quality_min", "infrastructure_distance_max")) else None
    rows = []
    for asset in intel()["assets"]:
        coords = valid_point(asset)
        if not coords:
            continue
        if asset_type and asset.get("asset_type") != asset_type:
            continue
        if listing_asset_ids is not None and asset.get("id") not in listing_asset_ids:
            continue
        if in_bbox(coords, box):
            rows.append(asset)
    return {"assets": rows, "needs_location": intel().get("needs_location", [])}


@app.get("/api/assets/{asset_id}")
def api_asset(asset_id: str):
    return asset_profile(unquote(asset_id))


@app.get("/api/assets/{asset_id}/due-diligence")
def api_asset_due_diligence(asset_id: str):
    profile = asset_profile(unquote(asset_id))
    return {
        "asset": profile,
        "owner": profile.get("owner"),
        "operator": profile.get("operator"),
        "permits": profile.get("permits", []),
        "risks": {"risk_score": (profile.get("farm_profile") or profile.get("industrial_profile") or {}).get("risk_score"), "status": "placeholder"},
        "infrastructure_proximity": [],
        "valuation": {
            "last_sale_price": (profile.get("farm_profile") or {}).get("last_sale_price"),
            "current_estimated_value": (profile.get("farm_profile") or {}).get("current_estimated_value"),
            "revenue_estimate": (profile.get("industrial_profile") or {}).get("revenue_estimate"),
            "status": "placeholder",
        },
    }


@app.get("/api/assets/{asset_id}/nearby-infrastructure")
def api_asset_nearby_infrastructure(asset_id: str):
    asset = asset_profile(unquote(asset_id))
    rows = [r for r in intel().get("layer_features", []) if r.get("source_layer") == "infrastructure_lines"]
    return {"asset_id": asset["id"], "nearby_infrastructure": rows[:8], "status": "placeholder"}


@app.get("/api/assets/{asset_id}/risk-summary")
def api_asset_risk_summary(asset_id: str):
    asset = asset_profile(unquote(asset_id))
    listing = (asset.get("listings") or [{}])[0]
    profile = asset.get("farm_profile") or asset.get("industrial_profile") or {}
    return {
        "asset_id": asset["id"],
        "risk_score": listing.get("risk_score") or profile.get("risk_score"),
        "flood_risk": listing.get("flood_risk") or asset.get("flood_drought_risk"),
        "crime_aggregate_score": listing.get("crime_aggregate_score"),
        "environmental_risk": listing.get("environmental_risk"),
        "source": listing.get("source") or asset.get("source"),
        "confidence": listing.get("confidence") or asset.get("confidence"),
        "status": "placeholder",
    }


@app.get("/api/assets/{asset_id}/valuation")
def api_asset_valuation(asset_id: str, case: str = "base"):
    return valuation_model(unquote(asset_id), case)


@app.get("/api/assets/{asset_id}/risk-score")
def api_asset_risk_score(asset_id: str, case: str = "base"):
    valuation = valuation_model(unquote(asset_id), case)
    return {
        "asset_id": unquote(asset_id),
        "case": case,
        "risk_score": valuation["risk_score"],
        "score": valuation["score"],
        "headline_recommendation": valuation["headline_recommendation"],
        "breakdown": valuation["score_breakdown"],
        "confidence_score": valuation["confidence_score"],
        "missing_data_fields": valuation["missing_data_fields"],
    }


@app.get("/api/assets/{asset_id}/valuation-assumptions")
def api_asset_valuation_assumptions(asset_id: str, case: str = "base"):
    aid = unquote(asset_id)
    return {
        "asset_id": aid,
        "case": case,
        "assumptions": asset_assumptions(aid, case),
        "overrides": valuation_overrides().get(aid, {}),
        "editable_fields": ["revenue", "cost", "growth", "discount_rate", "utilization", "yield", "capex", "tax_incentives", "risk_adjustment"],
    }


@app.post("/api/assets/{asset_id}/valuation-assumptions")
async def api_post_asset_valuation_assumptions(asset_id: str, payload: dict[str, Any]):
    aid = unquote(asset_id)
    case = str(payload.get("case") or "custom")
    assumptions = payload.get("assumptions") or payload
    editable = {"revenue", "cost", "growth", "discount_rate", "utilization", "yield", "capex", "tax_incentives", "risk_adjustment", "crop_price", "operating_cost_per_acre", "property_tax_rate", "electricity_cost_per_mwh", "revenue_per_mw", "construction_cost", "financing_cost"}
    clean = {k: v for k, v in assumptions.items() if k in editable and isinstance(v, (int, float))}
    rows = valuation_overrides()
    rows.setdefault(aid, {})[case] = clean
    save_valuation_overrides(rows)
    return {"ok": True, "asset_id": aid, "case": case, "assumptions": asset_assumptions(aid, case)}


@app.get("/api/assets/{asset_id}/scenario")
def api_asset_scenario(asset_id: str, case: str = "base"):
    return valuation_model(unquote(asset_id), case)


@app.get("/api/assets/{asset_id}/entities")
def api_asset_entities(asset_id: str):
    return {"asset_id": unquote(asset_id), **asset_entities(unquote(asset_id))}


@app.get("/api/assets/{asset_id}/relationship-graph")
def api_asset_relationship_graph(asset_id: str):
    aid = unquote(asset_id)
    profile = asset_profile(aid)
    nodes = [{"id": aid, "type": "asset", "label": profile.get("name")}]
    edges = []
    for rel in profile.get("asset_relationships", []):
        other = rel["source_id"] if rel.get("target_id") == aid else rel.get("target_id")
        nodes.append({"id": other, "type": "entity" if entity(other) else "object", "label": (entity(other) or {}).get("name", other)})
        edges.append(rel)
    for listing in profile.get("listings", []):
        nodes.append({"id": listing["id"], "type": "listing", "label": listing.get("title")})
        edges.append({"id": f"{aid}:listed:{listing['id']}", "source_id": aid, "target_id": listing["id"], "relationship_type": "LISTED_AS", "source": listing.get("source"), "confidence": listing.get("confidence"), "updated_at": listing.get("last_updated")})
    return {"nodes": nodes, "edges": edges}


@app.get("/api/listings/search")
def api_listings_search(
    bbox: str | None = None,
    asset_type: str | None = None,
    location: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_acres: float | None = None,
    max_acres: float | None = None,
    min_square_feet: float | None = None,
    max_square_feet: float | None = None,
    zoning: str | None = None,
    listing_status: str | None = None,
    owner_type: str | None = None,
    risk_max: float | None = None,
    soil_quality_min: str | None = None,
    infrastructure_distance_max: float | None = None,
    format: str = "json",
):
    filters = {k: v for k, v in locals().items() if k not in {"bbox", "format"} and v not in (None, "")}
    rows = listing_rows(filters, bbox_or_400(bbox))
    if format == "geojson":
        return feature_collection([f for row in rows if (f := listing_feature(row))])
    return {"listings": rows}


@app.get("/api/listings/{listing_id}")
def api_listing(listing_id: str):
    lid = unquote(listing_id)
    listing = next((r for r in intel().get("asset_listings", []) if r.get("id") == lid), None)
    if not listing:
        raise HTTPException(404, "listing not found")
    asset = asset_profile(listing["asset_id"]) if listing.get("asset_id") else None
    return {"listing": listing, "asset": asset}


@app.get("/api/entity/{entity_id}")
def api_entity(entity_id: str):
    row = entity(unquote(entity_id))
    if not row:
        raise HTTPException(404, "entity not found")
    return row


@app.get("/api/entity/{entity_id}/neighborhood")
def api_entity_neighborhood(entity_id: str, depth: int = 1):
    return neighborhood(unquote(entity_id), depth)


@app.get("/api/entity/{entity_id}/risk")
def api_entity_risk(entity_id: str):
    focus = load_json("graph-index.json", {}).get(unquote(entity_id), {})
    return risk_summary(unquote(entity_id), {unquote(entity_id), *focus.get("neighbors", [])})


@app.get("/api/entity/{entity_id}/assets")
def api_entity_assets(entity_id: str):
    eid = unquote(entity_id)
    rows = entity_asset_rows(eid)
    return {"entity": entity(eid), "assets": rows}


@app.get("/api/entity/{entity_id}/asset-map.geojson")
def api_entity_asset_map(entity_id: str):
    rows = entity_asset_rows(unquote(entity_id))
    features = []
    for row in rows:
        rel = row.get("asset_relationship", {})
        feature = geo_feature(row, f"entity-asset-{str(rel.get('relationship_type', 'asset')).lower()}", "entity_asset")
        if feature:
            feature["properties"]["asset_relationship"] = rel
            features.append(feature)
    return feature_collection(features)


@app.get("/api/entity/{entity_id}/combined-neighborhood")
def api_entity_combined_neighborhood(entity_id: str, depth: int = 2):
    eid = unquote(entity_id)
    graph = neighborhood(eid, depth)
    assets = entity_asset_rows(eid)
    asset_edges = [a.get("asset_relationship") for a in assets if a.get("asset_relationship")]
    return {**graph, "assets": assets, "asset_edges": asset_edges}


@app.get("/api/entity/{entity_id}/dcf.xlsx")
def api_entity_dcf(entity_id: str, method: str = "cash_flow"):
    return FileResponse(build_dcf_workbook(unquote(entity_id), method))


@app.get("/api/cameras/public.geojson")
def api_cameras_public(bbox: str | None = None):
    return public_cameras_geojson(bbox_or_400(bbox))


@app.get("/api/permits/search")
def api_permits_search(bbox: str | None = None, permit_type: str | None = None):
    return {"permits": public_permits(bbox_or_400(bbox), permit_type)}


@app.get("/api/location/unknown")
def api_location_unknown():
    return load_json("location_unknown.json", [])


@app.get("/api/data-sources/status")
def api_data_sources_status():
    return validation_status()


@app.get("/api/reliefs/dem/status")
def api_reliefs_dem_status():
    status = validation_status()
    return status["dem"] | {"checks": status["checks"], "sources": status["sources"]}


@app.get("/api/reliefs/dem/tilejson")
def api_reliefs_dem_tilejson():
    tilejson = dem_tilejson()
    if not tilejson:
        raise HTTPException(404, "DEM tilejson not found; run scripts/build_usgs_terrain_tiles.py")
    return tilejson


@app.get("/api/reliefs/terrain/sources")
def api_reliefs_terrain_sources():
    registry = terrain_coverage_registry()
    return {
        "active_source": registry.get("active_source"),
        "active_tilejson": registry.get("active_tilejson"),
        "sources": registry.get("sources", []),
    }


@app.get("/api/reliefs/terrain/coverage")
def api_reliefs_terrain_coverage():
    registry = terrain_coverage_registry()
    active = registry.get("active_tilejson")
    active_sources = [s for s in registry.get("sources", []) if s.get("public_tilejson") == active]
    return {
        "coverage_bbox": registry.get("coverage_bbox"),
        "georgia_bbox_coverage_pct": registry.get("georgia_bbox_coverage_pct"),
        "georgia_available_products_coverage_pct": registry.get("georgia_available_products_coverage_pct"),
        "georgia_available_products_processed": registry.get("georgia_available_products_processed"),
        "georgia_available_products_total": registry.get("georgia_available_products_total"),
        "florida_bbox_coverage_pct": registry.get("florida_bbox_coverage_pct"),
        "florida_available_products_coverage_pct": registry.get("florida_available_products_coverage_pct"),
        "florida_available_products_processed": registry.get("florida_available_products_processed"),
        "florida_available_products_total": registry.get("florida_available_products_total"),
        "south_carolina_bbox_coverage_pct": registry.get("south_carolina_bbox_coverage_pct"),
        "south_carolina_available_products_coverage_pct": registry.get("south_carolina_available_products_coverage_pct"),
        "south_carolina_available_products_processed": registry.get("south_carolina_available_products_processed"),
        "south_carolina_available_products_total": registry.get("south_carolina_available_products_total"),
        "north_carolina_bbox_coverage_pct": registry.get("north_carolina_bbox_coverage_pct"),
        "north_carolina_available_products_coverage_pct": registry.get("north_carolina_available_products_coverage_pct"),
        "north_carolina_available_products_processed": registry.get("north_carolina_available_products_processed"),
        "north_carolina_available_products_total": registry.get("north_carolina_available_products_total"),
        "virginia_bbox_coverage_pct": registry.get("virginia_bbox_coverage_pct"),
        "virginia_available_products_coverage_pct": registry.get("virginia_available_products_coverage_pct"),
        "virginia_available_products_processed": registry.get("virginia_available_products_processed"),
        "virginia_available_products_total": registry.get("virginia_available_products_total"),
        "west_virginia_bbox_coverage_pct": registry.get("west_virginia_bbox_coverage_pct"),
        "west_virginia_available_products_coverage_pct": registry.get("west_virginia_available_products_coverage_pct"),
        "west_virginia_available_products_processed": registry.get("west_virginia_available_products_processed"),
        "west_virginia_available_products_total": registry.get("west_virginia_available_products_total"),
        "maryland_bbox_coverage_pct": registry.get("maryland_bbox_coverage_pct"),
        "maryland_available_products_coverage_pct": registry.get("maryland_available_products_coverage_pct"),
        "maryland_available_products_processed": registry.get("maryland_available_products_processed"),
        "maryland_available_products_total": registry.get("maryland_available_products_total"),
        "pennsylvania_bbox_coverage_pct": registry.get("pennsylvania_bbox_coverage_pct"),
        "pennsylvania_available_products_coverage_pct": registry.get("pennsylvania_available_products_coverage_pct"),
        "pennsylvania_available_products_processed": registry.get("pennsylvania_available_products_processed"),
        "pennsylvania_available_products_total": registry.get("pennsylvania_available_products_total"),
        "new_jersey_bbox_coverage_pct": registry.get("new_jersey_bbox_coverage_pct"),
        "new_jersey_available_products_coverage_pct": registry.get("new_jersey_available_products_coverage_pct"),
        "new_jersey_available_products_processed": registry.get("new_jersey_available_products_processed"),
        "new_jersey_available_products_total": registry.get("new_jersey_available_products_total"),
        "new_york_bbox_coverage_pct": registry.get("new_york_bbox_coverage_pct"),
        "new_york_available_products_coverage_pct": registry.get("new_york_available_products_coverage_pct"),
        "new_york_available_products_processed": registry.get("new_york_available_products_processed"),
        "new_york_available_products_total": registry.get("new_york_available_products_total"),
        "delaware_bbox_coverage_pct": registry.get("delaware_bbox_coverage_pct"),
        "delaware_available_products_coverage_pct": registry.get("delaware_available_products_coverage_pct"),
        "delaware_available_products_processed": registry.get("delaware_available_products_processed"),
        "delaware_available_products_total": registry.get("delaware_available_products_total"),
        "connecticut_bbox_coverage_pct": registry.get("connecticut_bbox_coverage_pct"),
        "connecticut_available_products_coverage_pct": registry.get("connecticut_available_products_coverage_pct"),
        "connecticut_available_products_processed": registry.get("connecticut_available_products_processed"),
        "connecticut_available_products_total": registry.get("connecticut_available_products_total"),
        "rhode_island_bbox_coverage_pct": registry.get("rhode_island_bbox_coverage_pct"),
        "rhode_island_available_products_coverage_pct": registry.get("rhode_island_available_products_coverage_pct"),
        "rhode_island_available_products_processed": registry.get("rhode_island_available_products_processed"),
        "rhode_island_available_products_total": registry.get("rhode_island_available_products_total"),
        "massachusetts_bbox_coverage_pct": registry.get("massachusetts_bbox_coverage_pct"),
        "massachusetts_available_products_coverage_pct": registry.get("massachusetts_available_products_coverage_pct"),
        "massachusetts_available_products_processed": registry.get("massachusetts_available_products_processed"),
        "massachusetts_available_products_total": registry.get("massachusetts_available_products_total"),
        "vermont_bbox_coverage_pct": registry.get("vermont_bbox_coverage_pct"),
        "vermont_available_products_coverage_pct": registry.get("vermont_available_products_coverage_pct"),
        "vermont_available_products_processed": registry.get("vermont_available_products_processed"),
        "vermont_available_products_total": registry.get("vermont_available_products_total"),
        "maine_bbox_coverage_pct": registry.get("maine_bbox_coverage_pct"),
        "maine_available_products_coverage_pct": registry.get("maine_available_products_coverage_pct"),
        "maine_available_products_processed": registry.get("maine_available_products_processed"),
        "maine_available_products_total": registry.get("maine_available_products_total"),
        "ohio_bbox_coverage_pct": registry.get("ohio_bbox_coverage_pct"),
        "ohio_available_products_coverage_pct": registry.get("ohio_available_products_coverage_pct"),
        "ohio_available_products_processed": registry.get("ohio_available_products_processed"),
        "ohio_available_products_total": registry.get("ohio_available_products_total"),
        "kentucky_bbox_coverage_pct": registry.get("kentucky_bbox_coverage_pct"),
        "kentucky_available_products_coverage_pct": registry.get("kentucky_available_products_coverage_pct"),
        "kentucky_available_products_processed": registry.get("kentucky_available_products_processed"),
        "kentucky_available_products_total": registry.get("kentucky_available_products_total"),
        "tennessee_bbox_coverage_pct": registry.get("tennessee_bbox_coverage_pct"),
        "tennessee_available_products_coverage_pct": registry.get("tennessee_available_products_coverage_pct"),
        "tennessee_available_products_processed": registry.get("tennessee_available_products_processed"),
        "tennessee_available_products_total": registry.get("tennessee_available_products_total"),
        "alabama_bbox_coverage_pct": registry.get("alabama_bbox_coverage_pct"),
        "alabama_available_products_coverage_pct": registry.get("alabama_available_products_coverage_pct"),
        "alabama_available_products_processed": registry.get("alabama_available_products_processed"),
        "alabama_available_products_total": registry.get("alabama_available_products_total"),
        "mississippi_bbox_coverage_pct": registry.get("mississippi_bbox_coverage_pct"),
        "mississippi_available_products_coverage_pct": registry.get("mississippi_available_products_coverage_pct"),
        "mississippi_available_products_processed": registry.get("mississippi_available_products_processed"),
        "mississippi_available_products_total": registry.get("mississippi_available_products_total"),
        "louisiana_bbox_coverage_pct": registry.get("louisiana_bbox_coverage_pct"),
        "louisiana_available_products_coverage_pct": registry.get("louisiana_available_products_coverage_pct"),
        "louisiana_available_products_processed": registry.get("louisiana_available_products_processed"),
        "louisiana_available_products_total": registry.get("louisiana_available_products_total"),
        "arkansas_bbox_coverage_pct": registry.get("arkansas_bbox_coverage_pct"),
        "arkansas_available_products_coverage_pct": registry.get("arkansas_available_products_coverage_pct"),
        "arkansas_available_products_processed": registry.get("arkansas_available_products_processed"),
        "arkansas_available_products_total": registry.get("arkansas_available_products_total"),
        "missouri_bbox_coverage_pct": registry.get("missouri_bbox_coverage_pct"),
        "missouri_available_products_coverage_pct": registry.get("missouri_available_products_coverage_pct"),
        "missouri_available_products_processed": registry.get("missouri_available_products_processed"),
        "missouri_available_products_total": registry.get("missouri_available_products_total"),
        "indiana_bbox_coverage_pct": registry.get("indiana_bbox_coverage_pct"),
        "indiana_available_products_coverage_pct": registry.get("indiana_available_products_coverage_pct"),
        "indiana_available_products_processed": registry.get("indiana_available_products_processed"),
        "indiana_available_products_total": registry.get("indiana_available_products_total"),
        "illinois_bbox_coverage_pct": registry.get("illinois_bbox_coverage_pct"),
        "illinois_available_products_coverage_pct": registry.get("illinois_available_products_coverage_pct"),
        "illinois_available_products_processed": registry.get("illinois_available_products_processed"),
        "illinois_available_products_total": registry.get("illinois_available_products_total"),
        "michigan_bbox_coverage_pct": registry.get("michigan_bbox_coverage_pct"),
        "michigan_available_products_coverage_pct": registry.get("michigan_available_products_coverage_pct"),
        "michigan_available_products_processed": registry.get("michigan_available_products_processed"),
        "michigan_available_products_total": registry.get("michigan_available_products_total"),
        "wisconsin_bbox_coverage_pct": registry.get("wisconsin_bbox_coverage_pct"),
        "wisconsin_available_products_coverage_pct": registry.get("wisconsin_available_products_coverage_pct"),
        "wisconsin_available_products_processed": registry.get("wisconsin_available_products_processed"),
        "wisconsin_available_products_total": registry.get("wisconsin_available_products_total"),
        "minnesota_bbox_coverage_pct": registry.get("minnesota_bbox_coverage_pct"),
        "minnesota_available_products_coverage_pct": registry.get("minnesota_available_products_coverage_pct"),
        "minnesota_available_products_processed": registry.get("minnesota_available_products_processed"),
        "minnesota_available_products_total": registry.get("minnesota_available_products_total"),
        "iowa_bbox_coverage_pct": registry.get("iowa_bbox_coverage_pct"),
        "iowa_available_products_coverage_pct": registry.get("iowa_available_products_coverage_pct"),
        "iowa_available_products_processed": registry.get("iowa_available_products_processed"),
        "iowa_available_products_total": registry.get("iowa_available_products_total"),
        "north_dakota_bbox_coverage_pct": registry.get("north_dakota_bbox_coverage_pct"),
        "north_dakota_available_products_coverage_pct": registry.get("north_dakota_available_products_coverage_pct"),
        "north_dakota_available_products_processed": registry.get("north_dakota_available_products_processed"),
        "north_dakota_available_products_total": registry.get("north_dakota_available_products_total"),
        "south_dakota_bbox_coverage_pct": registry.get("south_dakota_bbox_coverage_pct"),
        "south_dakota_available_products_coverage_pct": registry.get("south_dakota_available_products_coverage_pct"),
        "south_dakota_available_products_processed": registry.get("south_dakota_available_products_processed"),
        "south_dakota_available_products_total": registry.get("south_dakota_available_products_total"),
        "nebraska_bbox_coverage_pct": registry.get("nebraska_bbox_coverage_pct"),
        "nebraska_available_products_coverage_pct": registry.get("nebraska_available_products_coverage_pct"),
        "nebraska_available_products_processed": registry.get("nebraska_available_products_processed"),
        "nebraska_available_products_total": registry.get("nebraska_available_products_total"),
        "kansas_bbox_coverage_pct": registry.get("kansas_bbox_coverage_pct"),
        "kansas_available_products_coverage_pct": registry.get("kansas_available_products_coverage_pct"),
        "kansas_available_products_processed": registry.get("kansas_available_products_processed"),
        "kansas_available_products_total": registry.get("kansas_available_products_total"),
        "oklahoma_bbox_coverage_pct": registry.get("oklahoma_bbox_coverage_pct"),
        "oklahoma_available_products_coverage_pct": registry.get("oklahoma_available_products_coverage_pct"),
        "oklahoma_available_products_processed": registry.get("oklahoma_available_products_processed"),
        "oklahoma_available_products_total": registry.get("oklahoma_available_products_total"),
        "texas_bbox_coverage_pct": registry.get("texas_bbox_coverage_pct"),
        "texas_available_products_coverage_pct": registry.get("texas_available_products_coverage_pct"),
        "texas_available_products_processed": registry.get("texas_available_products_processed"),
        "texas_available_products_total": registry.get("texas_available_products_total"),
        "new_mexico_bbox_coverage_pct": registry.get("new_mexico_bbox_coverage_pct"),
        "new_mexico_available_products_coverage_pct": registry.get("new_mexico_available_products_coverage_pct"),
        "new_mexico_available_products_processed": registry.get("new_mexico_available_products_processed"),
        "new_mexico_available_products_total": registry.get("new_mexico_available_products_total"),
        "colorado_bbox_coverage_pct": registry.get("colorado_bbox_coverage_pct"),
        "colorado_available_products_coverage_pct": registry.get("colorado_available_products_coverage_pct"),
        "colorado_available_products_processed": registry.get("colorado_available_products_processed"),
        "colorado_available_products_total": registry.get("colorado_available_products_total"),
        "wyoming_bbox_coverage_pct": registry.get("wyoming_bbox_coverage_pct"),
        "wyoming_available_products_coverage_pct": registry.get("wyoming_available_products_coverage_pct"),
        "wyoming_available_products_processed": registry.get("wyoming_available_products_processed"),
        "wyoming_available_products_total": registry.get("wyoming_available_products_total"),
        "montana_bbox_coverage_pct": registry.get("montana_bbox_coverage_pct"),
        "montana_available_products_coverage_pct": registry.get("montana_available_products_coverage_pct"),
        "montana_available_products_processed": registry.get("montana_available_products_processed"),
        "montana_available_products_total": registry.get("montana_available_products_total"),
        "idaho_bbox_coverage_pct": registry.get("idaho_bbox_coverage_pct"),
        "idaho_available_products_coverage_pct": registry.get("idaho_available_products_coverage_pct"),
        "idaho_available_products_processed": registry.get("idaho_available_products_processed"),
        "idaho_available_products_total": registry.get("idaho_available_products_total"),
        "utah_bbox_coverage_pct": registry.get("utah_bbox_coverage_pct"),
        "utah_available_products_coverage_pct": registry.get("utah_available_products_coverage_pct"),
        "utah_available_products_processed": registry.get("utah_available_products_processed"),
        "utah_available_products_total": registry.get("utah_available_products_total"),
        "arizona_bbox_coverage_pct": registry.get("arizona_bbox_coverage_pct"),
        "arizona_available_products_coverage_pct": registry.get("arizona_available_products_coverage_pct"),
        "arizona_available_products_processed": registry.get("arizona_available_products_processed"),
        "arizona_available_products_total": registry.get("arizona_available_products_total"),
        "nevada_bbox_coverage_pct": registry.get("nevada_bbox_coverage_pct"),
        "nevada_available_products_coverage_pct": registry.get("nevada_available_products_coverage_pct"),
        "nevada_available_products_processed": registry.get("nevada_available_products_processed"),
        "nevada_available_products_total": registry.get("nevada_available_products_total"),
        "california_bbox_coverage_pct": registry.get("california_bbox_coverage_pct"),
        "california_available_products_coverage_pct": registry.get("california_available_products_coverage_pct"),
        "california_available_products_processed": registry.get("california_available_products_processed"),
        "california_available_products_total": registry.get("california_available_products_total"),
        "oregon_bbox_coverage_pct": registry.get("oregon_bbox_coverage_pct"),
        "oregon_available_products_coverage_pct": registry.get("oregon_available_products_coverage_pct"),
        "oregon_available_products_processed": registry.get("oregon_available_products_processed"),
        "oregon_available_products_total": registry.get("oregon_available_products_total"),
        "washington_bbox_coverage_pct": registry.get("washington_bbox_coverage_pct"),
        "washington_available_products_coverage_pct": registry.get("washington_available_products_coverage_pct"),
        "washington_available_products_processed": registry.get("washington_available_products_processed"),
        "washington_available_products_total": registry.get("washington_available_products_total"),
        "new_hampshire_bbox_coverage_pct": registry.get("new_hampshire_bbox_coverage_pct"),
        "new_hampshire_available_products_coverage_pct": registry.get("new_hampshire_available_products_coverage_pct"),
        "new_hampshire_available_products_processed": registry.get("new_hampshire_available_products_processed"),
        "new_hampshire_available_products_total": registry.get("new_hampshire_available_products_total"),
        "hawaii_bbox_coverage_pct": registry.get("hawaii_bbox_coverage_pct"),
        "hawaii_available_products_coverage_pct": registry.get("hawaii_available_products_coverage_pct"),
        "hawaii_available_products_processed": registry.get("hawaii_available_products_processed"),
        "hawaii_available_products_total": registry.get("hawaii_available_products_total"),
        "alaska_bbox_coverage_pct": registry.get("alaska_bbox_coverage_pct"),
        "alaska_available_products_coverage_pct": registry.get("alaska_available_products_coverage_pct"),
        "alaska_available_products_processed": registry.get("alaska_available_products_processed"),
        "alaska_available_products_total": registry.get("alaska_available_products_total"),
        "total_tile_count": registry.get("total_tile_count", 0),
        "downloaded": sum(1 for s in active_sources if s.get("raw_file_path") and Path(s["raw_file_path"]).exists()),
        "processed": sum(1 for s in active_sources if s.get("processing_status") == "processed"),
        "active_tilejson": active,
    }


@app.get("/api/reliefs/terrain/jobs/status")
def api_reliefs_terrain_jobs_status():
    return terrain_coverage_registry().get("last_job") or {"status": "not run"}


@app.post("/api/location/override")
async def api_location_override(payload: dict[str, Any]):
    if not payload.get("id") or not isinstance(payload.get("lat"), (int, float)) or not isinstance(payload.get("lng"), (int, float)):
        return JSONResponse({"error": "id, lat, lng required"}, status_code=400)
    rows = load_json(OVERRIDES, {})
    rows[payload["id"]] = payload
    OVERRIDES.write_text(json.dumps(rows, indent=2) + "\n")
    return {"ok": True, "id": payload["id"]}


def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(v: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", v).strip("_")[:120] or "report"


def source_url(row: dict) -> str | None:
    return row.get("source_url") or row.get("public_url") or row.get("listing_url") or row.get("public_source_url")


def source_date(row: dict) -> str | None:
    return row.get("source_date") or row.get("updated_at") or row.get("last_updated") or row.get("listed_date") or row.get("as_of_date")


def evidence_row(
    linked_object_type: str,
    linked_object_id: str,
    claim_type: str,
    claim_value: Any,
    source: dict | str | None,
    confidence: Any = None,
    extraction_method: str = "structured_public_seed",
    notes: str = "",
) -> dict:
    source_dict = source if isinstance(source, dict) else {}
    source_name = source_dict.get("source_name") or source_dict.get("source") or (source if isinstance(source, str) else None) or "source pending"
    conf = confidence if confidence is not None else source_dict.get("confidence")
    raw_status = source_dict.get("evidence_status") or source_dict.get("claim_status")
    status = raw_status if raw_status in {"confirmed", "inferred", "estimated", "user_override"} else ("confirmed" if num(conf, 0) >= 0.8 else "inferred")
    stable = f"{linked_object_type}:{linked_object_id}:{claim_type}:{source_name}:{str(claim_value)[:48]}"
    return {
        "id": "ev:" + slug(stable),
        "linked_object_type": linked_object_type,
        "linked_object_id": linked_object_id,
        "claim_type": claim_type,
        "claim_value": claim_value,
        "source_name": source_name,
        "source_url": source_url(source_dict),
        "source_document_id": source_dict.get("source_document_id") or source_dict.get("id"),
        "source_date": source_date(source_dict),
        "retrieved_at": source_dict.get("retrieved_at") or today(),
        "confidence": conf,
        "extraction_method": source_dict.get("extraction_method") or extraction_method,
        "notes": notes or source_dict.get("notes") or "",
        "status": status,
    }


def add_evidence(rows: list[dict], kind: str, oid: str | None, claims: dict[str, Any], source: dict | str | None, confidence: Any = None, notes: str = "") -> None:
    if not oid:
        return
    for claim_type, claim_value in claims.items():
        if claim_value in (None, "", []):
            continue
        rows.append(evidence_row(kind, oid, claim_type, claim_value, source, confidence, notes=notes))


def generated_evidence() -> list[dict]:
    data = intel()
    rows: list[dict] = []
    for e in data.get("entities", []):
        add_evidence(rows, "entity", e.get("id"), {"identity": e.get("name") or e.get("n"), "ticker": e.get("ticker") or e.get("t"), "sector": e.get("sector")}, e, e.get("confidence") or e.get("source_confidence"))
    for asset in data.get("assets", []):
        location = ", ".join(str(x) for x in [asset.get("address"), asset.get("city"), asset.get("state"), asset.get("country")] if x)
        add_evidence(rows, "asset", asset.get("id"), {
            "asset_type": asset.get("asset_type"),
            "location": location,
            "acreage": asset.get("area_acres"),
            "ownership": asset.get("owner_entity_id"),
            "operator": asset.get("operator_entity_id"),
        }, asset, asset.get("confidence"))
    for rel in data.get("asset_relationships", []):
        add_evidence(rows, "relationship", rel.get("id"), {"relationship": f"{rel.get('source_id')} {rel.get('relationship_type')} {rel.get('target_id')}"}, rel, rel.get("confidence"), notes=f"Status: {rel.get('status', 'inferred')}")
    for permit in data.get("permits", []):
        add_evidence(rows, "permit", permit.get("id"), {"government_approval": permit.get("approval_status"), "permit_cost": permit.get("estimated_cost"), "permit_type": permit.get("permit_type")}, permit, permit.get("confidence"))
        add_evidence(rows, "asset", permit.get("asset_id"), {"government_approval": permit.get("approval_status"), "permit_cost": permit.get("estimated_cost")}, permit, permit.get("confidence"))
    for farm in data.get("farm_profiles", []):
        add_evidence(rows, "asset", farm.get("asset_id"), {
            "crop_history": farm.get("crop_history"),
            "soil_quality": farm.get("soil_quality"),
            "water_access": farm.get("water_access"),
            "acreage": farm.get("acres"),
            "annual_yield": farm.get("estimated_yield"),
            "sale_price": farm.get("last_sale_price"),
            "current_estimated_value": farm.get("current_estimated_value"),
            "risk_score": farm.get("risk_score"),
        }, farm, farm.get("confidence"))
    for industrial in data.get("industrial_profiles", []):
        add_evidence(rows, "asset", industrial.get("asset_id"), {
            "project_cost": industrial.get("estimated_project_cost"),
            "power_capacity": industrial.get("power_capacity_mw"),
            "annual_revenue": industrial.get("revenue_estimate"),
            "operating_cost": industrial.get("operating_cost_estimate"),
            "risk_score": industrial.get("risk_score"),
        }, industrial, industrial.get("confidence"))
    for listing in data.get("asset_listings", []):
        add_evidence(rows, "listing", listing.get("id"), {
            "listing_price": listing.get("price"),
            "acreage": listing.get("acreage"),
            "listing_status": listing.get("listing_status"),
            "current_estimated_value": listing.get("current_estimated_value"),
            "flood_risk": listing.get("flood_risk"),
            "environmental_risk": listing.get("environmental_risk"),
            "crime_aggregate": listing.get("crime_aggregate_score"),
        }, listing, listing.get("confidence"))
        add_evidence(rows, "asset", listing.get("asset_id"), {"listing_price": listing.get("price"), "listing_status": listing.get("listing_status")}, listing, listing.get("confidence"))
    for camera in data.get("cameras", []):
        if camera.get("legal_public_access") is True:
            add_evidence(rows, "camera", camera.get("id"), {"public_camera_source": camera.get("source_url") or camera.get("name")}, camera, camera.get("confidence"))
    for feature in data.get("layer_features", []):
        add_evidence(rows, "layer_feature", feature.get("id"), {feature.get("layer_type") or "layer_feature": feature.get("name")}, feature, feature.get("confidence"))
    for asset in data.get("assets", []):
        try:
            valuation = valuation_model(asset["id"])
        except Exception:
            continue
        model_source = {"source": "deterministic valuation model", "updated_at": today(), "confidence": valuation.get("confidence_score")}
        add_evidence(rows, "valuation", asset["id"], {"current_estimated_value": valuation.get("estimated_current_value"), "annual_revenue": valuation.get("estimated_annual_revenue"), "risk_score": valuation.get("risk_score")}, model_source, valuation.get("confidence_score"), "Modeled estimate, not a fact or guarantee.")
        add_evidence(rows, "risk_score", asset["id"], {"risk_score": valuation.get("risk_score"), "score_breakdown": valuation.get("score_breakdown")}, model_source, valuation.get("confidence_score"), "Deterministic scoring from public/mock fields and assumptions.")
    dedup = {}
    for row in rows:
        dedup[row["id"]] = row
    return sorted(dedup.values(), key=lambda r: (r["linked_object_type"], r["linked_object_id"], r["claim_type"]))


def user_override_rows() -> list[dict]:
    return load_json(USER_OVERRIDES, [])


def save_user_overrides(rows: list[dict]) -> None:
    USER_OVERRIDES.write_text(json.dumps(rows, indent=2) + "\n")


def is_stale(row: dict) -> bool:
    raw = row.get("source_date") or row.get("retrieved_at")
    if not raw:
        return True
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            return True
    return (date.today() - d).days > 365


def quality_summary() -> dict:
    data = intel()
    evidence = generated_evidence()
    rels = data.get("asset_relationships", [])
    assets = data.get("assets", [])
    valuation_missing = 0
    for asset in assets:
        try:
            if valuation_model(asset["id"]).get("missing_data_fields"):
                valuation_missing += 1
        except Exception:
            valuation_missing += 1
    owned_asset_ids = {r.get("target_id") for r in rels if r.get("relationship_type") == "OWNS"}
    return {
        "total_entities": len(universe_nodes()) + len(data.get("entities", [])),
        "total_assets": len(assets),
        "total_relationships": len(map_relationships()["features"]) + len(rels),
        "total_evidence_records": len(evidence),
        "assets_missing_location": sum(1 for a in assets if not geom(a)),
        "assets_missing_owner": sum(1 for a in assets if not a.get("owner_entity_id") and a.get("id") not in owned_asset_ids),
        "assets_missing_valuation": valuation_missing,
        "low_confidence_relationships": sum(1 for r in rels if num(r.get("confidence"), 0) < 0.5),
        "stale_records": sum(1 for r in evidence if is_stale(r)),
        "records_needing_review": sum(1 for r in evidence if not r.get("source_name") or num(r.get("confidence"), 0) < 0.5 or is_stale(r)),
        "generated_at": now_iso(),
    }


def layer_quality(layer_name: str) -> dict:
    data = intel()
    assets = data.get("assets", [])
    listings = data.get("asset_listings", [])
    permits = data.get("permits", [])
    farms = [a for a in assets if a.get("asset_type") in {"farm", "agricultural_complex", "parcel"}]
    industrial = [a for a in assets if a.get("asset_type") in {"data_center", "factory", "industrial_complex", "power_plant", "hydro_facility"}]
    farm_profiles = {p.get("asset_id"): p for p in data.get("farm_profiles", [])}
    industrial_profiles = {p.get("asset_id"): p for p in data.get("industrial_profiles", [])}
    metrics = {
        "farms_loaded": len(farms),
        "farms_missing_acres": sum(1 for a in farms if not (a.get("area_acres") or farm_profiles.get(a.get("id"), {}).get("acres"))),
        "farms_missing_last_sale_price": sum(1 for a in farms if not farm_profiles.get(a.get("id"), {}).get("last_sale_price")),
        "industrial_assets_missing_project_cost": sum(1 for a in industrial if not industrial_profiles.get(a.get("id"), {}).get("estimated_project_cost")),
        "data_centers_missing_power_capacity": sum(1 for a in industrial if a.get("asset_type") == "data_center" and not industrial_profiles.get(a.get("id"), {}).get("power_capacity_mw")),
        "government_facilities_missing_source": sum(1 for a in assets if a.get("asset_type") == "government_facility" and not a.get("source")),
        "listings_missing_geometry": sum(1 for l in listings if not listing_geometry(l)),
        "permits_missing_public_url": sum(1 for p in permits if not p.get("public_url")),
    }
    return {"layer_name": layer_name, "metrics": metrics, "generated_at": now_iso()}


def report_payload(object_type: str, object_id: str) -> dict:
    sections: dict[str, Any] = {}
    if object_type == "entity":
        obj = entity(object_id) or {}
        if not obj:
            raise HTTPException(404, "entity not found")
        sections["assets"] = entity_asset_rows(object_id)
        sections["relationship_graph"] = neighborhood(object_id, 1)
    elif object_type == "listing":
        obj = next((r for r in intel().get("asset_listings", []) if r.get("id") == object_id), None)
        if not obj:
            raise HTTPException(404, "listing not found")
        if obj.get("asset_id"):
            sections["asset"] = asset_profile(obj["asset_id"])
            sections["valuation"] = valuation_model(obj["asset_id"])
    else:
        obj = asset_profile(object_id)
        sections["permits"] = obj.get("permits", [])
        sections["relationship_graph"] = api_asset_relationship_graph(object_id)
        sections["nearby_infrastructure"] = api_asset_nearby_infrastructure(object_id)
        sections["risk_summary"] = api_asset_risk_summary(object_id)
        sections["valuation"] = valuation_model(object_id)
        sections["scenarios"] = {case: valuation_model(object_id, case) for case in ("bear", "base", "bull")}
    evidence = [
        r for r in generated_evidence()
        if (r["linked_object_type"] == object_type and r["linked_object_id"] == object_id)
        or (object_type == "asset" and r["linked_object_type"] in {"valuation", "risk_score"} and r["linked_object_id"] == object_id)
    ]
    missing = sorted({x for x in sections.get("valuation", {}).get("missing_data_fields", []) if x})
    confidences = [num(r.get("confidence"), None) for r in evidence]
    confidences = [x for x in confidences if x is not None]
    return {
        "report_id": None,
        "object_type": object_type,
        "object_id": object_id,
        "report_type": {"asset": "asset due-diligence report", "listing": "acquisition listing report", "entity": "company asset exposure report"}.get(object_type, "due-diligence report"),
        "executive_summary": f"Non-AI due-diligence report for {obj.get('name') or obj.get('title') or object_id}. Values are sourced, modeled, inferred, or missing as labeled.",
        "overview": obj,
        "location_map_screenshot": "placeholder: capture current MapLibre viewport in production export",
        "sections": sections,
        "evidence_source_appendix": evidence,
        "missing_data_appendix": missing,
        "confidence_score": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "generated_at": now_iso(),
    }


def report_html(report: dict) -> str:
    def block(title: str, value: Any) -> str:
        return f"<h2>{html_escape(title)}</h2><pre>{html_escape(json.dumps(value, indent=2, default=str))}</pre>"
    return "<!doctype html><html><head><meta charset='utf-8'><title>Due Diligence Report</title><style>body{font:14px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#0b0f16;color:#e8edf4;padding:28px;line-height:1.45}pre{white-space:pre-wrap;background:#151b24;border:1px solid #2a303a;border-radius:8px;padding:14px}.tag{display:inline-block;padding:3px 8px;border:1px solid #2a303a;border-radius:999px;color:#9aa6b6}</style></head><body>" + f"<h1>{html_escape(report['report_type'].title())}</h1><p>{html_escape(report['executive_summary'])}</p><p class='tag'>Confidence: {html_escape(str(report.get('confidence_score') or 'pending'))}</p>" + block("Overview", report.get("overview")) + block("Ownership / Permits / Infrastructure / Risks / Valuation", report.get("sections")) + block("Evidence Appendix", report.get("evidence_source_appendix")) + block("Missing Data Appendix", report.get("missing_data_appendix")) + "</body></html>"


def write_report_exports(report: dict) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = slug(f"{report['object_type']}_{report['object_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    report["report_id"] = report_id
    base = REPORTS_DIR / report_id
    base.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    base.with_suffix(".html").write_text(report_html(report))
    fields = ["id", "linked_object_type", "linked_object_id", "claim_type", "claim_value", "source_name", "source_url", "source_date", "retrieved_at", "confidence", "status", "notes"]
    with base.with_suffix(".csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in report.get("evidence_source_appendix", []):
            writer.writerow({k: json.dumps(row.get(k)) if isinstance(row.get(k), (list, dict)) else row.get(k) for k in fields})
    return {"report_id": report_id, "html": f"/api/reports/{report_id}/download?format=html", "json": f"/api/reports/{report_id}/download?format=json", "csv": f"/api/reports/{report_id}/download?format=csv", "pdf": "placeholder"}


@app.get("/api/evidence")
def api_evidence(object_type: str | None = None, object_id: str | None = None):
    rows = generated_evidence()
    if object_type:
        wanted = {object_type}
        if object_type == "asset":
            wanted |= {"valuation", "risk_score"}
        rows = [r for r in rows if r.get("linked_object_type") in wanted]
    if object_id:
        rows = [r for r in rows if r.get("linked_object_id") == object_id]
    return {"evidence": rows}


@app.get("/api/evidence/{evidence_id}")
def api_evidence_one(evidence_id: str):
    row = next((r for r in generated_evidence() if r["id"] == unquote(evidence_id)), None)
    if not row:
        raise HTTPException(404, "evidence not found")
    return row


@app.get("/api/data-quality/summary")
def api_data_quality_summary():
    return quality_summary()


@app.get("/api/data-quality/layer/{layer_name}")
def api_data_quality_layer(layer_name: str):
    return layer_quality(unquote(layer_name))


@app.post("/api/overrides")
async def api_post_override(payload: dict[str, Any]):
    if any(payload.get(k) in (None, "") for k in ["object_type", "object_id", "field_name", "new_value"]):
        raise HTTPException(400, "object_type, object_id, field_name, and new_value are required")
    rows = user_override_rows()
    row = {
        "id": f"override:{slug(str(payload['object_type']))}:{slug(str(payload['object_id']))}:{slug(str(payload['field_name']))}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "object_type": payload["object_type"],
        "object_id": payload["object_id"],
        "field_name": payload["field_name"],
        "old_value": payload.get("old_value"),
        "new_value": payload.get("new_value"),
        "user_note": payload.get("user_note") or "",
        "created_at": now_iso(),
        "review_status": payload.get("review_status") or "pending",
    }
    rows.append(row)
    save_user_overrides(rows)
    return {"ok": True, "override": row}


@app.get("/api/overrides")
def api_overrides(object_type: str | None = None, object_id: str | None = None):
    rows = user_override_rows()
    if object_type:
        rows = [r for r in rows if r.get("object_type") == object_type]
    if object_id:
        rows = [r for r in rows if r.get("object_id") == object_id]
    return {"overrides": rows}


@app.delete("/api/overrides/{override_id}")
def api_delete_override(override_id: str):
    oid = unquote(override_id)
    rows = user_override_rows()
    kept = [r for r in rows if r.get("id") != oid]
    if len(kept) == len(rows):
        raise HTTPException(404, "override not found")
    save_user_overrides(kept)
    return {"ok": True, "id": oid}


@app.get("/api/reports/{report_id}/download")
def api_report_download(report_id: str, format: str = "html"):
    ext = {"html": ".html", "json": ".json", "csv": ".csv", "pdf": ".html"}.get(format, ".html")
    path = REPORTS_DIR / f"{slug(unquote(report_id))}{ext}"
    if not path.exists():
        raise HTTPException(404, "report export not found")
    media = {"html": "text/html", "json": "application/json", "csv": "text/csv", "pdf": "text/html"}.get(format, "text/html")
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/api/reports/{object_type}/{object_id}")
def api_report_preview(object_type: str, object_id: str):
    return report_payload(unquote(object_type), unquote(object_id))


@app.post("/api/reports/{object_type}/{object_id}/generate")
async def api_report_generate(object_type: str, object_id: str, payload: dict[str, Any] | None = None):
    report = report_payload(unquote(object_type), unquote(object_id))
    if payload:
        report["requested_sections"] = payload.get("sections")
        report["requested_report_type"] = payload.get("report_type")
    return {"ok": True, **write_report_exports(report)}


app.mount("/", StaticFiles(directory=str(ROOT / "graph"), html=True), name="graph")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8788)


if __name__ == "__main__":
    main()

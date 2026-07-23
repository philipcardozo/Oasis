from __future__ import annotations

import json
import csv
import gzip
import hashlib
import re
import os
import threading
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timezone
from functools import lru_cache
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from oasis_paths import raw_data_root
from data_sources import (
    METADATA_PATH,
    TERRAIN_COVERAGE_PATH,
    TILEJSON_PATH,
    UNIFIED_TILEJSON_PATH,
    dem_path,
    dem_tilejson,
    terrain_coverage_registry,
    validation_status,
)
from store import EDGES as STORE_EDGES, NODES as STORE_NODES, aliases as store_aliases, by_id as store_by_id, node_count as store_node_count

try:
    import ujson as fast_json
except ImportError:  # pragma: no cover - optional local speedup
    fast_json = json

ROOT = Path(__file__).parent
DATA = ROOT / "graph" / "data"
INTEL = DATA / "map_intelligence.json"
OVERRIDES = DATA / "location_overrides.json"
VALUATION_ASSUMPTIONS = DATA / "valuation_assumptions.json"
USER_OVERRIDES = DATA / "user_overrides.json"
REPORTS_DIR = DATA / "reports"
WATCHLISTS = DATA / "watchlists.json"
COMPANYFACTS = DATA / "companyfacts"
EVENTS = ROOT / "data" / "store" / "events.parquet"
POL_MEMBERS = ROOT / "data" / "store" / "pol_members.parquet"
POL_TRADES = ROOT / "data" / "store" / "pol_trades.parquet"
COMMITTEE_POLICY_MAP = DATA / "committee_policy_map.json"
GOV_CONTRACTS = DATA / "gov_contracts.json"
RAW_DATA_ROOT = raw_data_root()  # cross-platform; OASIS_RAW_DATA_ROOT overrides
RAW_FEEDS = {
    "usgs_3dep": {"source_layer": "relief_features", "default_layer": "relief-terrain"},
    "eia": {"source_layer": "industrial_assets", "default_layer": "industrial-energy"},
    "fbi_crime": {"source_layer": "relief_features", "default_layer": "relief-crime"},
}
FULL_WORLD_BBOX = (-180.0, -90.0, 180.0, 90.0)


@asynccontextmanager
async def oasis_lifespan(app: FastAPI):
    warm_startup_caches()
    start_background_warm_caches()
    yield


app = FastAPI(title="Oasis Map Intelligence API", lifespan=oasis_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)


STATIC_JSON = {
    "aliases.json",
    "companies.geojson",
    "edge_candidates.json",
    "graph-index.json",
    "hq_coords.json",
    "location_unknown.json",
    "map_intelligence.json",
    "news.json",
    "relationships.geojson",
    "securities.geojson",
}


@lru_cache(maxsize=16)
def _load_json_cached(path: str, mtime: float):
    return fast_json.loads(Path(path).read_bytes())


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


def path_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0


def latest_mtime(path: Path, pattern: str = "*") -> float:
    if not path.exists():
        return 0
    if path.is_file():
        return path_mtime(path)
    latest = path.stat().st_mtime
    for child in path.glob(pattern):
        if child.is_file():
            latest = max(latest, child.stat().st_mtime)
    return latest



def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def compact_json_bytes(payload: Any) -> bytes:
    if fast_json is json:
        return json.dumps(payload, separators=(",", ":")).encode()
    return fast_json.dumps(payload).encode()


def gzip_api_bytes(raw: bytes) -> bytes:
    level = 4 if len(raw) > 1_000_000 else 3
    return gzip.compress(raw, compresslevel=level)


def cache_etag(key: str, *parts: Any) -> str:
    digest = hashlib.sha1("|".join(str(p) for p in (key, *parts)).encode()).hexdigest()[:16]
    return f'W/"oasis-{digest}"'


def request_has_etag(request: Request, etag: str) -> bool:
    return any(tag.strip() in {etag, "*"} for tag in request.headers.get("if-none-match", "").split(","))


def cached_bytes_response(
    request: Request,
    raw: bytes,
    gzipped: bytes,
    media_type: str,
    etag: str,
    cache_control: str = "public, max-age=60, must-revalidate",
) -> Response:
    base_headers = {"ETag": etag, "Vary": "Accept-Encoding", "Cache-Control": cache_control}
    if request_has_etag(request, etag):
        return Response(status_code=304, headers=base_headers)
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        return Response(
            gzipped,
            media_type=media_type,
            headers={**base_headers, "Content-Encoding": "gzip"},
        )
    return Response(raw, media_type=media_type, headers=base_headers)


def not_modified_response(request: Request, etag: str, cache_control: str = "public, max-age=60, must-revalidate") -> Response | None:
    headers = {"ETag": etag, "Vary": "Accept-Encoding", "Cache-Control": cache_control}
    if request_has_etag(request, etag):
        return Response(status_code=304, headers=headers)
    return None


@lru_cache(maxsize=8)
def _static_asset_bytes_cached(path: str, mtime: float):
    raw = Path(path).read_bytes()
    return raw, gzip.compress(raw, compresslevel=6)


def cached_static_data_response(name: str, request: Request, media_type: str = "application/json") -> Response:
    path = DATA / name
    mtime = path_mtime(path)
    raw, gzipped = _static_asset_bytes_cached(str(path), mtime)
    return cached_bytes_response(request, raw, gzipped, media_type, cache_etag(name, mtime, len(raw)))


def cached_graph_asset_response(
    relative_path: str,
    request: Request,
    media_type: str,
    cache_control: str = "public, max-age=31536000, immutable",
) -> Response:
    path = ROOT / "graph" / relative_path
    mtime = path_mtime(path)
    raw, gzipped = _static_asset_bytes_cached(str(path), mtime)
    return cached_bytes_response(
        request,
        raw,
        gzipped,
        media_type,
        cache_etag(relative_path, mtime, len(raw)),
        cache_control=cache_control,
    )


def file_etag(path: Path) -> str:
    stat = path.stat()
    return f'"{hashlib.md5(f"{stat.st_mtime}-{stat.st_size}".encode(), usedforsecurity=False).hexdigest()}"'


def conditional_file_response(request: Request, path: Path, media_type: str, filename: str | None = None) -> Response:
    etag = file_etag(path)
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60, must-revalidate"}
    if request_has_etag(request, etag):
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type=media_type, filename=filename, headers=headers)


def terrain_status_cache_parts() -> tuple:
    dem = dem_path()
    return (
        path_mtime(TERRAIN_COVERAGE_PATH),
        path_mtime(METADATA_PATH),
        path_mtime(UNIFIED_TILEJSON_PATH),
        path_mtime(TILEJSON_PATH),
        str(dem),
        path_mtime(dem),
        os.environ.get("EIA_API_KEY", ""),
        os.environ.get("DATA_GOV_API_KEY", ""),
        os.environ.get("TNM_ACCESS_PRODUCTS_URL", ""),
        os.environ.get("USGS_3DEP_DEM_PATH", ""),
    )


@lru_cache(maxsize=16)
def _json_payload_cached(cache_name: str, parts: tuple):
    if cache_name == "data-sources-status":
        payload = validation_status()
    elif cache_name == "reliefs-dem-status":
        status = validation_status()
        payload = status["dem"] | {"checks": status["checks"], "sources": status["sources"]}
    elif cache_name == "reliefs-terrain-sources":
        registry = terrain_coverage_registry()
        payload = {
            "active_source": registry.get("active_source"),
            "active_tilejson": registry.get("active_tilejson"),
            "sources": registry.get("sources", []),
        }
    elif cache_name == "reliefs-terrain-coverage":
        payload = terrain_coverage_payload()
    elif cache_name == "reliefs-terrain-jobs":
        payload = terrain_coverage_registry().get("last_job") or {"status": "not run"}
    else:
        payload = {}
    raw = compact_json_bytes(payload)
    return raw, gzip_api_bytes(raw)


def cached_json_payload_response(cache_name: str, request: Request) -> Response:
    parts = terrain_status_cache_parts()
    raw, gzipped = _json_payload_cached(cache_name, parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag(cache_name, *parts, len(raw)))


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


def feature_collection_bytes_from_files(paths: tuple[Path, ...]) -> bytes:
    parts = []
    for path in paths:
        raw = path.read_bytes().strip()
        key = raw.find(b'"features"')
        start = raw.find(b"[", key)
        end = raw.rfind(b"]")
        if key < 0 or start < 0 or end < start or raw[end + 1:].strip() != b"}":
            raise ValueError(f"{path.name} is not a supported FeatureCollection")
        body = raw[start + 1:end].strip()
        if body:
            parts.append(body)
    return b'{"type":"FeatureCollection","features":[' + b",".join(parts) + b"]}"


@lru_cache(maxsize=4)
def _map_entities_json_cached(companies_mtime: float, securities_mtime: float):
    raw = feature_collection_bytes_from_files((DATA / "companies.geojson", DATA / "securities.geojson"))
    return raw, gzip_api_bytes(raw)


def map_relationships(bbox: list[float] | None = None) -> dict:
    features = load_json("relationships.geojson", feature_collection([]))["features"]
    if bbox:
        features = [f for f in features if any(in_bbox(c, bbox) for c in f["geometry"]["coordinates"])]
    return feature_collection(features)


@lru_cache(maxsize=4)
def _map_relationships_json_cached(relationships_mtime: float):
    raw = (DATA / "relationships.geojson").read_bytes().strip()
    return raw, gzip_api_bytes(raw)


def universe_nodes() -> dict[str, dict]:
    return store_by_id()


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


@lru_cache(maxsize=4)
def _intel_indexes_cached(mtime: float):
    data = intel()
    relationships_by_object: dict[str, list[dict]] = {}
    for rel in data.get("asset_relationships", []):
        for key in (rel.get("source_id"), rel.get("target_id")):
            if key:
                relationships_by_object.setdefault(key, []).append(rel)
    return {
        "entities_by_id": {r.get("id"): r for r in data.get("entities", []) if r.get("id")},
        "assets_by_id": {r.get("id"): r for r in data.get("assets", []) if r.get("id")},
        "farm_by_asset": {r.get("asset_id"): r for r in data.get("farm_profiles", []) if r.get("asset_id")},
        "industrial_by_asset": {r.get("asset_id"): r for r in data.get("industrial_profiles", []) if r.get("asset_id")},
        "permits_by_asset": group_by_key(data.get("permits", []), "asset_id"),
        "listings_by_asset": group_by_key(data.get("asset_listings", []), "asset_id"),
        "relationships_by_object": relationships_by_object,
    }


def group_by_key(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        value = row.get(key)
        if value:
            out.setdefault(value, []).append(row)
    return out


def intel_indexes():
    return _intel_indexes_cached(path_mtime(INTEL))


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


NON_ENTITY_ID_PREFIXES = ("asset:", "listing:", "layer:", "permit:", "assetrel:")


def entity(entity_id: str | None) -> dict | None:
    if not entity_id:
        return None
    row = intel_entity(entity_id)
    if row:
        return row
    if entity_id.startswith(NON_ENTITY_ID_PREFIXES):
        return None
    n = universe_nodes().get(entity_id)
    if n:
        return entity_from_universe_node(n)
    return universe_entity(entity_id)


def intel_entity(entity_id: str) -> dict | None:
    return _intel_entities_by_id_cached(path_mtime(INTEL)).get(entity_id)


@lru_cache(maxsize=4)
def _intel_entities_by_id_cached(intel_mtime: float) -> dict[str, dict]:
    return {
        row["id"]: row
        for row in load_static_json(str(INTEL)).get("entities", [])
        if row.get("id")
    }


def entity_from_universe_node(n: dict) -> dict:
    return {
        "id": n["id"],
        "name": n.get("n"),
        "entity_type": n.get("kind"),
        "ticker": n.get("t"),
        "lei": n.get("lei"),
        "cik": n.get("cik"),
        "country": n.get("country"),
        "sector": n.get("sector"),
        "source": "data/store/nodes.parquet",
        "confidence": n.get("source_confidence"),
        "updated_at": n.get("as_of"),
    }


def universe_entity(entity_id: str) -> dict | None:
    path = DATA / "universe_bulk.json"
    nodes = _universe_nodes_by_id_cached(str(path), path_mtime(path))
    row = nodes.get(entity_id)
    return entity_from_universe_node(row) if row else None


@lru_cache(maxsize=4)
def _universe_nodes_by_id_cached(path: str, mtime: float) -> dict[str, dict]:
    data = load_static_json(path)
    return {row["id"]: row for row in data.get("nodes", []) if row.get("id")}


def entity_display_names(entity_ids: set[str]) -> dict[str, str]:
    indexes = _intel_entities_by_id_cached(path_mtime(INTEL))
    names = {
        entity_id: row.get("name") or entity_id
        for entity_id in entity_ids
        if (row := indexes.get(entity_id))
    }
    universe_names = universe_display_names()
    names.update({
        entity_id: universe_names.get(entity_id, entity_id)
        for entity_id in entity_ids - set(names)
    })
    return names


def universe_display_names() -> dict[str, str]:
    path = DATA / "universe_bulk.json"
    return _universe_display_names_cached(str(path), path_mtime(path))


@lru_cache(maxsize=4)
def _universe_display_names_cached(path: str, mtime: float) -> dict[str, str]:
    data = load_static_json(path)
    return {
        row["id"]: row.get("n") or row["id"]
        for row in data.get("nodes", [])
        if row.get("id")
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
    index = intel_indexes()["relationships_by_object"]
    if asset_id:
        rows = list(index.get(asset_id, []))
    elif entity_id:
        rows = list(index.get(entity_id, []))
    else:
        rows = intel().get("asset_relationships", [])
    if asset_id:
        rows = [r for r in rows if r.get("target_id") == asset_id or r.get("source_id") == asset_id]
    if entity_id:
        rows = [r for r in rows if r.get("source_id") == entity_id or r.get("target_id") == entity_id]
    return rows


def asset_entities(asset_id: str) -> dict:
    asset = intel_indexes()["assets_by_id"].get(asset_id, {}) or {}
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
    if not bbox:
        return _features_for_layer_cached(layer, path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"))
    return _features_for_layer(layer, bbox)


@lru_cache(maxsize=64)
def _features_for_layer_cached(layer: str, intel_mtime: float, universe_mtime: float) -> dict:
    return _features_for_layer(layer)


@lru_cache(maxsize=64)
def _features_for_layer_json_cached(layer: str, intel_mtime: float, universe_mtime: float):
    raw = compact_json_bytes(_features_for_layer_cached(layer, intel_mtime, universe_mtime))
    return raw, gzip_api_bytes(raw)


def _features_for_layer(layer: str, bbox: list[float] | None = None) -> dict:
    data = intel()
    indexes = intel_indexes()
    assets = indexes["assets_by_id"]
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

    candidate_assets = [asset for asset in data["assets"] if asset_source(asset) in wanted]
    display_ids = {
        entity_id
        for asset in candidate_assets
        for entity_id in (asset.get("owner_entity_id"), asset.get("operator_entity_id"))
        if entity_id
    }
    display_names = entity_display_names(display_ids)

    for asset in candidate_assets:
        farm = indexes["farm_by_asset"].get(asset["id"])
        industrial = indexes["industrial_by_asset"].get(asset["id"])
        permits = indexes["permits_by_asset"].get(asset["id"], [])
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
                    "owner_name": display_names.get(asset.get("owner_entity_id")) or asset.get("owner_entity_id"),
                    "operator_name": display_names.get(asset.get("operator_entity_id")) or asset.get("operator_entity_id"),
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
    assets = intel_indexes()["assets_by_id"]
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
    indexes = intel_indexes()
    asset = indexes["assets_by_id"].get(asset_id)
    if not asset:
        raise HTTPException(404, "asset not found")
    farm = indexes["farm_by_asset"].get(asset_id)
    industrial = indexes["industrial_by_asset"].get(asset_id)
    permits = indexes["permits_by_asset"].get(asset_id, [])
    listings = indexes["listings_by_asset"].get(asset_id, [])
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


def asset_model_profile(asset_id: str) -> dict:
    indexes = intel_indexes()
    asset = indexes["assets_by_id"].get(asset_id)
    if not asset:
        raise HTTPException(404, "asset not found")
    return {
        **asset,
        "permits": indexes["permits_by_asset"].get(asset_id, []),
        "listings": indexes["listings_by_asset"].get(asset_id, []),
        "farm_profile": indexes["farm_by_asset"].get(asset_id),
        "industrial_profile": indexes["industrial_by_asset"].get(asset_id),
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
    if VALUATION_ASSUMPTIONS.exists():
        return load_static_json(str(VALUATION_ASSUMPTIONS))
    return {}


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
    profile = asset_model_profile(asset_id)
    return asset_assumptions_for_profile(asset_id, profile, case)


def asset_assumptions_for_profile(asset_id: str, profile: dict, case: str = "base") -> dict:
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
    profile = asset_model_profile(asset_id)
    return valuation_model_for_profile(asset_id, profile, case)


def valuation_model_for_profile(asset_id: str, profile: dict, case: str = "base") -> dict:
    listing, farm, industrial = first_listing(profile), profile.get("farm_profile") or {}, profile.get("industrial_profile") or {}
    assumptions = asset_assumptions_for_profile(asset_id, profile, case)
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
def api_layers(request: Request):
    raw, gzipped = _map_layers_json_cached()
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-layers", hashlib.sha1(raw).hexdigest()[:16], len(raw)))


@lru_cache(maxsize=1)
def _map_layers_json_cached():
    raw = compact_json_bytes({
        "groups": LAYER_GROUPS,
        "sources": ["relief_features", "industrial_assets", "farm_parcels", "government_facilities", "public_cameras", "weather_overlays", "infrastructure_lines", "marketplace_listings", "usgs_3dep", "eia", "fbi_crime"],
    })
    return raw, gzip_api_bytes(raw)


@app.get("/api/map/entities.geojson")
def api_map_entities(request: Request, bbox: str | None = None):
    box = bbox_or_400(bbox)
    mtimes = (path_mtime(DATA / "companies.geojson"), path_mtime(DATA / "securities.geojson"))
    if box is None:
        raw, gzipped = _map_entities_json_cached(*mtimes)
        return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-entities", *mtimes, len(raw)))
    bbox_key = tuple(box)
    if bbox_key == FULL_WORLD_BBOX:
        raw, gzipped = _map_entities_json_cached(*mtimes)
        return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-entities-bbox", bbox_key, *mtimes, len(raw)))
    raw, gzipped = _map_entities_bbox_json_cached(bbox_key, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-entities-bbox", bbox_key, *mtimes, len(raw)))


@lru_cache(maxsize=256)
def _map_entities_bbox_json_cached(bbox_key: tuple, companies_mtime: float, securities_mtime: float):
    raw = compact_json_bytes(map_entities(list(bbox_key)))
    return raw, gzip_api_bytes(raw)


@app.get("/api/map/relationships.geojson")
def api_map_relationships(request: Request, bbox: str | None = None):
    box = bbox_or_400(bbox)
    mtime = path_mtime(DATA / "relationships.geojson")
    if box is None:
        raw, gzipped = _map_relationships_json_cached(mtime)
        return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-relationships", mtime, len(raw)))
    bbox_key = tuple(box)
    raw, gzipped = _map_relationships_bbox_json_cached(bbox_key, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-relationships-bbox", bbox_key, mtime, len(raw)))


@lru_cache(maxsize=256)
def _map_relationships_bbox_json_cached(bbox_key: tuple, relationships_mtime: float):
    raw = compact_json_bytes(map_relationships(list(bbox_key)))
    return raw, gzip_api_bytes(raw)


@app.get("/api/map/features.geojson")
def api_map_features(request: Request, layer: str = Query(...), bbox: str | None = None):
    box = bbox_or_400(bbox)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"))
    if box is None:
        raw, gzipped = _features_for_layer_json_cached(layer, *mtimes)
        return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-features", layer, *mtimes, len(raw)))
    bbox_key = tuple(box)
    raw, gzipped = _features_for_layer_bbox_json_cached(layer, bbox_key, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("map-features-bbox", layer, bbox_key, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _features_for_layer_bbox_json_cached(layer: str, bbox_key: tuple, intel_mtime: float, universe_mtime: float):
    raw = compact_json_bytes(features_for_layer(layer, list(bbox_key)))
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/search")
def api_assets_search(
    request: Request,
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
    key = (
        asset_type or "",
        tuple(box or ()),
        min_price if min_price is not None else "",
        max_price if max_price is not None else "",
        min_acres if min_acres is not None else "",
        max_acres if max_acres is not None else "",
        zoning or "",
        listing_status or "",
        risk_max if risk_max is not None else "",
        soil_quality_min or "",
        infrastructure_distance_max if infrastructure_distance_max is not None else "",
    )
    mtime = path_mtime(INTEL)
    raw, gzipped = _assets_search_json_cached(*key, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("assets-search", *key, mtime, len(raw)))


@lru_cache(maxsize=256)
def _assets_search_json_cached(
    asset_type: str,
    bbox_key: tuple,
    min_price,
    max_price,
    min_acres,
    max_acres,
    zoning: str,
    listing_status: str,
    risk_max,
    soil_quality_min: str,
    infrastructure_distance_max,
    intel_mtime: float,
):
    box = list(bbox_key) if bbox_key else None
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
    raw = compact_json_bytes({"assets": rows, "needs_location": intel().get("needs_location", [])})
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}")
def api_asset(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"))
    raw, gzipped = _asset_profile_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-profile", aid, *mtimes, len(raw)))


@lru_cache(maxsize=256)
def _asset_profile_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float):
    raw = compact_json_bytes(asset_profile(asset_id))
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}/due-diligence")
def api_asset_due_diligence(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"))
    raw, gzipped = _asset_due_diligence_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-due-diligence", aid, *mtimes, len(raw)))


@lru_cache(maxsize=256)
def _asset_due_diligence_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float):
    profile = asset_profile(asset_id)
    payload = {
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
    raw = compact_json_bytes(payload)
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}/nearby-infrastructure")
def api_asset_nearby_infrastructure(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _asset_nearby_infrastructure_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-nearby-infrastructure", aid, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_nearby_infrastructure_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    raw = compact_json_bytes(asset_nearby_infrastructure_payload(asset_id))
    return raw, gzip_api_bytes(raw)


def asset_nearby_infrastructure_payload(asset_id: str) -> dict:
    asset = asset_profile(asset_id)
    return asset_nearby_infrastructure_payload_from_profile(asset)


def asset_nearby_infrastructure_payload_from_profile(asset: dict) -> dict:
    rows = [r for r in intel().get("layer_features", []) if r.get("source_layer") == "infrastructure_lines"]
    return {"asset_id": asset["id"], "nearby_infrastructure": rows[:8], "status": "placeholder"}


@app.get("/api/assets/{asset_id}/risk-summary")
def api_asset_risk_summary(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _asset_risk_summary_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-risk-summary", aid, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_risk_summary_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    raw = compact_json_bytes(asset_risk_summary_payload(asset_id))
    return raw, gzip_api_bytes(raw)


def asset_risk_summary_payload(asset_id: str) -> dict:
    asset = asset_profile(asset_id)
    return asset_risk_summary_payload_from_profile(asset)


def asset_risk_summary_payload_from_profile(asset: dict) -> dict:
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
def api_asset_valuation(asset_id: str, request: Request, case: str = "base"):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS))
    raw, gzipped = _asset_valuation_json_cached(aid, case, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-valuation", aid, case, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_valuation_json_cached(asset_id: str, case: str, intel_mtime: float, assumptions_mtime: float):
    raw = compact_json_bytes(valuation_model(asset_id, case))
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}/risk-score")
def api_asset_risk_score(asset_id: str, request: Request, case: str = "base"):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS))
    raw, gzipped = _asset_risk_score_json_cached(aid, case, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-risk-score", aid, case, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_risk_score_json_cached(asset_id: str, case: str, intel_mtime: float, assumptions_mtime: float):
    valuation = valuation_model(asset_id, case)
    raw = compact_json_bytes({
        "asset_id": asset_id,
        "case": case,
        "risk_score": valuation["risk_score"],
        "score": valuation["score"],
        "headline_recommendation": valuation["headline_recommendation"],
        "breakdown": valuation["score_breakdown"],
        "confidence_score": valuation["confidence_score"],
        "missing_data_fields": valuation["missing_data_fields"],
    })
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}/valuation-assumptions")
def api_asset_valuation_assumptions(asset_id: str, request: Request, case: str = "base"):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS))
    raw, gzipped = _asset_valuation_assumptions_json_cached(aid, case, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-valuation-assumptions", aid, case, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_valuation_assumptions_json_cached(asset_id: str, case: str, intel_mtime: float, assumptions_mtime: float):
    raw = compact_json_bytes({
        "asset_id": asset_id,
        "case": case,
        "assumptions": asset_assumptions(asset_id, case),
        "overrides": valuation_overrides().get(asset_id, {}),
        "editable_fields": ["revenue", "cost", "growth", "discount_rate", "utilization", "yield", "capex", "tax_incentives", "risk_adjustment"],
    })
    return raw, gzip_api_bytes(raw)


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
def api_asset_scenario(asset_id: str, request: Request, case: str = "base"):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS))
    raw, gzipped = _asset_valuation_json_cached(aid, case, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-scenario", aid, case, *mtimes, len(raw)))


@app.get("/api/assets/{asset_id}/entities")
def api_asset_entities(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _asset_entities_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-entities", aid, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_entities_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    raw = compact_json_bytes({"asset_id": asset_id, **asset_entities(asset_id)})
    return raw, gzip_api_bytes(raw)


@app.get("/api/assets/{asset_id}/relationship-graph")
def api_asset_relationship_graph(asset_id: str, request: Request):
    aid = unquote(asset_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _asset_relationship_graph_json_cached(aid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("asset-relationship-graph", aid, *mtimes, len(raw)))


@lru_cache(maxsize=512)
def _asset_relationship_graph_json_cached(asset_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    raw = compact_json_bytes(asset_relationship_graph_payload(asset_id))
    return raw, gzip_api_bytes(raw)


def asset_relationship_graph_payload(asset_id: str) -> dict:
    profile = asset_profile(asset_id)
    return asset_relationship_graph_payload_from_profile(profile)


def asset_relationship_graph_payload_from_profile(profile: dict) -> dict:
    asset_id = profile["id"]
    nodes = [{"id": asset_id, "type": "asset", "label": profile.get("name")}]
    edges = []
    for rel in profile.get("asset_relationships", []):
        other = rel["source_id"] if rel.get("target_id") == asset_id else rel.get("target_id")
        other_entity = entity(other)
        nodes.append({"id": other, "type": "entity" if other_entity else "object", "label": (other_entity or {}).get("name", other)})
        edges.append(rel)
    for listing in profile.get("listings", []):
        nodes.append({"id": listing["id"], "type": "listing", "label": listing.get("title")})
        edges.append({"id": f"{asset_id}:listed:{listing['id']}", "source_id": asset_id, "target_id": listing["id"], "relationship_type": "LISTED_AS", "source": listing.get("source"), "confidence": listing.get("confidence"), "updated_at": listing.get("last_updated")})
    return {"nodes": nodes, "edges": edges}


@app.get("/api/listings/search")
def api_listings_search(
    request: Request,
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
    box = bbox_or_400(bbox)
    key = (
        tuple(box or ()),
        asset_type or "",
        location or "",
        min_price if min_price is not None else "",
        max_price if max_price is not None else "",
        min_acres if min_acres is not None else "",
        max_acres if max_acres is not None else "",
        min_square_feet if min_square_feet is not None else "",
        max_square_feet if max_square_feet is not None else "",
        zoning or "",
        listing_status or "",
        owner_type or "",
        risk_max if risk_max is not None else "",
        soil_quality_min or "",
        infrastructure_distance_max if infrastructure_distance_max is not None else "",
        format,
    )
    mtime = path_mtime(INTEL)
    raw, gzipped = _listings_search_json_cached(*key, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("listings-search", *key, mtime, len(raw)))


@lru_cache(maxsize=256)
def _listings_search_json_cached(
    bbox_key: tuple,
    asset_type: str,
    location: str,
    min_price,
    max_price,
    min_acres,
    max_acres,
    min_square_feet,
    max_square_feet,
    zoning: str,
    listing_status: str,
    owner_type: str,
    risk_max,
    soil_quality_min: str,
    infrastructure_distance_max,
    format: str,
    intel_mtime: float,
):
    filters = {k: v for k, v in locals().items() if k not in {"bbox", "format"} and v not in (None, "")}
    filters.pop("bbox_key", None)
    filters.pop("intel_mtime", None)
    rows = listing_rows(filters, list(bbox_key) if bbox_key else None)
    if format == "geojson":
        raw = compact_json_bytes(feature_collection([f for row in rows if (f := listing_feature(row))]))
    else:
        raw = compact_json_bytes({"listings": rows})
    return raw, gzip_api_bytes(raw)


@app.get("/api/listings/{listing_id}")
def api_listing(listing_id: str, request: Request):
    lid = unquote(listing_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"))
    raw, gzipped = _listing_json_cached(lid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("listing", lid, *mtimes, len(raw)))


@lru_cache(maxsize=256)
def _listing_json_cached(listing_id: str, intel_mtime: float, universe_mtime: float):
    listing = next((r for r in intel().get("asset_listings", []) if r.get("id") == listing_id), None)
    if not listing:
        raise HTTPException(404, "listing not found")
    asset = asset_profile(listing["asset_id"]) if listing.get("asset_id") else None
    raw = compact_json_bytes({"listing": listing, "asset": asset})
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}")
def api_entity(entity_id: str, request: Request):
    eid = unquote(entity_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _entity_json_cached(eid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity", eid, *mtimes, len(raw)))


@lru_cache(maxsize=1024)
def _entity_json_cached(entity_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    row = entity(entity_id)
    if not row:
        raise HTTPException(404, "entity not found")
    raw = compact_json_bytes(row)
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/neighborhood")
def api_entity_neighborhood(entity_id: str, request: Request, depth: int = 1):
    eid = unquote(entity_id)
    parts = (path_mtime(DATA / "graph-index.json"), path_mtime(STORE_NODES), path_mtime(DATA / "relationships.geojson"))
    raw, gzipped = _entity_neighborhood_json_cached(eid, depth, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-neighborhood", eid, depth, *parts, len(raw)))


@lru_cache(maxsize=256)
def _entity_neighborhood_json_cached(entity_id: str, depth: int, graph_mtime: float, nodes_mtime: float, relationships_mtime: float):
    raw = compact_json_bytes(neighborhood(entity_id, depth))
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/reverse-dcf")
def api_entity_reverse_dcf(entity_id: str, request: Request, discount: float = 0.09, terminal_growth: float = 0.025,
                           method: str = "cash_flow"):
    from reverse_dcf import reverse_dcf
    eid = unquote(entity_id)
    parts = (path_mtime(STORE_NODES), path_mtime(DATA / "aliases.json"), latest_mtime(COMPANYFACTS, "CIK*.json"))
    raw, gzipped = _entity_reverse_dcf_json_cached(eid, discount, terminal_growth, method, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-reverse-dcf", eid, discount, terminal_growth, method, *parts, len(raw)))


@lru_cache(maxsize=256)
def _entity_reverse_dcf_json_cached(entity_id: str, discount: float, terminal_growth: float, method: str, nodes_mtime: float, aliases_mtime: float, facts_mtime: float):
    from reverse_dcf import reverse_dcf
    raw = compact_json_bytes(reverse_dcf(entity_id, discount=discount, terminal_growth=terminal_growth, method=method))
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/comps")
def api_entity_comps(entity_id: str, request: Request, cap: int = 12):
    from comps import comps
    eid = unquote(entity_id)
    parts = (path_mtime(STORE_NODES), path_mtime(STORE_EDGES), path_mtime(DATA / "aliases.json"), latest_mtime(COMPANYFACTS, "CIK*.json"))
    raw, gzipped = _entity_comps_json_cached(eid, cap, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-comps", eid, cap, *parts, len(raw)))


@lru_cache(maxsize=256)
def _entity_comps_json_cached(entity_id: str, cap: int, nodes_mtime: float, edges_mtime: float, aliases_mtime: float, facts_mtime: float):
    from comps import comps
    raw = compact_json_bytes(comps(entity_id, cap=cap))
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/political")
def api_entity_political(entity_id: str, request: Request):
    eid = unquote(entity_id)
    parts = (
        path_mtime(STORE_NODES),
        path_mtime(DATA / "aliases.json"),
        path_mtime(COMMITTEE_POLICY_MAP),
        path_mtime(POL_MEMBERS),
        path_mtime(POL_TRADES),
        path_mtime(GOV_CONTRACTS),
        path_mtime(INTEL),
        path_mtime(DATA / "universe_core.json"),
    )
    raw, gzipped = _entity_political_json_cached(eid, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-political", eid, *parts, len(raw)))


@lru_cache(maxsize=512)
def _entity_political_json_cached(
    entity_id: str,
    nodes_mtime: float,
    aliases_mtime: float,
    committee_mtime: float,
    members_mtime: float,
    trades_mtime: float,
    contracts_mtime: float,
    intel_mtime: float,
    universe_mtime: float,
):
    from political import political_context
    raw = compact_json_bytes(political_context(entity_id))
    return raw, gzip_api_bytes(raw)


def _watchlist_ids() -> set:
    if not WATCHLISTS.exists():
        return set()
    wl = json.loads(WATCHLISTS.read_text())
    return {e for w in wl.get("watchlists", []) for e in w.get("entity_ids", [])}


@app.get("/api/entity/{entity_id}/events")
def api_entity_events(entity_id: str, request: Request, limit: int = 40):
    eid = unquote(entity_id)
    parts = (path_mtime(EVENTS), path_mtime(WATCHLISTS))
    raw, gzipped = _entity_events_json_cached(eid, limit, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-events", eid, limit, *parts, len(raw)))


@lru_cache(maxsize=512)
def _entity_events_json_cached(entity_id: str, limit: int, events_mtime: float, watchlists_mtime: float):
    import duckdb
    events = []
    if EVENTS.exists():
        rows = duckdb.execute(
            f"select event_id, event_type, ts, title, source_url, priority from '{EVENTS.as_posix()}' "
            f"where oasis_id = ? order by ts desc limit ?", [entity_id, limit]).fetchall()
        events = [{"id": r[0], "type": r[1], "ts": r[2], "title": r[3],
                   "source_url": r[4], "priority": r[5]} for r in rows]
    raw = compact_json_bytes({"events": events, "watchlisted": entity_id in _watchlist_ids()})
    return raw, gzip_api_bytes(raw)


@app.post("/api/watchlist/toggle")
def api_watchlist_toggle(payload: dict):
    eid = payload.get("entity_id")
    if not eid:
        raise HTTPException(400, "entity_id required")
    wl = json.loads(WATCHLISTS.read_text()) if WATCHLISTS.exists() else {"watchlists": []}
    default = next((w for w in wl["watchlists"] if w.get("name") == "Default"), None)
    if not default:
        default = {"name": "Default", "entity_ids": []}
        wl.setdefault("watchlists", []).append(default)
    ids = default["entity_ids"]
    starred = eid not in ids
    (ids.append if starred else ids.remove)(eid)
    WATCHLISTS.write_text(json.dumps(wl, indent=2))
    return {"entity_id": eid, "watchlisted": starred}


@app.get("/api/entity/{entity_id}/risk")
def api_entity_risk(entity_id: str, request: Request):
    eid = unquote(entity_id)
    mtimes = (path_mtime(DATA / "graph-index.json"), path_mtime(STORE_NODES))
    raw, gzipped = _entity_risk_json_cached(eid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-risk", eid, *mtimes, len(raw)))


@lru_cache(maxsize=1024)
def _entity_risk_json_cached(entity_id: str, graph_mtime: float, store_mtime: float):
    focus = load_json("graph-index.json", {}).get(entity_id, {})
    raw = compact_json_bytes(risk_summary(entity_id, {entity_id, *focus.get("neighbors", [])}))
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/assets")
def api_entity_assets(entity_id: str, request: Request):
    eid = unquote(entity_id)
    mtimes = (path_mtime(INTEL), path_mtime(DATA / "universe_bulk.json"), path_mtime(STORE_NODES))
    raw, gzipped = _entity_assets_json_cached(eid, *mtimes)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-assets", eid, *mtimes, len(raw)))


@lru_cache(maxsize=128)
def _entity_assets_json_cached(entity_id: str, intel_mtime: float, universe_mtime: float, store_mtime: float):
    rows = entity_asset_rows(entity_id)
    raw = compact_json_bytes({"entity": entity(entity_id), "assets": rows})
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/asset-map.geojson")
def api_entity_asset_map(entity_id: str, request: Request):
    eid = unquote(entity_id)
    mtime = path_mtime(INTEL)
    raw, gzipped = _entity_asset_map_json_cached(eid, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-asset-map", eid, mtime, len(raw)))


@lru_cache(maxsize=128)
def _entity_asset_map_json_cached(entity_id: str, intel_mtime: float):
    rows = entity_asset_rows(entity_id)
    features = []
    for row in rows:
        rel = row.get("asset_relationship", {})
        feature = geo_feature(row, f"entity-asset-{str(rel.get('relationship_type', 'asset')).lower()}", "entity_asset")
        if feature:
            feature["properties"]["asset_relationship"] = rel
            features.append(feature)
    raw = compact_json_bytes(feature_collection(features))
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/combined-neighborhood")
def api_entity_combined_neighborhood(entity_id: str, request: Request, depth: int = 2):
    eid = unquote(entity_id)
    parts = (
        path_mtime(DATA / "graph-index.json"),
        path_mtime(DATA / "relationships.geojson"),
        path_mtime(INTEL),
        path_mtime(DATA / "universe_bulk.json"),
        path_mtime(STORE_NODES),
    )
    raw, gzipped = _entity_combined_neighborhood_json_cached(eid, depth, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("entity-combined-neighborhood", eid, depth, *parts, len(raw)))


@lru_cache(maxsize=256)
def _entity_combined_neighborhood_json_cached(entity_id: str, depth: int, graph_mtime: float, relationships_mtime: float, intel_mtime: float, universe_mtime: float, store_mtime: float):
    graph = neighborhood(entity_id, depth)
    assets = entity_asset_rows(entity_id)
    asset_edges = [a.get("asset_relationship") for a in assets if a.get("asset_relationship")]
    raw = compact_json_bytes({**graph, "assets": assets, "asset_edges": asset_edges})
    return raw, gzip_api_bytes(raw)


@app.get("/api/entity/{entity_id}/dcf.xlsx")
def api_entity_dcf(entity_id: str, request: Request, method: str = "cash_flow"):
    from dcf_export import FactsUnavailable, build_dcf_workbook

    try:
        path = build_dcf_workbook(unquote(entity_id), method)
    except FactsUnavailable as exc:
        # Local-only by design: never fetch from SEC inside a request.
        raise HTTPException(
            503,
            f"SEC facts for CIK{exc.cik} are not cached locally. "
            "Run `python3 refresh_financial_facts.py` to acquire them.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return conditional_file_response(request, path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", path.name)


@app.get("/api/cameras/public.geojson")
def api_cameras_public(request: Request, bbox: str | None = None):
    box = bbox_or_400(bbox)
    key = tuple(box or ())
    mtime = path_mtime(INTEL)
    raw, gzipped = _cameras_public_json_cached(key, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("cameras-public", key, mtime, len(raw)))


@lru_cache(maxsize=128)
def _cameras_public_json_cached(bbox_key: tuple, intel_mtime: float):
    raw = compact_json_bytes(public_cameras_geojson(list(bbox_key) if bbox_key else None))
    return raw, gzip_api_bytes(raw)


@app.get("/api/permits/search")
def api_permits_search(request: Request, bbox: str | None = None, permit_type: str | None = None):
    box = bbox_or_400(bbox)
    key = (tuple(box or ()), permit_type or "")
    mtime = path_mtime(INTEL)
    raw, gzipped = _permits_search_json_cached(*key, mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("permits-search", *key, mtime, len(raw)))


@lru_cache(maxsize=128)
def _permits_search_json_cached(bbox_key: tuple, permit_type: str, intel_mtime: float):
    raw = compact_json_bytes({"permits": public_permits(list(bbox_key) if bbox_key else None, permit_type or None)})
    return raw, gzip_api_bytes(raw)


@app.get("/api/location/unknown")
def api_location_unknown(request: Request):
    mtime = path_mtime(DATA / "location_unknown.json")
    raw, gzipped = _location_unknown_json_cached(mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("location-unknown", mtime, len(raw)))


@lru_cache(maxsize=4)
def _location_unknown_json_cached(unknown_mtime: float):
    raw = compact_json_bytes(load_json("location_unknown.json", []))
    return raw, gzip_api_bytes(raw)


@app.get("/api/data-sources/status")
def api_data_sources_status(request: Request):
    return cached_json_payload_response("data-sources-status", request)


@lru_cache(maxsize=8)
def _bootstrap_signals_json_cached(aliases_mtime: float, hq_mtime: float, news_mtime: float, edge_mtime: float, unknown_mtime: float):
    location_unknown = load_json("location_unknown.json", [])
    payload = {
        "aliases": load_json("aliases.json", {}),
        "hq_coords": load_json("hq_coords.json", {}),
        "news": load_json("news.json", None),
        "edge_candidates": load_json("edge_candidates.json", []),
        "location_unknown_count": len(location_unknown) if isinstance(location_unknown, list) else 0,
    }
    raw = compact_json_bytes(payload)
    return raw, gzip_api_bytes(raw)


@app.get("/api/bootstrap/signals")
def api_bootstrap_signals(request: Request):
    mtimes = (
        path_mtime(DATA / "aliases.json"),
        path_mtime(DATA / "hq_coords.json"),
        path_mtime(DATA / "news.json"),
        path_mtime(DATA / "edge_candidates.json"),
        path_mtime(DATA / "location_unknown.json"),
    )
    raw, gzipped = _bootstrap_signals_json_cached(
        *mtimes,
    )
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("bootstrap-signals", *mtimes, len(raw)))


@lru_cache(maxsize=4)
def _ui_bulk_json_cached(path: str, mtime: float):
    data = load_static_json(path)
    nodes = []
    for node in data.get("nodes", []):
        slim = dict(node)
        slim.pop("entity_model", None)
        nodes.append(slim)
    raw = compact_json_bytes({**data, "nodes": nodes})
    return raw, gzip_api_bytes(raw)


@app.get("/api/universe/bulk")
def api_universe_bulk(request: Request):
    path = DATA / "universe_bulk.json"
    mtime = path.stat().st_mtime if path.exists() else 0
    raw, gzipped = _ui_bulk_json_cached(str(path), mtime)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("universe-bulk", mtime, len(raw)))


@app.get("/data/universe_core.json", include_in_schema=False)
def static_universe_core(request: Request):
    return cached_static_data_response("universe_core.json", request)


@app.get("/data/companies.geojson", include_in_schema=False)
def static_companies_geojson(request: Request):
    return cached_static_data_response("companies.geojson", request)


@app.get("/data/securities.geojson", include_in_schema=False)
def static_securities_geojson(request: Request):
    return cached_static_data_response("securities.geojson", request)


@app.get("/data/relationships.geojson", include_in_schema=False)
def static_relationships_geojson(request: Request):
    return cached_static_data_response("relationships.geojson", request)


@app.get("/data/graph-index.json", include_in_schema=False)
def static_graph_index(request: Request):
    return cached_static_data_response("graph-index.json", request)


@app.get("/api/reliefs/dem/status")
def api_reliefs_dem_status(request: Request):
    return cached_json_payload_response("reliefs-dem-status", request)


@app.get("/api/reliefs/dem/tilejson")
def api_reliefs_dem_tilejson():
    tilejson = dem_tilejson()
    if not tilejson:
        raise HTTPException(404, "DEM tilejson not found; run scripts/build_usgs_terrain_tiles.py")
    return tilejson


@app.get("/api/reliefs/terrain/sources")
def api_reliefs_terrain_sources(request: Request):
    return cached_json_payload_response("reliefs-terrain-sources", request)


def terrain_coverage_payload():
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


@app.get("/api/reliefs/terrain/coverage")
def api_reliefs_terrain_coverage(request: Request):
    return cached_json_payload_response("reliefs-terrain-coverage", request)


@app.get("/api/reliefs/terrain/jobs/status")
def api_reliefs_terrain_jobs_status(request: Request):
    return cached_json_payload_response("reliefs-terrain-jobs", request)


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


@lru_cache(maxsize=4)
def _generated_evidence_cached(intel_mtime: float, assumptions_mtime: float, evidence_date: str) -> tuple[dict, ...]:
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
    return tuple(sorted(dedup.values(), key=lambda r: (r["linked_object_type"], r["linked_object_id"], r["claim_type"])))


def generated_evidence() -> list[dict]:
    rows = _generated_evidence_cached(path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS), today())
    return [dict(row) for row in rows]


@lru_cache(maxsize=128)
def _evidence_json_cached(object_type: str, object_id: str, intel_mtime: float, assumptions_mtime: float, evidence_date: str):
    rows = generated_evidence()
    if object_type:
        wanted = {object_type}
        if object_type == "asset":
            wanted |= {"valuation", "risk_score"}
        rows = [r for r in rows if r.get("linked_object_type") in wanted]
    if object_id:
        rows = [r for r in rows if r.get("linked_object_id") == object_id]
    raw = compact_json_bytes({"evidence": rows})
    return raw, gzip_api_bytes(raw)


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


def data_quality_cache_parts() -> tuple:
    return (
        path_mtime(INTEL),
        path_mtime(VALUATION_ASSUMPTIONS),
        path_mtime(USER_OVERRIDES),
        path_mtime(DATA / "relationships.geojson"),
        path_mtime(STORE_NODES),
        today(),
    )


def quality_summary() -> dict:
    return {**_quality_summary_cached(*data_quality_cache_parts()), "generated_at": now_iso()}


@lru_cache(maxsize=8)
def _quality_summary_cached(intel_mtime: float, assumptions_mtime: float, user_overrides_mtime: float, relationships_mtime: float, store_mtime: float, evidence_date: str) -> dict:
    data = intel()
    evidence = generated_evidence()
    rels = data.get("asset_relationships", [])
    assets = data.get("assets", [])
    farm_profiles = {p.get("asset_id"): p for p in data.get("farm_profiles", [])}
    industrial_profiles = {p.get("asset_id"): p for p in data.get("industrial_profiles", [])}
    permits_by_asset: dict[str, list[dict]] = {}
    for permit in data.get("permits", []):
        permits_by_asset.setdefault(permit.get("asset_id"), []).append(permit)
    listings_by_asset: dict[str, list[dict]] = {}
    for listing in data.get("asset_listings", []):
        listings_by_asset.setdefault(listing.get("asset_id"), []).append(listing)
    valuation_missing = 0
    for asset in assets:
        try:
            asset_id = asset["id"]
            profile = {
                **asset,
                "permits": permits_by_asset.get(asset_id, []),
                "listings": listings_by_asset.get(asset_id, []),
                "farm_profile": farm_profiles.get(asset_id),
                "industrial_profile": industrial_profiles.get(asset_id),
            }
            if missing_fields(profile, asset_assumptions_for_profile(asset["id"], profile)):
                valuation_missing += 1
        except Exception:
            valuation_missing += 1
    owned_asset_ids = {r.get("target_id") for r in rels if r.get("relationship_type") == "OWNS"}
    return {
        "total_entities": store_node_count() + len(data.get("entities", [])),
        "total_assets": len(assets),
        "total_relationships": len(map_relationships()["features"]) + len(rels),
        "total_evidence_records": len(evidence),
        "assets_missing_location": sum(1 for a in assets if not geom(a)),
        "assets_missing_owner": sum(1 for a in assets if not a.get("owner_entity_id") and a.get("id") not in owned_asset_ids),
        "assets_missing_valuation": valuation_missing,
        "low_confidence_relationships": sum(1 for r in rels if num(r.get("confidence"), 0) < 0.5),
        "stale_records": sum(1 for r in evidence if is_stale(r)),
        "records_needing_review": sum(1 for r in evidence if not r.get("source_name") or num(r.get("confidence"), 0) < 0.5 or is_stale(r)),
    }


def layer_quality(layer_name: str) -> dict:
    return {"layer_name": layer_name, "metrics": _layer_quality_metrics_cached(*data_quality_cache_parts()), "generated_at": now_iso()}


@lru_cache(maxsize=8)
def _layer_quality_metrics_cached(intel_mtime: float, assumptions_mtime: float, user_overrides_mtime: float, relationships_mtime: float, store_mtime: float, evidence_date: str) -> dict:
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
    return metrics


def quality_dashboard() -> dict:
    base_layer = layer_quality("dashboard")
    layers = {name: {**base_layer, "layer_name": name} for name in ("farms", "industrial", "government")}
    return {"summary": quality_summary(), "layers": layers, "generated_at": now_iso()}


def report_cache_parts() -> tuple:
    return (
        path_mtime(INTEL),
        path_mtime(VALUATION_ASSUMPTIONS),
        path_mtime(DATA / "graph-index.json"),
        path_mtime(DATA / "relationships.geojson"),
        path_mtime(DATA / "universe_bulk.json"),
        path_mtime(STORE_NODES),
        today(),
    )


def report_payload(object_type: str, object_id: str) -> dict:
    return {**_report_payload_core_cached(object_type, object_id, *report_cache_parts()), "generated_at": now_iso()}


@lru_cache(maxsize=256)
def _report_payload_core_cached(
    object_type: str,
    object_id: str,
    intel_mtime: float,
    assumptions_mtime: float,
    graph_mtime: float,
    relationships_mtime: float,
    universe_mtime: float,
    store_mtime: float,
    evidence_date: str,
) -> dict:
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
        sections["relationship_graph"] = asset_relationship_graph_payload_from_profile(obj)
        sections["nearby_infrastructure"] = asset_nearby_infrastructure_payload_from_profile(obj)
        sections["risk_summary"] = asset_risk_summary_payload_from_profile(obj)
        sections["valuation"] = valuation_model_for_profile(object_id, obj)
        sections["scenarios"] = {case: valuation_model_for_profile(object_id, obj, case) for case in ("bear", "base", "bull")}
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
def api_evidence(request: Request, object_type: str | None = None, object_id: str | None = None):
    filters = (object_type or "", object_id or "")
    parts = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS), today())
    raw, gzipped = _evidence_json_cached(*filters, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("evidence", *filters, *parts, len(raw)))


@app.get("/api/evidence/{evidence_id}")
def api_evidence_one(evidence_id: str, request: Request):
    eid = unquote(evidence_id)
    parts = (path_mtime(INTEL), path_mtime(VALUATION_ASSUMPTIONS), today())
    raw, gzipped = _evidence_one_json_cached(eid, *parts)
    return cached_bytes_response(request, raw, gzipped, "application/json", cache_etag("evidence-one", eid, *parts, len(raw)))


@lru_cache(maxsize=512)
def _evidence_one_json_cached(evidence_id: str, intel_mtime: float, assumptions_mtime: float, evidence_date: str):
    row = next((r for r in generated_evidence() if r["id"] == evidence_id), None)
    if not row:
        raise HTTPException(404, "evidence not found")
    raw = compact_json_bytes(row)
    return raw, gzip_api_bytes(raw)


@app.get("/api/data-quality/summary")
def api_data_quality_summary(request: Request):
    parts = data_quality_cache_parts()
    etag = cache_etag("data-quality-summary", *parts)
    if response := not_modified_response(request, etag):
        return response
    raw = compact_json_bytes(quality_summary())
    return cached_bytes_response(request, raw, gzip_api_bytes(raw), "application/json", etag)


@app.get("/api/data-quality/layer/{layer_name}")
def api_data_quality_layer(layer_name: str, request: Request):
    name = unquote(layer_name)
    parts = data_quality_cache_parts()
    etag = cache_etag("data-quality-layer", name, *parts)
    if response := not_modified_response(request, etag):
        return response
    raw = compact_json_bytes(layer_quality(name))
    return cached_bytes_response(request, raw, gzip_api_bytes(raw), "application/json", etag)


@app.get("/api/data-quality/dashboard")
def api_data_quality_dashboard(request: Request):
    parts = data_quality_cache_parts()
    etag = cache_etag("data-quality-dashboard", *parts)
    if response := not_modified_response(request, etag):
        return response
    raw = compact_json_bytes(quality_dashboard())
    return cached_bytes_response(request, raw, gzip_api_bytes(raw), "application/json", etag)


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
def api_report_download(report_id: str, request: Request, format: str = "html"):
    ext = {"html": ".html", "json": ".json", "csv": ".csv", "pdf": ".html"}.get(format, ".html")
    path = REPORTS_DIR / f"{slug(unquote(report_id))}{ext}"
    if not path.exists():
        raise HTTPException(404, "report export not found")
    media = {"html": "text/html", "json": "application/json", "csv": "text/csv", "pdf": "text/html"}.get(format, "text/html")
    return conditional_file_response(request, path, media, path.name)


@app.get("/api/reports/{object_type}/{object_id}")
def api_report_preview(object_type: str, object_id: str, request: Request):
    kind, oid = unquote(object_type), unquote(object_id)
    parts = report_cache_parts()
    etag = cache_etag("report-preview", kind, oid, *parts)
    if response := not_modified_response(request, etag):
        return response
    raw = compact_json_bytes(report_payload(kind, oid))
    return cached_bytes_response(request, raw, gzip_api_bytes(raw), "application/json", etag)


@app.post("/api/reports/{object_type}/{object_id}/generate")
async def api_report_generate(object_type: str, object_id: str, payload: dict[str, Any] | None = None):
    report = report_payload(unquote(object_type), unquote(object_id))
    if payload:
        report["requested_sections"] = payload.get("sections")
        report["requested_report_type"] = payload.get("report_type")
    return {"ok": True, **write_report_exports(report)}


def warm_latency_caches() -> None:
    warm_startup_caches()
    warm_payload_caches()
    warm_research_caches()


def start_background_warm_caches() -> None:
    thread = threading.Thread(target=warm_background_caches, name="oasis-cache-warmup", daemon=True)
    thread.start()


def warm_background_caches() -> None:
    warm_payload_caches()
    warm_research_caches()


def warm_payload_caches() -> None:
    with suppress(Exception):
        path = DATA / "universe_bulk.json"
        _ui_bulk_json_cached(str(path), path_mtime(path))
    with suppress(Exception):
        _map_entities_json_cached(path_mtime(DATA / "companies.geojson"), path_mtime(DATA / "securities.geojson"))
    with suppress(Exception):
        _map_relationships_json_cached(path_mtime(DATA / "relationships.geojson"))
    for cache_name in (
        "data-sources-status",
        "reliefs-dem-status",
        "reliefs-terrain-sources",
        "reliefs-terrain-coverage",
        "reliefs-terrain-jobs",
    ):
        with suppress(Exception):
            _json_payload_cached(cache_name, terrain_status_cache_parts())
    for name in ("universe_core.json", "companies.geojson", "securities.geojson", "relationships.geojson", "graph-index.json"):
        with suppress(Exception):
            path = DATA / name
            _static_asset_bytes_cached(str(path), path_mtime(path))
    for name in ("vendor/maplibre-gl/5.6.2/maplibre-gl.css", "vendor/maplibre-gl/5.6.2/maplibre-gl.js"):
        with suppress(Exception):
            path = ROOT / "graph" / name
            _static_asset_bytes_cached(str(path), path_mtime(path))


def warm_research_caches() -> None:
    with suppress(Exception):
        __import__("duckdb")
    for module in ("political", "comps", "reverse_dcf"):
        with suppress(Exception):
            __import__(module)
    with suppress(Exception):
        store_by_id()
    with suppress(Exception):
        store_aliases()
    with suppress(Exception):
        intel_indexes()
    with suppress(Exception):
        generated_evidence()
    for entity_id in ("GM", "USDA"):
        with suppress(Exception):
            _entity_events_json_cached(entity_id, 40, path_mtime(EVENTS), path_mtime(WATCHLISTS))
        with suppress(Exception):
            parts = (path_mtime(STORE_NODES), path_mtime(DATA / "aliases.json"), latest_mtime(COMPANYFACTS, "CIK*.json"))
            _entity_reverse_dcf_json_cached(entity_id, 0.09, 0.025, "cash_flow", *parts)
        with suppress(Exception):
            from dcf_export import build_dcf_workbook

            build_dcf_workbook(entity_id, "cash_flow")
        with suppress(Exception):
            parts = (path_mtime(STORE_NODES), path_mtime(STORE_EDGES), path_mtime(DATA / "aliases.json"), latest_mtime(COMPANYFACTS, "CIK*.json"))
            _entity_comps_json_cached(entity_id, 8, *parts)
        with suppress(Exception):
            parts = (
                path_mtime(STORE_NODES),
                path_mtime(DATA / "aliases.json"),
                path_mtime(COMMITTEE_POLICY_MAP),
                path_mtime(POL_MEMBERS),
                path_mtime(POL_TRADES),
                path_mtime(GOV_CONTRACTS),
                path_mtime(INTEL),
                path_mtime(DATA / "universe_core.json"),
            )
            _entity_political_json_cached(entity_id, *parts)


def warm_startup_caches() -> None:
    with suppress(Exception):
        _bootstrap_signals_json_cached(
            path_mtime(DATA / "aliases.json"),
            path_mtime(DATA / "hq_coords.json"),
            path_mtime(DATA / "news.json"),
            path_mtime(DATA / "edge_candidates.json"),
            path_mtime(DATA / "location_unknown.json"),
        )
    with suppress(Exception):
        store_node_count()
    with suppress(Exception):
        store_by_id()
    with suppress(Exception):
        load_static_json(str(DATA / "graph-index.json"))
    with suppress(Exception):
        load_static_json(str(DATA / "relationships.geojson"))


@app.get("/vendor/maplibre-gl/5.6.2/maplibre-gl.css", include_in_schema=False)
def vendor_maplibre_css(request: Request):
    return cached_graph_asset_response("vendor/maplibre-gl/5.6.2/maplibre-gl.css", request, "text/css")


@app.get("/vendor/maplibre-gl/5.6.2/maplibre-gl.js", include_in_schema=False)
def vendor_maplibre_js(request: Request):
    return cached_graph_asset_response("vendor/maplibre-gl/5.6.2/maplibre-gl.js", request, "application/javascript")


@app.get("/js/main.js", include_in_schema=False)
def app_main_js(request: Request):
    return cached_graph_asset_response("js/main.js", request, "application/javascript", "public, max-age=60, must-revalidate")


@app.get("/js/config.js", include_in_schema=False)
def app_config_js(request: Request):
    return cached_graph_asset_response("js/config.js", request, "application/javascript", "public, max-age=60, must-revalidate")


@app.get("/js/state.js", include_in_schema=False)
def app_state_js(request: Request):
    return cached_graph_asset_response("js/state.js", request, "application/javascript", "public, max-age=60, must-revalidate")


@app.get("/css/app.css", include_in_schema=False)
def app_css(request: Request):
    return cached_graph_asset_response("css/app.css", request, "text/css", "public, max-age=60, must-revalidate")


@app.get("/Logo_Dark_BG_96.png", include_in_schema=False)
def app_logo(request: Request):
    return cached_graph_asset_response("Logo_Dark_BG_96.png", request, "image/png", "public, max-age=31536000, immutable")


@app.get("/", include_in_schema=False)
def app_index(request: Request):
    return cached_graph_asset_response("index.html", request, "text/html", "public, max-age=60, must-revalidate")


@app.get("/index.html", include_in_schema=False)
def app_index_html(request: Request):
    return cached_graph_asset_response("index.html", request, "text/html", "public, max-age=60, must-revalidate")


app.mount("/", StaticFiles(directory=str(ROOT / "graph"), html=True), name="graph")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8788)


if __name__ == "__main__":
    main()

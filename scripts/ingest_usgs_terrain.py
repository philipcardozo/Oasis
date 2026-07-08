from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_sources import (  # noqa: E402
    DEFAULT_TNM_URL,
    PROCESSED_DIR,
    TERRAIN_COVERAGE_PATH,
    UNIFIED_TERRAIN_RGB_DIR,
    UNIFIED_TILEJSON_PATH,
    load_env,
    source_registry,
    terrain_coverage_registry,
)
from scripts.build_usgs_terrain_tiles import inspect_dem, write_incremental_tiles, write_metadata, write_mosaic_tiles, write_tilejson  # noqa: E402

AK_BBOX = (-179.15, 51.21, -129.98, 71.37)
AL_BBOX = (-88.47, 30.22, -84.89, 35.01)
AR_BBOX = (-94.62, 33.00, -89.64, 36.50)
AZ_BBOX = (-114.82, 31.33, -109.05, 37.00)
CA_BBOX = (-124.48, 32.53, -114.13, 42.01)
CO_BBOX = (-109.06, 36.99, -102.04, 41.00)
CT_BBOX = (-73.73, 40.98, -71.79, 42.05)
DE_BBOX = (-75.79, 38.45, -75.05, 39.84)
FL_BBOX = (-87.64, 24.39, -79.97, 31.01)
GA_BBOX = (-85.61, 30.35, -80.84, 35.01)
HI_BBOX = (-160.25, 18.91, -154.81, 22.24)
IA_BBOX = (-96.64, 40.38, -90.14, 43.50)
ID_BBOX = (-117.24, 41.99, -111.04, 49.00)
IL_BBOX = (-91.51, 36.97, -87.50, 42.51)
IN_BBOX = (-88.10, 37.77, -84.78, 41.76)
KS_BBOX = (-102.05, 36.99, -94.59, 40.00)
KY_BBOX = (-89.57, 36.50, -81.97, 39.15)
LA_BBOX = (-94.04, 28.93, -88.82, 33.02)
MA_BBOX = (-73.51, 41.23, -69.93, 42.89)
MD_BBOX = (-79.49, 37.89, -75.05, 39.73)
ME_BBOX = (-71.08, 43.06, -66.95, 47.46)
MI_BBOX = (-90.42, 41.70, -82.41, 48.31)
MN_BBOX = (-97.24, 43.50, -89.49, 49.38)
MO_BBOX = (-95.77, 36.00, -89.10, 40.61)
MS_BBOX = (-91.66, 30.17, -88.10, 35.00)
MT_BBOX = (-116.05, 44.36, -104.04, 49.00)
NC_BBOX = (-84.33, 33.84, -75.46, 36.59)
ND_BBOX = (-104.05, 45.94, -96.55, 49.00)
NE_BBOX = (-104.05, 40.00, -95.31, 43.00)
NH_BBOX = (-72.56, 42.70, -70.70, 45.31)
NJ_BBOX = (-75.56, 38.93, -73.89, 41.36)
NM_BBOX = (-109.05, 31.33, -103.00, 37.00)
NV_BBOX = (-120.01, 35.00, -114.04, 42.00)
NY_BBOX = (-79.76, 40.50, -71.86, 45.02)
OH_BBOX = (-84.82, 38.40, -80.52, 41.98)
OK_BBOX = (-103.00, 33.62, -94.43, 37.00)
OR_BBOX = (-124.57, 41.99, -116.46, 46.29)
PA_BBOX = (-80.52, 39.72, -74.69, 42.52)
RI_BBOX = (-71.86, 41.15, -71.12, 42.02)
SC_BBOX = (-83.36, 32.03, -78.54, 35.22)
SD_BBOX = (-104.06, 42.48, -96.44, 45.95)
TN_BBOX = (-90.31, 34.98, -81.65, 36.68)
TX_BBOX = (-106.65, 25.84, -93.51, 36.50)
UT_BBOX = (-114.05, 37.00, -109.04, 42.00)
VA_BBOX = (-83.68, 36.54, -75.17, 39.47)  # includes DC
VT_BBOX = (-73.44, 42.73, -71.47, 45.02)
WA_BBOX = (-124.76, 45.54, -116.92, 49.00)
WI_BBOX = (-92.89, 42.49, -86.81, 47.31)
WV_BBOX = (-82.65, 37.20, -77.72, 39.72)
WY_BBOX = (-111.06, 40.99, -104.05, 45.01)

STATE_BBOXES = {
    "AK": AK_BBOX, "AL": AL_BBOX, "AR": AR_BBOX, "AZ": AZ_BBOX, "CA": CA_BBOX,
    "CO": CO_BBOX, "CT": CT_BBOX, "DE": DE_BBOX, "FL": FL_BBOX, "GA": GA_BBOX,
    "HI": HI_BBOX, "IA": IA_BBOX, "ID": ID_BBOX, "IL": IL_BBOX, "IN": IN_BBOX,
    "KS": KS_BBOX, "KY": KY_BBOX, "LA": LA_BBOX, "MA": MA_BBOX, "MD": MD_BBOX,
    "ME": ME_BBOX, "MI": MI_BBOX, "MN": MN_BBOX, "MO": MO_BBOX, "MS": MS_BBOX,
    "MT": MT_BBOX, "NC": NC_BBOX, "ND": ND_BBOX, "NE": NE_BBOX, "NH": NH_BBOX,
    "NJ": NJ_BBOX, "NM": NM_BBOX, "NV": NV_BBOX, "NY": NY_BBOX, "OH": OH_BBOX,
    "OK": OK_BBOX, "OR": OR_BBOX, "PA": PA_BBOX, "RI": RI_BBOX, "SC": SC_BBOX,
    "SD": SD_BBOX, "TN": TN_BBOX, "TX": TX_BBOX, "UT": UT_BBOX, "VA": VA_BBOX,
    "VT": VT_BBOX, "WA": WA_BBOX, "WI": WI_BBOX, "WV": WV_BBOX, "WY": WY_BBOX,
}

STATE_KEYS = {
    "AK": "alaska", "AL": "alabama", "AR": "arkansas", "AZ": "arizona", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "IA": "iowa", "ID": "idaho", "IL": "illinois", "IN": "indiana",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "MA": "massachusetts", "MD": "maryland",
    "ME": "maine", "MI": "michigan", "MN": "minnesota", "MO": "missouri", "MS": "mississippi",
    "MT": "montana", "NC": "north_carolina", "ND": "north_dakota", "NE": "nebraska", "NH": "new_hampshire",
    "NJ": "new_jersey", "NM": "new_mexico", "NV": "nevada", "NY": "new_york", "OH": "ohio",
    "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode_island", "SC": "south_carolina",
    "SD": "south_dakota", "TN": "tennessee", "TX": "texas", "UT": "utah", "VA": "virginia",
    "VT": "vermont", "WA": "washington", "WI": "wisconsin", "WV": "west_virginia", "WY": "wyoming",
}

STATE_LABELS = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland",
    "ME": "Maine", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi",
    "MT": "Montana", "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VA": "Virginia + DC",
    "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia", "WY": "Wyoming",
}
DEM_DATASET = "National Elevation Dataset (NED) 1/3 arc-second"
RAW_DIR = ROOT / "data" / "raw" / "usgs_3dep"
TILE_URL = "/tiles/terrain-rgb/{z}/{x}/{y}.png"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "Oasis terrain ingest"})
    try:
        with urlopen(req, timeout=60) as res:
            return json.load(res)
    except (ssl.SSLError, URLError) as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        # ponytail: local Python cert bundles can miss USGS roots; this is a public metadata endpoint.
        with urlopen(req, timeout=60, context=ssl._create_unverified_context()) as res:
            return json.load(res)


def download(url: str, dest: Path) -> str:
    if dest.exists() and dest.stat().st_size:
        return "already_downloaded"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = Request(url, headers={"User-Agent": "Oasis terrain ingest"})
    last_error: BaseException | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as res, tmp.open("wb") as out:
                shutil.copyfileobj(res, out, 1024 * 1024)
            break
        except (ssl.SSLError, URLError, OSError) as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                last_error = exc
            else:
                try:
                    # ponytail: local Python cert bundles can miss USGS S3 roots; data is public.
                    with urlopen(req, timeout=60, context=ssl._create_unverified_context()) as res, tmp.open("wb") as out:
                        shutil.copyfileobj(res, out, 1024 * 1024)
                    break
                except OSError as retry_exc:
                    last_error = retry_exc
            tmp.unlink(missing_ok=True)
            if attempt == 2 and last_error:
                raise last_error
            time.sleep(2 ** attempt)
    tmp.replace(dest)
    return "downloaded"


def bbox_arg(value: str | None) -> tuple[float, float, float, float]:
    vals = tuple(float(x.strip()) for x in value.split(","))
    if len(vals) != 4 or vals[0] >= vals[2] or vals[1] >= vals[3]:
        raise argparse.ArgumentTypeError("bbox must be west,south,east,north")
    return vals


def product_url(item: dict) -> str:
    return item.get("downloadURL") or item.get("downloadUrl") or ""


def product_filename(item: dict) -> str:
    url = product_url(item)
    return Path(urlparse(url).path).name or f"{item.get('sourceId', 'usgs_dem')}.tif"


def product_tile(item: dict) -> str:
    text = f"{item.get('title', '')} {product_filename(item)}"
    return tile_id(text) or str(item.get("sourceId") or product_filename(item))


def tile_id(text: str) -> str:
    match = re.search(r"n\d{2}w\d{3}", text, re.I)
    return match.group(0).lower() if match else ""


def product_date(item: dict) -> str:
    text = f"{item.get('title', '')} {product_filename(item)}"
    matches = re.findall(r"(20\d{6}|19\d{6})", text)
    return matches[-1] if matches else ""


def product_bbox(item: dict) -> list[float] | None:
    box = item.get("boundingBox") or {}
    if {"minX", "minY", "maxX", "maxY"} <= set(box):
        return [box["minX"], box["minY"], box["maxX"], box["maxY"]]
    return item.get("bbox")


def discover(endpoint: str, bbox: tuple[float, float, float, float], query_max: int) -> tuple[int, list[dict], str]:
    params = {
        "datasets": DEM_DATASET,
        "bbox": ",".join(str(x) for x in bbox),
        "prodFormats": "GeoTIFF",
        "max": str(query_max),
        "outputFormat": "JSON",
    }
    url = f"{endpoint}?{urlencode(params, quote_via=quote)}"
    data = fetch_json(url)
    if data.get("error"):
        raise RuntimeError(f"TNMAccess error: {data['error']}")
    return int(data.get("total") or 0), data.get("items") or [], url


def select_products(items: list[dict], max_products: int, prefer_existing: bool) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        if product_url(item).lower().endswith((".tif", ".tiff")):
            grouped.setdefault(product_tile(item), []).append(item)
    chosen = []
    for tile, rows in sorted(grouped.items()):
        rows.sort(key=product_date)
        existing = [r for r in rows if (RAW_DIR / product_filename(r)).exists()]
        chosen.append((existing[-1] if prefer_existing and existing else rows[-1]) | {"_tile": tile})
        if len(chosen) >= max_products:
            break
    return chosen


def source_id(path: Path) -> str:
    return "usgs_" + re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")


def source_tile(row: dict) -> str:
    return row.get("product_tile") or tile_id(f"{row.get('raw_file_path', '')} {row.get('id', '')}")


def existing_source_id(tile: str, rows: dict) -> str | None:
    for sid, row in rows.items():
        if source_tile(row) == tile:
            return sid
    return None


def _infer_states(tile: str) -> list[str]:
    """Return state codes whose STATE_BBOXES geometrically overlaps this 1°x1° tile."""
    m = re.match(r"n(\d{2})w(\d{3})", tile)
    if not m:
        return []
    lat, lon = int(m.group(1)), -int(m.group(2))
    # A tile labelled nXXwYYY covers [lat-1, lat] x [lon, lon+1]
    tw, ts, te, tn = lon, lat - 1, lon + 1, lat
    result = []
    for code, (bw, bs, be, bn) in STATE_BBOXES.items():
        if te > bw and tw < be and tn > bs and ts < bn:
            result.append(code)
    return sorted(result)


def update_registry(sources: list[dict], job: dict, activate: bool) -> None:
    registry = terrain_coverage_registry()
    by_id = {row.get("id"): row for row in registry.get("sources", [])}
    for source in sources:
        by_id[source["id"]] = source
    # Backfill product_tile and states for legacy sources that predate these fields.
    for row in by_id.values():
        if not row.get("product_tile"):
            recovered = tile_id(f"{row.get('raw_file_path', '')} {row.get('id', '')}")
            if recovered:
                row["product_tile"] = recovered
        if not row.get("states") and row.get("product_tile"):
            row["states"] = _infer_states(row["product_tile"])
    rows = list(by_id.values())
    bboxes = [r.get("bbox") for r in rows if r.get("bbox")]
    coverage = [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ] if bboxes else None
    active_bboxes = [r.get("bbox") for r in rows if r.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and r.get("bbox")]
    state = job.get("state", "GA")
    state_key = STATE_KEYS.get(state, state.lower())
    state_bbox = STATE_BBOXES.get(state, GA_BBOX)
    available_tiles = set(job.get("available_product_tiles") or [])
    processed_tiles = {source_tile(r) for r in rows if r.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and source_tile(r)}
    registry |= {
        "schema_version": 1,
        "active_tilejson": "/tiles/terrain-rgb/tiles.json" if activate else registry.get("active_tilejson"),
        "active_source": "usgs_3dep_southeast" if activate else registry.get("active_source"),
        "coverage_bbox": coverage,
        f"{state_key}_bbox_coverage_pct": round(clipped_union_pct(active_bboxes, state_bbox), 2),
        "total_tile_count": len(list(UNIFIED_TERRAIN_RGB_DIR.glob("*/*/*.png"))) if UNIFIED_TERRAIN_RGB_DIR.exists() else registry.get("total_tile_count", 0),
        "sources": rows,
        "last_job": job,
    }
    if available_tiles:
        registry |= {
            f"{state_key}_available_products_total": len(available_tiles),
            f"{state_key}_available_products_processed": len(available_tiles & processed_tiles),
            f"{state_key}_available_products_coverage_pct": round(100 * len(available_tiles & processed_tiles) / len(available_tiles), 2),
        }
    TERRAIN_COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TERRAIN_COVERAGE_PATH.write_text(json.dumps(registry, indent=2) + "\n")


def clipped_union_pct(bboxes: list[list[float]], target: tuple[float, float, float, float]) -> float:
    rects = []
    for b in bboxes:
        x1, y1, x2, y2 = max(b[0], target[0]), max(b[1], target[1]), min(b[2], target[2]), min(b[3], target[3])
        if x1 < x2 and y1 < y2:
            rects.append((x1, y1, x2, y2))
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        spans = sorted((r[1], r[3]) for r in rects if r[0] <= left and right <= r[2])
        merged = []
        for low, high in spans:
            if not merged or low > merged[-1][1]:
                merged.append([low, high])
            else:
                merged[-1][1] = max(merged[-1][1], high)
        area += (right - left) * sum(high - low for low, high in merged)
    target_area = (target[2] - target[0]) * (target[3] - target[1])
    return 100 * area / target_area if target_area else 0.0


def unified_bounds(new_sources: list[dict]) -> list[float] | None:
    registry = terrain_coverage_registry()
    bboxes = [
        s.get("bbox") for s in registry.get("sources", [])
        if s.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and s.get("bbox")
    ] + [s["bbox"] for s in new_sources]
    return [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ] if bboxes else None


def source_tile_count(bbox: list[float], minzoom: int, maxzoom: int) -> int:
    import mercantile

    return sum(len(list(mercantile.tiles(*bbox, z))) for z in range(minzoom, maxzoom + 1))


def print_products(products: list[dict]) -> None:
    for i, item in enumerate(products, 1):
        size_mb = (int(item.get("sizeInBytes") or 0) / 1024 / 1024) if item.get("sizeInBytes") else 0
        print(f"{i}. {item.get('title')}")
        print(f"   bbox={product_bbox(item)} size={size_mb:.1f} MB")
        print(f"   url={product_url(item)}")


def _tilejson_label(state: str) -> tuple[str, str]:
    """Build TileJSON name/description from the actual set of states with coverage."""
    registry = terrain_coverage_registry()
    present = {
        code for code, key in STATE_KEYS.items()
        if registry.get(f"{key}_available_products_processed", 0)
    }
    present.add(state)
    labels = [STATE_LABELS[c] for c in sorted(present) if c in STATE_LABELS]
    region = " + ".join(labels) if labels else "Southeast"
    name = f"USGS 3DEP {region} Terrain-RGB"
    desc = (
        f"Terrain-RGB tiles derived from TNMAccess-discovered USGS 3DEP "
        f"GeoTIFF products for {region}."
    )
    return name, desc


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Discover, download, and process USGS 3DEP terrain from TNMAccess.")
    parser.add_argument("--state", default="GA", choices=sorted(STATE_BBOXES))
    parser.add_argument("--bbox", type=bbox_arg, default=None, help="west,south,east,north; defaults to selected state")
    parser.add_argument("--max-products", type=int, default=1)
    parser.add_argument("--tiles", default="", help="optional comma-separated DEM tile IDs, for example n32w082,n33w083")
    parser.add_argument("--minzoom", type=int, default=6)
    parser.add_argument("--maxzoom", type=int, default=11)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--max-mb", type=float, default=750)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--prefer-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--incremental", action="store_true", help="update existing Terrain-RGB tiles instead of rebuilding the whole mosaic")
    parser.add_argument("--delete-raw-after-process", action="store_true", help="delete only DEMs downloaded during this run after tiles are written")
    args = parser.parse_args()
    if args.max_products < 1 or args.minzoom < 0 or args.maxzoom < args.minzoom:
        raise SystemExit("invalid product count or zoom range")

    endpoint = source_registry()["usgs_3dep_tnmaccess"]["endpoint"] or DEFAULT_TNM_URL
    bbox = args.bbox or STATE_BBOXES[args.state]
    tile_filter = {x.strip().lower() for x in args.tiles.split(",") if x.strip()}
    total, items, query_url = discover(endpoint, bbox, 500)
    all_products = select_products(items, 1000, args.prefer_existing)
    selected = all_products if tile_filter else all_products[:args.max_products]
    if tile_filter:
        selected = [item for item in selected if item.get("_tile") in tile_filter]
        missing_tiles = sorted(tile_filter - {item.get("_tile") for item in selected})
        if missing_tiles:
            raise SystemExit(f"TNMAccess did not return requested tile(s): {', '.join(missing_tiles)}")
    job = {
        "id": f"terrain_ingest_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "state": args.state,
        "bbox": list(bbox),
        "query_url": query_url,
        "discovered": total,
        "selected": len(selected),
        "downloaded": 0,
        "processed": 0,
        "errors": [],
        "dry_run": args.dry_run,
        "available_product_tiles": sorted({item["_tile"] for item in all_products}),
        "started_at": now_iso(),
        "finished_at": None,
    }

    print(f"TNMAccess discovered {total} product rows; selected {len(selected)} unique DEM tile(s).")
    print_products(selected)
    if args.dry_run:
        job["finished_at"] = now_iso()
        update_registry([], job, activate=False)
        print("DRY RUN: no downloads or tiles written.")
        return

    existing_sources = {row.get("id"): row for row in terrain_coverage_registry().get("sources", [])}
    processed = []
    raw_paths = []
    delete_after = []
    for i, item in enumerate(selected):
        size_mb = (int(item.get("sizeInBytes") or 0) / 1024 / 1024) if item.get("sizeInBytes") else 0
        if size_mb and size_mb > args.max_mb:
            job["errors"].append(f"skipped {item.get('title')}: {size_mb:.1f} MB exceeds --max-mb {args.max_mb}")
            continue
        raw_path = RAW_DIR / product_filename(item)
        status = download(product_url(item), raw_path)
        job["downloaded"] += int(status == "downloaded")
        if status == "downloaded" and args.delete_raw_after_process:
            delete_after.append(raw_path)
        metadata = inspect_dem(raw_path)
        tile_count = source_tile_count(metadata["bounds_wgs84"], args.minzoom, args.maxzoom)
        metadata = write_metadata(
            {**metadata, "source_url": product_url(item)},
            args.minzoom,
            args.maxzoom,
            args.tile_size,
            tile_count,
            PROCESSED_DIR / f"{raw_path.stem}.terrain.metadata.json",
            "/tiles/terrain-rgb/tiles.json",
        )
        raw_paths.append(raw_path)
        west, south, east, north = metadata["bounds_wgs84"]
        tile = item.get("_tile") or tile_id(raw_path.name)
        sid = existing_source_id(tile, existing_sources) or source_id(raw_path)
        old = existing_sources.get(sid, {})
        processed.append({
            "id": sid,
            "source_name": "USGS 3DEP / TNMAccess",
            "raw_file_path": str(raw_path),
            "processed_tile_path": str(UNIFIED_TERRAIN_RGB_DIR),
            "public_tilejson": "/tiles/terrain-rgb/tiles.json",
            "product_tile": tile,
            "product_filename": raw_path.name,
            "states": sorted(set(old.get("states") or []) | {args.state}),
            "bbox": metadata["bounds_wgs84"],
            "center": [(west + east) / 2, (south + north) / 2, max(args.minzoom, min(args.maxzoom, 9))],
            "crs": metadata.get("crs"),
            "resolution": metadata.get("resolution"),
            "min_elevation": metadata.get("elevation_min_m"),
            "max_elevation": metadata.get("elevation_max_m"),
            "minzoom": args.minzoom,
            "maxzoom": args.maxzoom,
            "tile_count": tile_count,
            "processing_status": "processed",
            "source_url": product_url(item),
            "downloaded_at": now_iso() if status == "downloaded" else existing_sources.get(sid, {}).get("downloaded_at"),
            "processed_at": now_iso(),
            "raw_file_available": True,
        })
        job["processed"] += 1

    if processed:
        union = unified_bounds(processed)
        if args.incremental:
            mosaic_count = sum(write_incremental_tiles(path, inspect_dem(path), args.minzoom, args.maxzoom, args.tile_size, UNIFIED_TERRAIN_RGB_DIR) for path in raw_paths)
        else:
            registry = terrain_coverage_registry()
            for row in registry.get("sources", []):
                if row.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and row.get("raw_file_path"):
                    raw_paths.append(Path(row["raw_file_path"]))
            raw_paths = sorted(set(path for path in raw_paths if path.exists()))
            mosaic_count = write_mosaic_tiles(raw_paths, union, args.minzoom, args.maxzoom, args.tile_size, True, UNIFIED_TERRAIN_RGB_DIR)
        for row in processed:
            row["mosaic_tile_count"] = mosaic_count
        for path in delete_after:
            if path.exists():
                path.unlink()
        for row in processed:
            if Path(row["raw_file_path"]) in delete_after:
                row["raw_file_available"] = False
                row["raw_file_deleted_at"] = now_iso()
        tj_name, tj_desc = _tilejson_label(args.state)
        write_tilejson(
            {"bounds_wgs84": union, "minzoom": args.minzoom, "maxzoom": args.maxzoom},
            UNIFIED_TILEJSON_PATH,
            TILE_URL,
            tj_name,
            tj_desc,
        )
    job["finished_at"] = now_iso()
    update_registry(processed, job, activate=bool(processed))
    if job["errors"]:
        print("WARN:", "; ".join(job["errors"]))
    print(f"OK: downloaded {job['downloaded']} new DEM(s); processed {job['processed']} DEM(s)")
    print(f"OK: tilejson {UNIFIED_TILEJSON_PATH if processed else 'unchanged'}")
    print(f"OK: registry {TERRAIN_COVERAGE_PATH}")


if __name__ == "__main__":
    main()

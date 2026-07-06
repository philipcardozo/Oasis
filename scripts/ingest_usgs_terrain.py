from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
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

GA_BBOX = (-85.61, 30.35, -80.84, 35.01)
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
    try:
        with urlopen(req, timeout=60) as res, tmp.open("wb") as out:
            shutil.copyfileobj(res, out, 1024 * 1024)
    except (ssl.SSLError, URLError) as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        with urlopen(req, timeout=60, context=ssl._create_unverified_context()) as res, tmp.open("wb") as out:
            shutil.copyfileobj(res, out, 1024 * 1024)
    tmp.replace(dest)
    return "downloaded"


def bbox_arg(value: str | None) -> tuple[float, float, float, float]:
    if not value:
        return GA_BBOX
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
    match = re.search(r"n\d{2}w\d{3}", text, re.I)
    return match.group(0).lower() if match else str(item.get("sourceId") or product_filename(item))


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
    return "ga_" + re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")


def update_registry(sources: list[dict], job: dict, activate: bool) -> None:
    registry = terrain_coverage_registry()
    by_id = {row.get("id"): row for row in registry.get("sources", [])}
    for source in sources:
        by_id[source["id"]] = source
    rows = list(by_id.values())
    bboxes = [r.get("bbox") for r in rows if r.get("bbox")]
    coverage = [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ] if bboxes else None
    active_bboxes = [r.get("bbox") for r in rows if r.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and r.get("bbox")]
    registry |= {
        "schema_version": 1,
        "active_tilejson": "/tiles/terrain-rgb/tiles.json" if activate else registry.get("active_tilejson"),
        "active_source": "usgs_3dep_atlanta_corridor" if activate else registry.get("active_source"),
        "coverage_bbox": coverage,
        "georgia_bbox_coverage_pct": round(clipped_union_pct(active_bboxes, GA_BBOX), 2),
        "total_tile_count": len(list(UNIFIED_TERRAIN_RGB_DIR.glob("*/*/*.png"))) if UNIFIED_TERRAIN_RGB_DIR.exists() else registry.get("total_tile_count", 0),
        "sources": rows,
        "last_job": job,
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


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Discover, download, and process USGS 3DEP terrain from TNMAccess.")
    parser.add_argument("--state", default="GA", choices=["GA"])
    parser.add_argument("--bbox", type=bbox_arg, default=None, help="west,south,east,north; defaults to Georgia")
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
    bbox = args.bbox or GA_BBOX
    tile_filter = {x.strip().lower() for x in args.tiles.split(",") if x.strip()}
    total, items, query_url = discover(endpoint, bbox, 500 if tile_filter else max(args.max_products * 20, 20))
    selected = select_products(items, 1000 if tile_filter else args.max_products, args.prefer_existing)
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
        sid = source_id(raw_path)
        processed.append({
            "id": sid,
            "source_name": "USGS 3DEP / TNMAccess",
            "raw_file_path": str(raw_path),
            "processed_tile_path": str(UNIFIED_TERRAIN_RGB_DIR),
            "public_tilejson": "/tiles/terrain-rgb/tiles.json",
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
        write_tilejson(
            {"bounds_wgs84": union, "minzoom": args.minzoom, "maxzoom": args.maxzoom},
            UNIFIED_TILEJSON_PATH,
            TILE_URL,
            "USGS 3DEP Atlanta Corridor Terrain-RGB",
            "Terrain-RGB tiles derived from TNMAccess-discovered USGS 3DEP GeoTIFF products for the Atlanta corridor foundation.",
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

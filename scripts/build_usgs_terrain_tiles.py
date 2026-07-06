from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

from data_sources import DEFAULT_TNM_URL, METADATA_PATH, PUBLIC_TILE_DIR, TERRAIN_RGB_DIR, TILEJSON_PATH, dem_path, load_env, source_registry


def inspect_dem(path: Path) -> dict:
    with rasterio.open(path) as src:
        bounds_wgs84 = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        arr = src.read(1, masked=True)
        return {
            "source_path": str(path),
            "source_name": path.name,
            "crs": str(src.crs),
            "bounds": list(src.bounds),
            "bounds_wgs84": list(bounds_wgs84),
            "width": src.width,
            "height": src.height,
            "resolution": list(src.res),
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
            "elevation_min_m": float(arr.min()),
            "elevation_max_m": float(arr.max()),
        }


def encode_terrain_rgb(elevation_m: np.ndarray) -> np.ndarray:
    value = np.clip(np.rint((elevation_m + 10000.0) * 10.0), 0, 16777215).astype(np.uint32)
    rgb = np.empty((*value.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = (value >> 16) & 255
    rgb[:, :, 1] = (value >> 8) & 255
    rgb[:, :, 2] = value & 255
    return rgb


def decode_terrain_rgb(rgb: np.ndarray) -> np.ndarray:
    value = rgb[:, :, 0].astype(np.uint32) * 65536 + rgb[:, :, 1].astype(np.uint32) * 256 + rgb[:, :, 2].astype(np.uint32)
    return value.astype(np.float32) * 0.1 - 10000.0


def tile_array(src, tile: mercantile.Tile, tile_size: int, fill: bool = True) -> np.ndarray | None:
    bounds = mercantile.xy_bounds(tile)
    dst = np.full((tile_size, tile_size), np.nan, dtype=np.float32)
    reproject(
        source=rasterio.band(src, 1),
        destination=dst,
        src_transform=src.transform,
        src_crs=src.crs,
        src_nodata=src.nodata,
        dst_transform=from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, tile_size, tile_size),
        dst_crs="EPSG:3857",
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    finite = np.isfinite(dst)
    if not finite.any():
        return None
    if fill:
        dst[~finite] = float(np.nanmin(dst))
    return dst


def write_tiles(path: Path, metadata: dict, minzoom: int, maxzoom: int, tile_size: int, force: bool, terrain_rgb_dir: Path = TERRAIN_RGB_DIR) -> int:
    if force and terrain_rgb_dir.exists():
        shutil.rmtree(terrain_rgb_dir)
    terrain_rgb_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = metadata["bounds_wgs84"]
    count = 0
    with rasterio.open(path) as src:
        for z in range(minzoom, maxzoom + 1):
            tiles = list(mercantile.tiles(west, south, east, north, z))
            for tile in tiles:
                out = terrain_rgb_dir / str(tile.z) / str(tile.x) / f"{tile.y}.png"
                if out.exists() and not force:
                    count += 1
                    continue
                arr = tile_array(src, tile, tile_size)
                if arr is None:
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(encode_terrain_rgb(arr)).save(out)
                count += 1
    return count


def write_mosaic_tiles(paths: list[Path], bounds_wgs84: list[float], minzoom: int, maxzoom: int, tile_size: int, force: bool, terrain_rgb_dir: Path = TERRAIN_RGB_DIR) -> int:
    if force and terrain_rgb_dir.exists():
        shutil.rmtree(terrain_rgb_dir)
    terrain_rgb_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    sources = []
    for path in paths:
        src = rasterio.open(path)
        sources.append((src, transform_bounds(src.crs, "EPSG:3857", *src.bounds, densify_pts=21)))
    try:
        west, south, east, north = bounds_wgs84
        for z in range(minzoom, maxzoom + 1):
            for tile in mercantile.tiles(west, south, east, north, z):
                out = terrain_rgb_dir / str(tile.z) / str(tile.x) / f"{tile.y}.png"
                if out.exists() and not force:
                    count += 1
                    continue
                dst = np.full((tile_size, tile_size), np.nan, dtype=np.float32)
                tile_bounds = mercantile.xy_bounds(tile)
                for src, src_bounds in sources:
                    if tile_bounds.right < src_bounds[0] or tile_bounds.left > src_bounds[2] or tile_bounds.top < src_bounds[1] or tile_bounds.bottom > src_bounds[3]:
                        continue
                    arr = tile_array(src, tile, tile_size, fill=False)
                    if arr is None:
                        continue
                    mask = np.isfinite(arr)
                    dst[mask] = arr[mask]
                if not np.isfinite(dst).any():
                    continue
                dst[~np.isfinite(dst)] = float(np.nanmin(dst))
                out.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(encode_terrain_rgb(dst)).save(out)
                count += 1
    finally:
        for src, _ in sources:
            src.close()
    return count


def write_incremental_tiles(path: Path, metadata: dict, minzoom: int, maxzoom: int, tile_size: int, terrain_rgb_dir: Path = TERRAIN_RGB_DIR) -> int:
    terrain_rgb_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = metadata["bounds_wgs84"]
    count = 0
    with rasterio.open(path) as src:
        for z in range(minzoom, maxzoom + 1):
            for tile in mercantile.tiles(west, south, east, north, z):
                arr = tile_array(src, tile, tile_size, fill=False)
                if arr is None:
                    continue
                mask = np.isfinite(arr)
                if not mask.any():
                    continue
                out = terrain_rgb_dir / str(tile.z) / str(tile.x) / f"{tile.y}.png"
                if out.exists():
                    base = decode_terrain_rgb(np.array(Image.open(out).convert("RGB")))
                else:
                    base = np.array(arr, copy=True)
                    base[~mask] = float(np.nanmin(arr))
                base[mask] = arr[mask]
                out.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(encode_terrain_rgb(base)).save(out)
                count += 1
    return count


def write_metadata(metadata: dict, minzoom: int, maxzoom: int, tile_size: int, tile_count: int, metadata_path: Path = METADATA_PATH, public_tilejson: str = "/tiles/usgs_3dep/tiles.json") -> dict:
    west, south, east, north = metadata["bounds_wgs84"]
    coverage = {str(z): len(list(mercantile.tiles(west, south, east, north, z))) for z in range(minzoom, maxzoom + 1)}
    registry = source_registry()["usgs_3dep_tnmaccess"]
    out = {
        **metadata,
        "tile_format": "Mapbox Terrain-RGB PNG",
        "encoding": "mapbox",
        "tile_size": tile_size,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "generated_tile_count": tile_count,
        "tile_coverage_by_zoom": coverage,
        "public_tilejson": public_tilejson,
        "source_registry": registry,
        "tnm_discovery_example": f"{registry['endpoint'] or DEFAULT_TNM_URL}?{urlencode({'datasets': 'National Elevation Dataset (NED) 1/3 arc-second', 'bbox': ','.join(str(round(x, 6)) for x in [west, south, east, north]), 'prodFormats': 'GeoTIFF'})}",
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(out, indent=2) + "\n")
    return out


def write_tilejson(metadata: dict, tilejson_path: Path = TILEJSON_PATH, tile_url: str = "/tiles/usgs_3dep/terrain-rgb/{z}/{x}/{y}.png", name: str | None = None, description: str | None = None) -> None:
    tilejson_path.parent.mkdir(parents=True, exist_ok=True)
    west, south, east, north = metadata["bounds_wgs84"]
    tilejson = {
        "tilejson": "2.2.0",
        "name": name or "USGS 3DEP 1/3 arc-second n34w085 Terrain-RGB",
        "description": description or "Local Terrain-RGB tiles derived from USGS_13_n34w085_20220725.tif.",
        "version": "1.0.0",
        "scheme": "xyz",
        "tiles": [tile_url],
        "minzoom": metadata["minzoom"],
        "maxzoom": metadata["maxzoom"],
        "bounds": [west, south, east, north],
        "center": [(west + east) / 2, (south + north) / 2, max(metadata["minzoom"], min(metadata["maxzoom"], 9))],
        "encoding": "mapbox",
        "attribution": "USGS 3DEP via The National Map",
    }
    tilejson_path.write_text(json.dumps(tilejson, indent=2) + "\n")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Build local MapLibre Terrain-RGB tiles from the USGS 3DEP GeoTIFF.")
    parser.add_argument("--minzoom", type=int, default=6)
    parser.add_argument("--maxzoom", type=int, default=13)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    path = dem_path()
    if not path.exists():
        raise SystemExit(f"DEM not found: {path}")
    if args.minzoom < 0 or args.maxzoom < args.minzoom:
        raise SystemExit("invalid zoom range")

    metadata = inspect_dem(path)
    tile_count = write_tiles(path, metadata, args.minzoom, args.maxzoom, args.tile_size, args.force)
    metadata = write_metadata(metadata, args.minzoom, args.maxzoom, args.tile_size, tile_count)
    write_tilejson(metadata)
    print(f"OK: inspected {path.name}")
    print(f"OK: wrote {tile_count} Terrain-RGB tiles to {TERRAIN_RGB_DIR}")
    print(f"OK: metadata {METADATA_PATH}")
    print(f"OK: tilejson {TILEJSON_PATH}")


if __name__ == "__main__":
    main()

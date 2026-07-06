from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
DEFAULT_DEM = ROOT / "data" / "raw" / "usgs_3dep" / "USGS_13_n34w085_20220725.tif"
PROCESSED_DIR = ROOT / "data" / "processed" / "usgs_3dep"
PUBLIC_TILE_DIR = ROOT / "graph" / "tiles" / "usgs_3dep"
TERRAIN_RGB_DIR = PUBLIC_TILE_DIR / "terrain-rgb"
TILEJSON_PATH = PUBLIC_TILE_DIR / "tiles.json"
METADATA_PATH = PROCESSED_DIR / "USGS_13_n34w085_20220725.metadata.json"
UNIFIED_PUBLIC_TILE_DIR = ROOT / "graph" / "tiles" / "terrain-rgb"
UNIFIED_TERRAIN_RGB_DIR = UNIFIED_PUBLIC_TILE_DIR
UNIFIED_TILEJSON_PATH = UNIFIED_PUBLIC_TILE_DIR / "tiles.json"
TERRAIN_COVERAGE_PATH = PROCESSED_DIR / "terrain_coverage.json"
DEFAULT_TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
GEORGIA_BBOX = (-85.61, 30.35, -80.84, 35.01)


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def project_path(raw: str | None, default: Path) -> Path:
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def dem_path() -> Path:
    load_env()
    return project_path(os.environ.get("USGS_3DEP_DEM_PATH"), DEFAULT_DEM)


def source_registry() -> dict[str, Any]:
    load_env()
    return {
        "usgs_3dep_tnmaccess": {
            "name": "USGS 3DEP / TNMAccess",
            "endpoint": os.environ.get("TNM_ACCESS_PRODUCTS_URL") or DEFAULT_TNM_URL,
            "purpose": "Discover and download future DEM products by bbox, state, county, or area of interest.",
            "active_local_dem": str(dem_path()),
            "processed_metadata": str(METADATA_PATH),
            "tilejson": "/tiles/usgs_3dep/tiles.json",
            "active": True,
        },
        "eia": {
            "name": "EIA Open Data",
            "key_env": "EIA_API_KEY",
            "purpose": "Future electricity prices, generation, energy demand, and grid indicators.",
            "configured": bool(os.environ.get("EIA_API_KEY")),
        },
        "data_gov": {
            "name": "api.data.gov",
            "key_env": "DATA_GOV_API_KEY",
            "purpose": "Future FEMA, FBI aggregate crime, and other public api.data.gov datasets.",
            "configured": bool(os.environ.get("DATA_GOV_API_KEY")),
        },
    }


def dem_tilejson() -> dict[str, Any] | None:
    for path in (UNIFIED_TILEJSON_PATH, TILEJSON_PATH):
        if path.exists():
            return json.loads(path.read_text())
    return None


def dem_metadata() -> dict[str, Any] | None:
    if not METADATA_PATH.exists():
        return None
    return json.loads(METADATA_PATH.read_text())


def public_tile_dir(tilejson: dict[str, Any] | None) -> Path:
    if not tilejson or not tilejson.get("tiles"):
        return TERRAIN_RGB_DIR
    public = str(tilejson["tiles"][0]).split("{z}", 1)[0].strip("/")
    if public.startswith("tiles/"):
        public = public[len("tiles/") :]
    return ROOT / "graph" / "tiles" / public


def terrain_coverage_registry() -> dict[str, Any]:
    if TERRAIN_COVERAGE_PATH.exists():
        return json.loads(TERRAIN_COVERAGE_PATH.read_text())
    metadata = dem_metadata()
    tilejson = dem_tilejson()
    if not metadata or not tilejson:
        return {"schema_version": 1, "sources": [], "active_tilejson": None, "active_source": None, "last_job": None}
    return {
        "schema_version": 1,
        "active_tilejson": "/tiles/usgs_3dep/tiles.json",
        "active_source": "local_usgs_13_n34w085_20220725",
        "coverage_bbox": tilejson.get("bounds"),
        "total_tile_count": metadata.get("generated_tile_count", 0),
        "sources": [
            {
                "id": "local_usgs_13_n34w085_20220725",
                "source_name": "USGS 3DEP / TNMAccess",
                "raw_file_path": metadata.get("source_path"),
                "processed_tile_path": str(TERRAIN_RGB_DIR),
                "public_tilejson": "/tiles/usgs_3dep/tiles.json",
                "bbox": metadata.get("bounds_wgs84"),
                "center": tilejson.get("center"),
                "crs": metadata.get("crs"),
                "resolution": metadata.get("resolution"),
                "min_elevation": metadata.get("elevation_min_m"),
                "max_elevation": metadata.get("elevation_max_m"),
                "minzoom": metadata.get("minzoom"),
                "maxzoom": metadata.get("maxzoom"),
                "tile_count": metadata.get("generated_tile_count", 0),
                "processing_status": "processed",
                "source_url": None,
                "downloaded_at": None,
                "processed_at": None,
            }
        ],
        "last_job": None,
    }


def covers_bbox(coverage: list[float] | tuple[float, ...] | None, target: tuple[float, float, float, float]) -> bool:
    return bool(coverage and coverage[0] <= target[0] and coverage[1] <= target[1] and coverage[2] >= target[2] and coverage[3] >= target[3])


def validation_status() -> dict[str, Any]:
    load_env()
    tilejson = dem_tilejson()
    metadata = dem_metadata()
    registry = terrain_coverage_registry()
    active_tilejson = registry.get("active_tilejson")
    georgia_pct = float(registry.get("georgia_bbox_coverage_pct") or 0)
    georgia_products_pct = float(registry.get("georgia_available_products_coverage_pct") or 0)
    coverage_label = (
        "Georgia complete available 3DEP product coverage" if active_tilejson == "/tiles/terrain-rgb/tiles.json" and georgia_products_pct >= 100
        else
        "Georgia" if active_tilejson == "/tiles/terrain-rgb/tiles.json" and covers_bbox(registry.get("coverage_bbox"), GEORGIA_BBOX)
        else "Georgia high-coverage terrain foundation" if active_tilejson == "/tiles/terrain-rgb/tiles.json" and georgia_pct >= 90
        else "north and central Georgia / Atlanta corridor" if active_tilejson == "/tiles/terrain-rgb/tiles.json"
        else "northwest Georgia / eastern Alabama"
    )
    tile_dir = public_tile_dir(tilejson)
    sample_tiles = list(tile_dir.glob("*/*/*.png"))[:1] if tile_dir.exists() else []
    checks = [
        {"name": "EIA_API_KEY", "ok": bool(os.environ.get("EIA_API_KEY")), "message": "OK: EIA_API_KEY loaded" if os.environ.get("EIA_API_KEY") else "ERROR: EIA_API_KEY missing"},
        {"name": "DATA_GOV_API_KEY", "ok": bool(os.environ.get("DATA_GOV_API_KEY")), "message": "OK: DATA_GOV_API_KEY loaded" if os.environ.get("DATA_GOV_API_KEY") else "ERROR: DATA_GOV_API_KEY missing"},
        {"name": "TNM_ACCESS_PRODUCTS_URL", "ok": bool(os.environ.get("TNM_ACCESS_PRODUCTS_URL") or DEFAULT_TNM_URL), "message": "OK: TNMAccess endpoint configured"},
        {"name": "USGS_3DEP_DEM_PATH", "ok": dem_path().exists(), "message": "OK: local DEM found" if dem_path().exists() else f"ERROR: local DEM missing at {dem_path()}"},
    ]
    terrain_ready = bool(tilejson and sample_tiles)
    return {
        "checks": checks,
        "sources": source_registry(),
        "dem": {
            "available": terrain_ready,
            "status": "loaded" if terrain_ready else "DEM unavailable",
            "raw_path": str(dem_path()),
            "metadata": metadata,
            "tilejson_url": registry.get("active_tilejson") or ("/tiles/usgs_3dep/tiles.json" if tilejson else None),
            "active_tilejson_url": registry.get("active_tilejson") or ("/tiles/usgs_3dep/tiles.json" if tilejson else None),
            "tilejson": tilejson,
            "tiles_found": bool(sample_tiles),
            "coverage": registry,
            "coverage_label": coverage_label,
        },
    }


def main() -> None:
    status = validation_status()
    for check in status["checks"]:
        print(check["message"])
    dem = status["dem"]
    print(("OK" if dem["available"] else "ERROR") + f": terrain tiles {dem['status']}")


if __name__ == "__main__":
    main()

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
DEFAULT_TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"


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
    if not TILEJSON_PATH.exists():
        return None
    return json.loads(TILEJSON_PATH.read_text())


def dem_metadata() -> dict[str, Any] | None:
    if not METADATA_PATH.exists():
        return None
    return json.loads(METADATA_PATH.read_text())


def validation_status() -> dict[str, Any]:
    load_env()
    tilejson = dem_tilejson()
    metadata = dem_metadata()
    sample_tiles = list(TERRAIN_RGB_DIR.glob("*/*/*.png"))[:1] if TERRAIN_RGB_DIR.exists() else []
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
            "tilejson_url": "/tiles/usgs_3dep/tiles.json" if tilejson else None,
            "tilejson": tilejson,
            "tiles_found": bool(sample_tiles),
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

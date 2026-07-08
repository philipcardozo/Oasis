# Reliefs: terrain (AWS default + USGS 3DEP AOI)

## Default: AWS Terrain Tiles (global, no key)

The globe's default terrain + hillshade now come from **AWS Terrain Tiles**
(Tilezen "Joerd" on the AWS Open Data program): global coverage, z0–z15,
terrarium-encoded, free, no API key. Wired client-side in `graph/js/main.js`
(`AWS_TERRAIN_TILEJSON`, `addPhysicalContextLayers`) as a MapLibre `raster-dem`
source with `"encoding": "terrarium"`. Attribution: *Terrain: Tilezen/Mapzen,
USGS 3DEP, SRTM, GMTED, ETOPO1 (AWS Open Data)*.

`/api/reliefs/dem/status` now reports `{ "source": "aws"|"local", "ready": bool }`
(the old nested state coverage-label was removed from `data_sources.py`).

## Optional: local USGS 3DEP high-resolution AOI

The local 3DEP pipeline is retained as an **on-demand high-resolution AOI tool**,
not a default. Set `productPrefs.terrainSource = "local"` to use locally-built
tiles when present. Builders live in `scripts/terrain_aoi/` (+
`scripts/build_usgs_terrain_tiles.py`); the bulk 50-state tile tree under
`graph/tiles/terrain-rgb/` is regenerable and may be removed from disk. The
processed metadata (`data/processed/usgs_3dep/*.metadata.json`) is the record of
work and is kept.

The rest of this doc describes that local 3DEP pipeline.

This stage uses local USGS 3DEP GeoTIFFs as the first real Reliefs data source.

## Raw Data

- Seed raw DEM: `data/raw/usgs_3dep/USGS_13_n34w085_20220725.tif`
- Source family: USGS 3DEP / TNMAccess
- Raw data is not mutated by the conversion script.
- Most ingested raw DEMs are deleted after processing with `--delete-raw-after-process` to avoid filling local disk; their processed metadata remains in `data/processed/usgs_3dep/`.

## Generated Data

- Metadata: `data/processed/usgs_3dep/USGS_13_n34w085_20220725.metadata.json`
- Terrain coverage registry: `data/processed/usgs_3dep/terrain_coverage.json`
- TileJSON: `graph/tiles/usgs_3dep/tiles.json`
- Terrain-RGB PNG tiles: `graph/tiles/usgs_3dep/terrain-rgb/{z}/{x}/{y}.png`
- Unified Southeast TileJSON: `graph/tiles/terrain-rgb/tiles.json`
- Unified Southeast Terrain-RGB PNG tiles: `graph/tiles/terrain-rgb/{z}/{x}/{y}.png`

The generated tiles use Mapbox Terrain-RGB encoding for MapLibre `raster-dem` sources.

## Regenerate Tiles

Install the small geospatial toolchain if needed:

```bash
python3 -m pip install --user rasterio mercantile
```

Regenerate the Terrain-RGB tiles:

```bash
python3 scripts/build_usgs_terrain_tiles.py --force
```

Default coverage is z6-z13. The source DEM is about one degree around northwest Georgia/eastern Alabama, so TileJSON bounds prevent MapLibre from requesting it globally.

## TNMAccess Ingestion

Dry-run Georgia DEM discovery without downloading:

```bash
python3 scripts/ingest_usgs_terrain.py --state GA --max-products 2 --dry-run
```

Process the bounded Atlanta-corridor foundation area. This keeps downloads limited, uses z6-z11, and writes the unified terrain source:

```bash
python3 scripts/ingest_usgs_terrain.py --state GA --bbox=-85.05,33.01,-83.95,33.99 --max-products 1 --no-dry-run --minzoom 6 --maxzoom 11
```

Expand the corridor to at least 25% of the Georgia bbox without calling it full-state coverage:

```bash
python3 scripts/ingest_usgs_terrain.py --state GA --bbox=-85.05,32.01,-83.05,35.01 --max-products 7 --no-dry-run --minzoom 6 --maxzoom 11
```

Expand the corridor to at least 40% of the Georgia bbox:

```bash
python3 scripts/ingest_usgs_terrain.py --state GA --bbox=-83.05,32.01,-82.05,35.01 --max-products 6 --no-dry-run --minzoom 6 --maxzoom 11
```

Continue toward maximum Georgia coverage with explicit high-value tiles:

```bash
python3 scripts/ingest_usgs_terrain.py --state GA --bbox=-85.61,30.35,-80.84,35.01 --tiles n32w086,n35w085 --max-products 2 --no-dry-run --minzoom 6 --maxzoom 11
```

Current approved coverage:

- Scope: Georgia + Florida + South Carolina + North Carolina complete available 3DEP product coverage
- Georgia DEM products in the unified source: 35 of 35 returned by TNMAccess for the Georgia bbox
- Florida DEM products in the unified source: 35 of 35 returned by TNMAccess for the Florida bbox
- South Carolina DEM products in the unified source: 23 of 23 returned by TNMAccess for the South Carolina bbox
- North Carolina DEM products in the unified source: 38 of 38 returned by TNMAccess for the North Carolina bbox
- Available-product coverage: 100% for all four states
- Georgia rectangular bbox coverage: about 99.5%; the remaining sliver is from the coarse rectangular query boundary, not an unprocessed TNMAccess DEM product.
- Florida rectangular bbox coverage: about 50.3%; the rectangle includes large ocean areas outside useful land DEM coverage.
- South Carolina rectangular bbox coverage: about 97.1%.
- North Carolina rectangular bbox coverage: about 99.0%.
- Unified Terrain-RGB tiles: 4,286 at z6-z11

Process one state tile safely:

```bash
python3 scripts/ingest_usgs_terrain.py --state NC --tiles n37w085 --max-products 1 --no-dry-run --minzoom 6 --maxzoom 11 --incremental --delete-raw-after-process
```

Useful safety knobs:

- `--dry-run` is the default; use `--no-dry-run` only after reviewing product sizes.
- `--max-products 1` keeps the first test bounded.
- `--max-mb 750` skips unexpectedly large products.
- `--minzoom 6 --maxzoom 11` avoids high-zoom tile explosions while this remains corridor coverage.
- `--force` clears the unified tile folder before processing the selected product.
- `--delete-raw-after-process` keeps the generated tiles and metadata, then removes newly downloaded raw GeoTIFFs.

Raw downloads go to `data/raw/usgs_3dep/`. Processed unified terrain tiles go to `graph/tiles/terrain-rgb/`. The current manual DEM remains available at `graph/tiles/usgs_3dep/tiles.json` as fallback.

If TNMAccess returns a warning payload instead of products, the script exits without updating the terrain registry. Re-run the same dry-run command later before using `--no-dry-run`.

## Environment

Create `.env` from `.env.example` and set:

- `EIA_API_KEY`
- `DATA_GOV_API_KEY`
- `TNM_ACCESS_PRODUCTS_URL`
- `USGS_3DEP_DEM_PATH`

`.env` is ignored by git. Do not expose these values in frontend code or browser requests.

## Backend Status

Validation endpoints:

- `GET /api/data-sources/status`
- `GET /api/reliefs/dem/status`
- `GET /api/reliefs/dem/tilejson`
- `GET /api/reliefs/terrain/sources`
- `GET /api/reliefs/terrain/coverage`
- `GET /api/reliefs/terrain/jobs/status`

These endpoints report whether keys and DEM tiles are configured, but they do not return API key values.

## TNMAccess Future Use

TNMAccess will be used to discover future DEM products by bbox, state, county, or area of interest:

`https://tnmaccess.nationalmap.gov/api/v1/products`

The ingestion script currently uses the TNMAccess dataset label `National Elevation Dataset (NED) 1/3 arc-second`, which returns the `USGS_13_...tif` GeoTIFF products used by the working DEM.

## Current Reliefs Layer Status

Real data:

- Terrain / relief: local USGS 3DEP Terrain-RGB tiles
- Hillshade: local USGS 3DEP Terrain-RGB tiles

Placeholders:

- Mountains / slope
- Plateaus
- Rivers / water bodies
- Vegetation
- Weather
- Infrastructure
- Crime aggregates
- Public cameras where legally available

If DEM tiles are missing, the map still loads and the Reliefs panel reports `DEM unavailable`.

## QA Checklist

- Open `http://127.0.0.1:8792/?reliefDemo=1`.
- Check `GET /api/reliefs/dem/status` returns `available: true`.
- Check `GET /api/reliefs/dem/tilejson` returns `/tiles/usgs_3dep/terrain-rgb/{z}/{x}/{y}.png`.
- If unified ingestion has run, `GET /api/reliefs/dem/tilejson` returns `/tiles/terrain-rgb/{z}/{x}/{y}.png`.
- In browser Network, filter `terrain-rgb`; USGS 3DEP PNG tiles should return `200`.
- Reliefs panel should show:
  - Terrain / relief: `loaded`
  - Hillshade: `loaded`
  - Other Reliefs layers: `not loaded yet`
  - Status text: `DEM loaded · Coverage: Georgia + Florida + South Carolina + North Carolina complete available 3DEP product coverage · Zoom range: z6-z11 · Source: USGS 3DEP`
- Move the terrain exaggeration slider; `map.getTerrain().exaggeration` should update without reload.
- Known non-fatal MapLibre warnings:
  - Same DEM source used for hillshade and terrain.
  - `calculateFogMatrix is not supported on globe projection`.

# Reliefs: USGS 3DEP DEM

This stage uses one local USGS 3DEP GeoTIFF as the first real Reliefs data source.

## Raw Data

- Raw DEM: `data/raw/usgs_3dep/USGS_13_n34w085_20220725.tif`
- Source family: USGS 3DEP / TNMAccess
- Raw data is not mutated by the conversion script.

## Generated Data

- Metadata: `data/processed/usgs_3dep/USGS_13_n34w085_20220725.metadata.json`
- TileJSON: `graph/tiles/usgs_3dep/tiles.json`
- Terrain-RGB PNG tiles: `graph/tiles/usgs_3dep/terrain-rgb/{z}/{x}/{y}.png`

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

These endpoints report whether keys and DEM tiles are configured, but they do not return API key values.

## TNMAccess Future Use

TNMAccess will be used to discover future DEM products by bbox, state, county, or area of interest:

`https://tnmaccess.nationalmap.gov/api/v1/products`

The metadata file includes an example query for the current DEM bounds. This stage keeps the local downloaded GeoTIFF as the active DEM.

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

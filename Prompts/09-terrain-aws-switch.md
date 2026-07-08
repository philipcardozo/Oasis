# 09 — Terrain: switch default to AWS Terrain Tiles, retire bulk 3DEP builds

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 01 (tiles untracked from git). Ponytail rules apply.

## Decision (Option A — default)

Default globe terrain/hillshade moves to **AWS Terrain Tiles** (Tilezen
"Joerd" dataset on the AWS Open Data program): global coverage, z0–z15,
free, no API key, terrarium encoding, served from
`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`.
MapLibre supports it natively via `"encoding": "terrarium"` on a
`raster-dem` source. The local USGS 3DEP pipeline is kept as an on-demand
high-resolution AOI tool, not a default, and the 5 GB / ~83k-PNG bulk tile
tree is removed from the working tree.

## Context

- Local tiles live in `graph/tiles/terrain-rgb/` (Mapbox terrain-rgb
  encoding, z6–z13, all 50 states, ~83,000 PNGs, 5 GB), built by
  `scripts/build_usgs_terrain_tiles.py` + `scripts/run_full_state_ingest.py`,
  registry in `data/processed/usgs_3dep/terrain_coverage.json` (1,341 sources).
- Frontend terrain wiring: `graph/index.html`/`graph/js/globe.js` reads
  `TERRAIN_STATUS_URL` → `/api/reliefs/dem/status`; `data_sources.py`
  (`validation_status`, `terrain_coverage_registry`) and `map_api.py`
  `/api/reliefs/*` routes serve tilejson/coverage.

## Task

1. Add the AWS terrarium source as the default `raster-dem` in the globe
   (terrain + hillshade). Attribution: add "Terrain: Tilezen/Mapzen, USGS
   3DEP, SRTM, GMTED, ETOPO1 (AWS Open Data)" to the map attribution control.
2. Keep the local-tiles path as a fallback/override: if the local tilejson
   exists AND a user setting (`productPrefs.terrainSource = "local"`) selects
   it, use it; otherwise AWS. Simplify `/api/reliefs/dem/status` to report
   `{source: "aws"|"local", ready: bool}` — delete the 50-state
   `coverage_label` ternary chain in `data_sources.py` (states list logic can
   go; keep the registry file readable for the AOI tool).
3. Archive, don't delete, the pipeline: move `run_all_remaining_states.py`
   and `run_full_state_ingest.py` under `scripts/terrain_aoi/` with a short
   README saying they're for high-res AOI builds. `build_usgs_terrain_tiles.py`
   stays (it's the AOI builder).
4. After the user confirms the AWS source renders correctly across a few
   states + zoom levels, delete `graph/tiles/terrain-rgb/` from disk
   (5 GB). **Ask in-session before deleting**; they are regenerable from the
   registry but the rebuild takes a long time. Keep
   `data/processed/usgs_3dep/*.metadata.json` (small, the record of work).
5. Update `docs/reliefs_usgs_3dep.md` to describe the new default + AOI flow.

## Option B (if the owner rejects the remote dependency)

Self-host: convert `graph/tiles/terrain-rgb/` into a single `terrain.pmtiles`
(pmtiles CLI or `pmtiles` Python package — the one allowed new dep), serve
via the `pmtiles://` protocol with maplibre + pmtiles JS (vendor the small
JS locally, no CDN). Same UI wiring; US-only coverage remains.

## Acceptance checks

- Globe terrain + hillshade render over Georgia, Colorado, Alaska, AND a
  non-US area (Alps) — the last one is impossible with the old tiles.
- Zoom z4→z13 shows no seams/black tiles; offline (network blocked) the app
  still loads with terrain disabled gracefully (no console spam, status
  reports not-ready).
- `git status` untouched by tile changes (prompt 01 rules hold).
- `data_sources.py` no longer contains the nested coverage-label conditional;
  `python3 data_sources.py` prints a sane status.
- Disk under `graph/tiles/` < 100 MB after cleanup (Option A).

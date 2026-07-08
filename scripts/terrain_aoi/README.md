# Terrain AOI builders (high-resolution, on-demand)

The default globe terrain is now **AWS Terrain Tiles** (global terrarium, no key) —
see `docs/reliefs_usgs_3dep.md`. These scripts build the *optional* local USGS 3DEP
terrain-rgb tiles for a specific area of interest (AOI), used only when a user sets
`productPrefs.terrainSource = "local"`. They are slow (large DEM downloads +
tiling) and are not part of the normal refresh.

- `scripts/build_usgs_terrain_tiles.py` — the AOI tile builder (kept at scripts/).
- `run_full_state_ingest.py` — ingest a full state's 3DEP products.
- `run_all_remaining_states.py` — batch the remaining states.

Output tiles go to `graph/tiles/terrain-rgb/` (gitignored); the registry is
`data/processed/usgs_3dep/terrain_coverage.json`.

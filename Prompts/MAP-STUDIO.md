# MAP STUDIO — selectable basemaps + 3 map slots + Conditions placeholder

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. **Run prompt 16
first** (a clean tree currently has no map data and 12 failing tests). Ponytail
rules: smallest working diff, no framework, no full MapLibre rewrite, reuse the
existing style-reload machinery. Product spec = Obsidian vault (never read its
`Restricted information` folder).

## Grounding — the architecture already supports this

Read these before coding; they are the seams you build on:

- **Control buttons** live in `graph/index.html` (~L26–29): `#gearBtn`
  (settings gear) and `#dataBtn` (data layers), both `class="tool-btn"`. The
  new Map Studio button goes **next to them**.
- **Panel pattern**: `#gearPanel`/`#workspacePanel` toggled via
  `toggleToolPanel(...)` in `graph/js/main.js`; `#gearBtn.onclick` (~L2234).
  Add `#studioPanel` the same way.
- **Basemap switching is a solved problem here.** `createMapGlobe` registers
  `map.on("style.load", …)` (main.js ~L1168) which re-runs `addMapLayers()` —
  which re-adds terrain (`addPhysicalContextLayers`), companies, securities,
  relationships, cluster/node/label layers, manual layers, and re-applies
  `applyProductPrefs()`. So **`map.setStyle(newUrl)` already re-adds every
  overlay after the new base loads.** You are wiring a style picker to
  `setStyle`, not rebuilding the map. (`addMapLayers` guards on
  `getSource("companies")`, which is cleared by `setStyle` — so it re-runs.)
- **Current basemap**: `MAP_STYLE_URL="https://tiles.openfreemap.org/styles/liberty"`
  (main.js ~L1114). **Terrain**: AWS terrarium DEM (`AWS_TERRAIN_TILEJSON`,
  ~L1118) + `terrain-hillshade` layer, controlled by `productPrefs.engine.terrain`
  / `terrainExaggeration` / `terrainSource`.
- **Persistence**: `productPrefs` (`graph/js/state.js` ~L39) → `saveProductPrefs()`
  (localStorage). `productPrefs.dataLayers`, `.engine`, `.terrainSource` already
  live here. Add `productPrefs.basemap` and `productPrefs.mapSlots` alongside.
- **View state**: `captureViewState()` already serializes mode/camera/filters/
  selection; prompt 12 added `.oasis.json` workspace export. **A map slot is a
  named workspace** — reuse both, don't reinvent.

## Terrain reality (IMPORTANT — reconcile before writing cards)

The old local USGS 3DEP tiles (`/tiles/usgs_3dep/tiles.json`,
`/tiles/usgs_3dep/terrain-rgb/...`) were **deleted in prompt 09** — `graph/tiles/`
no longer exists. Do **not** try to verify or serve them, and do **not**
regenerate them in this task. Terrain is now the **AWS terrarium overlay**
(global, built from the same USGS 3DEP + SRTM data), which composes over ANY
basemap. So:

- **Basemaps (3, mutually exclusive):** Standard, Dark, Satellite.
- **Terrain (AWS)** is an **overlay toggle**, not a fourth basemap — it already
  works over the current base and must keep working over all three.
- High-res local 3DEP is now an on-demand AOI build only (`scripts/terrain_aoi/`);
  surface it as "on-demand", not a live style.

## Basemap styles to add (free, no API key)

1. **Standard** — the existing `MAP_STYLE_URL` (OpenFreeMap Liberty). Labels,
   roads, boundaries, terrain-compatible. Best for general geography.
2. **Dark minimal** — recommend CARTO `dark-matter`
   (`https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`, no key).
   Reduces noise; best for the company graph, arcs, financial network. (If you
   prefer zero new remote host, recolor Liberty via a patch function instead —
   more work; pick one and note it.)
3. **Satellite** — ESRI World Imagery raster, no key: a minimal MapLibre style
   with one raster source
   `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
   attribution "Imagery © Esri, Maxar, Earthstar Geographics". Best for farms,
   industrial sites, data centers, physical due diligence. **Note:** raster
   satellite has **no vector labels/roads** and no symbol layers — so
   `firstSymbolLayerId()` returns undefined (layers add on top; verify no crash)
   and `normalizeBaseMapLabels()` must no-op safely. This is the concrete case
   for the panel's "feature not supported by this basemap" warning (labels).

Keep style URLs in one small config object (e.g. `BASEMAPS` in `config.js`):
`{id, name, styleUrl|styleSpec, bestFor, supports:{labels,terrain,boundaries}}`.
No fragile per-call hardcoding.

## UI

**Button:** add `#studioBtn` (`class="tool-btn"`) next to `#gearBtn`/`#dataBtn`,
icon = a layers/stack or globe-gear glyph, `aria-label="Map Studio"`,
`title="Map Studio"`. Opens `#studioPanel` (right-side/floating, same show/hide
class pattern as the other tool panels).

**Panel sections:**

1. **Map Styles** — preview cards for Standard / Dark / Satellite. Each card:
   name, small thumbnail/preview area (a static swatch or tiny canvas is fine —
   no live mini-map required), best-use-case line, available status, selected
   state (strong highlight on the active one). Clicking a card switches the
   basemap (see behavior below).
2. **Compatible overlays / warnings** — show which overlays are active and
   whether the current basemap supports them (e.g. Satellite → "Labels: not
   provided by this basemap"; Terrain: supported on all three). Warning row when
   a feature isn't supported.
3. **Conditions (placeholder)** — disabled toggles, labelled "not loaded yet":
   Clouds, Hurricanes/storms, Precipitation, Temperature, Wind, Wildfire/smoke,
   Flood alerts, Weather radar. **UI architecture only — no weather ingestion.**
   Persist their (disabled) state shape so the wiring exists for later.
4. **Map Slots** — Slot 1 / 2 / 3. Each: select/load, rename, "save current
   setup", reset, shows its basemap + active-overlay count. Example default
   names: "Standard Research", "Dark Network View", "Satellite Site Analysis".
5. **Save / Reset current map setup** — buttons (save writes to the selected
   slot; reset returns to defaults). Placeholders are acceptable only if wired
   to the slot store below (don't ship dead buttons).

## Basemap switch behavior (safe, reuse existing machinery)

On card click:
1. Set `productPrefs.basemap = id`; `saveProductPrefs()`.
2. Call `map.setStyle(BASEMAPS[id].styleUrl)` (for the satellite raster style,
   pass the inline style spec). Patch the Standard/Dark vector styles through
   the existing `patchBaseMapStyle()` where applicable.
3. The existing `map.on("style.load")` handler re-adds terrain, companies,
   securities, relationships, data layers, and re-applies prefs. **Verify** this
   fires and everything returns — do not add a parallel re-add path.
4. `initMapGlobe`/`loadBaseMapStyle` must honor `productPrefs.basemap` on first
   load (not always Liberty), so a saved basemap survives reload.

Guarantees to verify after switching: company clusters/nodes/arcs reappear;
terrain + hillshade still work (AWS DEM re-added); Data Layers panel state is
unchanged (`productPrefs.dataLayers` untouched); terrain exaggeration preserved.

## Map slots + "user" model (NO real auth)

OASIS has **no auth/user system** and the vault defers accounts until the
readiness gate — do **not** build login/passwords/backend here. Build the
**local-dev foundation** only:

- A `productPrefs.mapSlots` array of up to **3** slots in localStorage, clearly
  dev/local-only (comment + a small "local profile (dev)" label in the panel).
- Slot shape = a named workspace: `{name, basemap, engine (incl.
  terrainExaggeration), dataLayers, terrainSource, viewState (from
  captureViewState: camera center/zoom, mode, filters, selection), graphVisibility,
  conditions}`. **Reuse `captureViewState()` + the prompt-12 workspace
  serialization** — a slot is a workspace with a name and a basemap.
- Save current → writes the active config into the chosen slot. Load → applies
  it atomically (setStyle + apply prefs + restore view) via the existing restore
  path. Rename/reset per slot.

Persist now: selected basemap, terrain/hillshade on-state, terrain exaggeration,
active data-layer toggles, camera center/zoom, selected slot + slot names.

## Do not

Full MapLibre rewrite · recreate whole app state on switch · break Reliefs/
terrain state · break company graph layers · hardcode style logic across the
codebase · build weather ingestion · build real/production auth · expose any API
key or secret in the frontend (none of the chosen sources need a key — keep it
that way).

## Testing / acceptance checks

1. `python3 -m pytest -q` still green (prompt 16 first).
2. App loads with a populated globe; no new console errors.
3. Map Studio button opens the panel; three style cards render with selected
   state.
4. Switch Standard → Dark → Satellite: basemap changes each time.
5. After each switch: company nodes/arcs reappear; terrain + hillshade still
   work; Data Layers toggles unchanged.
6. Satellite basemap shows the "labels not provided" warning and does not crash
   (`firstSymbolLayerId` undefined path handled).
7. Save current setup into Slot 2; change things; reload Slot 2 → basemap,
   overlays, terrain, and camera restore.
8. Reload the page → selected basemap + slot names persist (localStorage).
9. Conditions toggles render disabled / "not loaded yet"; no weather network
   calls fire.
10. No API keys/secrets in the frontend or network tab.
11. Verify in the owner's real browser for the cross-host styles (CARTO dark,
    ESRI imagery) — the preview sandbox may block those hosts.

## Deliverable

A Map Studio foundation: new top-right icon button; Standard/Dark/Satellite
basemap cards with safe `setStyle`-based switching that preserves terrain,
company graph, and Data Layers; a Conditions placeholder section; and a 3-slot
local-dev map-customization system reusing the existing workspace/view-state
serialization. No auth, no weather ingestion, no tile regeneration.

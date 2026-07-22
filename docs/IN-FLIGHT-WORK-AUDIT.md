# In-Flight Work Audit

**Date:** 2026-07-22 · **Baseline:** `70238f0` · **Branch:** `main`
**Scope:** 9 modified + 2 untracked paths, +1,742 / −273 lines.
**Backup:** `.local-backups/pre-audit-working-tree.patch` (142 KB, gitignored).
No Phase 0 fixes were implemented during this audit.

---

## 1. Executive verdict

### `SAFE TO COMMIT`

The uncommitted work is a coherent, well-executed **performance and
self-hosting pass**. It adds an HTTP caching layer (ETag / gzip / cache-control)
with explicit static routes, two new payload endpoints, mtime-keyed read caches
across the data modules, a DCF workbook cache, and defers expensive frontend
work (MapLibre now vendored and lazy-loaded instead of a blocking CDN script).

It introduces **no new required dependency**, **no schema change**, **no API
break** (17 routes added, **0 removed or modified**), and **no secrets**. Tests
hold at the established baseline. It is not a rewrite and does not conflict with
Phase 0 — it actually makes two Phase 0 tasks easier.

Two items are flagged below as **follow-ups, not blockers**: startup cache
warming can perform SEC network I/O on a cold machine, and `ujson` is used
opportunistically without being declared.

---

## 2. Modified-file inventory

| File | Δ | Purpose | Complete | New dep | API change | Schema | Network | OS paths | Tests |
|---|---|---|---|---|---|---|---|---|---|
| `map_api.py` | +1457/−? | HTTP caching layer, static routes, 3 new endpoints, startup warming | Yes | no | additive only | no | **startup only** (see §7) | no | partial |
| `store.py` | +35 | mtime-keyed caches, `node_count()`, lazy duckdb import | Yes | no | no | no | no | no | yes |
| `data_sources.py` | +31 | mtime-keyed caches for DEM/tilejson/coverage | Yes | no | no | no | no | no | indirect |
| `political.py` | +62 | mtime-keyed caches, lazy duckdb import | Yes | no | no | no | no | no | yes |
| `dcf_export.py` | +66 | workbook cache, lazy openpyxl/urllib, `fast_json` | Yes | **optional `ujson`** | no | no | unchanged (pre-existing) | no | yes |
| `graph/js/main.js` | +244 | vendored+lazy MapLibre, deferred grid/index/quality | Yes | no | consumes new endpoints | no | no | no | Playwright |
| `graph/index.html` | +8 | drop unpkg CDN, preconnect hints, 96px favicon | Yes | no | no | no | removes 2 CDN deps | no | Playwright |
| `graph/js/config.js` | +1 | `glyphs` on satellite styleSpec | Yes | no | no | no | no | no | Playwright |
| `test_map_intelligence_api.py` | +111 | coverage for new endpoints/caching | Yes | no | — | — | no | no | — |
| `graph/vendor/` | new 984K | vendored MapLibre 5.6.2 (js+css) | Yes | removes CDN | — | — | — | — | — |
| `graph/Logo_Dark_BG_96.png` | new 4K | 96px favicon (replaces 347 KB original) | Yes | — | — | — | — | — | — |

`.gitignore` was also modified **by this audit** to ignore `.local-backups/`.

---

## 3. Feature-level explanation

**A. Self-hosted MapLibre (removes two CDN dependencies).** `index.html` drops
the blocking `unpkg.com` script/stylesheet; `main.js` lazy-loads
`vendor/maplibre-gl/5.6.2/*` via `ensureMapLibre()` only when the globe is
needed. Favicon shrinks 347 KB → 4 KB. Adds `preconnect` hints for the tile and
glyph hosts. This is a real supply-chain and startup win.

**B. HTTP caching layer.** New helpers (`cache_etag`, `request_has_etag`,
`cached_bytes_response`, `cached_graph_asset_response`) serve pre-gzipped bytes
with weak ETags and 304 handling. Explicit routes now serve `/`, `/index.html`,
`/css/*`, `/js/*`, `/vendor/*`, `/data/*` instead of relying on the `StaticFiles`
mount — which is what makes custom ETag/cache-control possible.

Cache-control is **correctly scoped** (verified live):

| Path | Cache-Control | Correct? |
|---|---|---|
| `/js/main.js`, `/css/app.css`, `/data/*` | `max-age=60, must-revalidate` | ✅ revalidates |
| `/vendor/maplibre-gl/5.6.2/maplibre-gl.js` | `max-age=31536000, immutable` | ✅ safe — version is in the path |

**C. New endpoints (all additive).** `/api/universe/bulk` (strips `entity_model`
from nodes, pre-gzipped, mtime-cached), `/api/bootstrap/signals` (collapses 5
small JSON fetches into 1), `/api/data-quality/dashboard`.

**D. Read-path caching.** `store.py`, `political.py`, `data_sources.py` all gain
mtime-keyed `lru_cache` wrappers — the same idiom already used in the codebase.
`duckdb` import becomes function-local (startup win). `node_count()` uses a SQL
`COUNT` instead of materialising 14,627 rows.

**E. DCF workbook cache.** `facts_path_for_node()` resolves the facts path
*without* parsing multi-MB JSON, so `fresh_cached_workbook_path()` can return an
existing `.xlsx` when it is newer than all dependencies (facts, code, nodes,
aliases, logos). openpyxl import is deferred behind `load_openpyxl()`.

**F. Frontend deferral.** `markGridDirty()` replaces eager `buildGrid()`;
`loadMapGraphIndex()` and `queueHydrateDataQuality()` defer non-critical loads;
`warnMapOnce()` dedupes map warnings.

---

## 4. Route and API changes

**17 added, 0 modified, 0 removed → no backward-compatibility break.** The
`StaticFiles` mount at `/` (line 3033) remains as a fallback; explicit routes are
registered earlier and therefore win. No route takes a path parameter that maps
to the filesystem, so **no path-traversal surface is introduced**.

| Added | Kind |
|---|---|
| `/api/universe/bulk`, `/api/bootstrap/signals`, `/api/data-quality/dashboard` | API |
| `/`, `/index.html`, `/css/app.css`, `/js/{main,config,state}.js` | static |
| `/vendor/maplibre-gl/5.6.2/{js,css}`, `/Logo_Dark_BG_96.png` | static |
| `/data/{universe_core.json,companies,securities,relationships}.geojson`, `/data/graph-index.json` | static data |

Responses are JSON-serialisable (`compact_json_bytes` on plain dicts) or byte
responses with explicit media types. Errors use FastAPI's standard shape —
verified: `GET /api/entity/DOES_NOT_EXIST_XYZ` → `404 {"detail":"entity not found"}`.

**Authentication:** none — unchanged. The app has no auth anywhere; this work
neither adds nor weakens it. Still a Phase-1 gate before any public deployment.

**Eventual modularisation:** `map_api.py` is now ~3,000+ lines / 67 routes. The
caching helpers (§B) and the static-route block are the two cleanest extraction
candidates (`api/caching.py`, `api/routers/static.py`). **Not done here** — out
of scope for an audit.

---

## 5. Data and schema changes

**None.** No Parquet schema change, no new stored fields, no migration. The only
payload-shape change is `/api/universe/bulk` omitting `entity_model` from nodes
— a deliberate payload reduction consumed by the frontend in the same changeset.

On the `universe.json` question: the remaining readers are **build-time writers
and refresh scripts** (`expand_us.py` writes it; `build_store.py`,
`build_map_geojson.py`, `refresh_*.py` read it during the pipeline). The
**production runtime readers** (`map_api`, `comps`, `reverse_dcf`, `dcf_export`,
`build_events`) go through `store.py` / Parquet. By the stated criterion, the
Parquet migration is **complete for runtime**; `universe.json` persists as a
build artifact only.

---

## 6. Test results (exact commands)

| Command | Result |
|---|---|
| `python3 -m compileall -q map_api.py dcf_export.py store.py political.py data_sources.py` | OK |
| `node --check graph/js/{config,main,state,util}.js` | OK (4/4) |
| `python3 -m pytest -q` | **39 passed, 1 skipped** ✅ baseline |
| `npx playwright test` | **7 passed** ✅ baseline |
| `store.load_nodes()` | **14,627** ✅ baseline |
| `companies.geojson` features | **11,338** ✅ baseline |

API smoke (all `200`, warm): bootstrap/signals 8.9 ms · universe/bulk 35 ms ·
data-quality/dashboard 5.1 ms · entity/NVDA 1.3 ms · reverse-dcf 1.9 ms ·
comps 95 ms · events 1.0 ms · LMT/political 1.2 ms · map/entities.geojson 33 ms ·
index.html 1.0 ms · js/main.js 1.0 ms.

**Every baseline number is unchanged. No regression detected.**

### Browser verification — environmental limitation (important)

In the preview browser the globe renders blank and `mapStudioState().styleLoaded`
stays `false`. **This is not a regression.** Proof: a bare MapLibre map built
with a dependency-free inline style (`{version:8, sources:{}, layers:[]}`) also
never fires `style.load` in this browser, while Web Workers, WebGL (ANGLE Metal,
M3) and external `fetch()` (200 for both the OpenFreeMap style and an AWS terrain
tile) all work. MapLibre simply does not complete initialisation in this
environment.

Verified working here: app boot, 14,627 entities, network view (958 SVG nodes),
Map Studio panel, basemap switching state (all three), terrain/overlay/
exaggeration preservation, drawer and rail actions, console free of errors
(warnings only).

> **Not verifiable locally:** actual map tile rendering. The owner must confirm
> Standard/Dark/Satellite render in a real browser before deploying.

---

## 7. Performance and network concerns

**Wins:** two CDN dependencies removed; 343 KB favicon saved; MapLibre no longer
blocks parse; 5 bootstrap fetches → 1; `entity_model` stripped from the bulk
payload; DCF workbooks and all hot reads cached; `node_count()` no longer
materialises 14,627 rows.

**Follow-up 1 — startup cache warming can hit the network (not a blocker).**
`oasis_lifespan` → `warm_startup_caches()`, plus a daemon thread
(`start_background_warm_caches`), calls `warm_research_caches()`, which invokes
`build_dcf_workbook` and reverse-DCF/comps warming for `GM` and `USDA`. Those
paths reach `load_facts` → `cache_one` → **SEC download**, all silenced by
`with suppress(Exception)`.

Measured: starting a fresh server changed nothing (**102 files / 288 MB before
and after**) because GM/USDA facts are already cached. On a **cold machine** it
would fetch them. Bounded to 2 entities, but it is unbounded per entity (comps
can pull up to 18 files), unrated, unlogged, and would run per replica.

*Assessment:* this is the **right direction** — Phase 0 explicitly asks for
"request-independent data warming" — with the wrong controls. Phase 0 should
keep the seam and add rate limiting, a cache cap, backoff, and logging, and move
it out of the request-serving process.

**Follow-up 2 — `ujson` used but undeclared.** `dcf_export.py` does
`try: import ujson as fast_json / except ImportError: fast_json = json`. It is
installed here (5.11.0) but absent from `requirements.txt`, so production
silently runs the slower stdlib path. Safe, but declare it as an optional extra.

**Memory note:** `_ui_bulk_json_cached` and `_static_asset_bytes_cached` hold raw
+ gzipped bytes (bulk ≈ 6.1 MB raw + ~1 MB gz; companies.geojson 6.6 MB).
Bounded by `lru_cache(maxsize=4)`. Acceptable for a single node; worth a ceiling
when multiple replicas share a small container.

**Pre-existing, not introduced (do not attribute to this diff):**
`/api/reliefs/dem/status` returns **1.5 MB** (the 1,341-source terrain registry
under `coverage`) — identical in `HEAD`, loaded lazily.

---

## 8. Phase 0 overlap analysis

| Phase 0 task | Touched? | Fixed? | Merge risk |
|---|---|---|---|
| 1. Sync SEC downloads in request path (`dcf_export`) | **Yes** | No | **Low, and helpful** — `facts_path_for_node()` is now the single choke point where `allow_network=False` belongs |
| 2. Clearbit logo in export (`dcf_export.py:193`) | Yes (import moved) | No | Low — still `urlretrieve` with a guessed domain |
| 3. Basemap preference overwrite (`main.js:1232`) | **No** | No | **None** — line untouched |
| 4. Eager `/api/universe/bulk` | Yes (endpoint added) | No | Low — `loadBulk()` still called at startup; the endpoint is now the right place to paginate |
| 5. POSIX `/data/raw` default | No | No | None |

**Conclusion: committing first strictly reduces Phase 0 risk.** Two of the five
tasks land in files this work restructures; doing Phase 0 against a clean tree
avoids resolving a 1,742-line diff by hand.

**One interaction to note:** Phase 0 will make request paths cache-only. The
startup warming (§7) becomes the *only* place facts are fetched — so Phase 0
should harden it in the same pass rather than leaving it unbounded.

---

## 9. Recommended commit structure

Dependency-ordered so no intermediate commit leaves the app broken. `map_api.py`
must land **before** the frontend that consumes its new endpoints; the old
frontend keeps working through the `StaticFiles` fallback, so C2 is
backward-compatible on its own.

| # | Title | Files | Revert-safe alone? |
|---|---|---|---|
| C1 | `chore: ignore local audit backups` | `.gitignore` | Yes |
| C2 | `perf(api): ETag/gzip caching layer, static routes, bulk + bootstrap endpoints` | `map_api.py`, `store.py`, `data_sources.py`, `political.py`, `test_map_intelligence_api.py` | Yes (additive) |
| C3 | `perf(web): self-host MapLibre, lazy-load map runtime, defer non-critical work` | `graph/index.html`, `graph/js/main.js`, `graph/js/config.js`, `graph/vendor/`, `graph/Logo_Dark_BG_96.png` | Only if C2 present |
| C4 | `perf(export): cache DCF workbooks, defer openpyxl import` | `dcf_export.py` | Yes |

Contains no secrets, caches, datasets, build outputs, or browser artifacts
(`node_modules/`, `test-results/`, `.local-backups/`, `data/`, `graph/data/` all
ignored — verified).

---

## 10. Remaining risks

| Risk | Severity | Action |
|---|---|---|
| Map tile rendering unverified locally (preview browser can't run MapLibre) | **Medium** | Owner confirms all 3 basemaps in a real browser |
| Startup warming does SEC I/O on a cold machine | Medium | Harden in Phase 0 §1 (same seam) |
| `ujson` undeclared → silent slow path in prod | Low | Add optional extra to `requirements.txt` |
| `build_dcf_workbook(method=...)` ignores `method`; new cache makes a wrong `?method=dividend` result sticky | Low | **Pre-existing** (identical in `HEAD`); fix separately |
| `map_api.py` ~3,000 lines / 67 routes | Low (debt) | Extract caching + static routers post-Phase 0 |
| `suppress(Exception)` hides warming failures | Low | Add logging when observability lands |

---

## Verdict

# `SAFE TO COMMIT`

No regressions. Baselines hold (39/1 skipped, 7 Playwright, 14,627 entities,
11,338 features). No API break, no schema change, no secrets, no required new
dependency. Commit in the C1–C4 order above, then Phase 0 may begin against a
clean tree.

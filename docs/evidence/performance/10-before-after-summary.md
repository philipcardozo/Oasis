# Before/After Summary

**Optimization:** add explicit cached static route for `/js/util.js`  
**Base commit:** `9fb135fc54d7f3cf3f44ab3a51fe86d4f0bcb01e`  
**Capture method:** Playwright HAR plus Proxyman-routed Chromium capture through
`http://127.0.0.1:9090`.

## Why This Patch

Browser HAR capture showed `/js/util.js` on the first-paint path without the
cache/gzip headers used by the other first-party JavaScript assets. The route
fell through to the generic static mount while `/js/main.js`, `/js/config.js`,
and `/js/state.js` had explicit cached routes.

This was a header-only static-serving optimization. It does not change module
contents, execution order, UI behavior, API semantics, navigation, actions, or
outputs.

## Result

| Asset | Before | After |
|---|---|---|
| `/js/util.js` cache-control | none captured | `public, max-age=60, must-revalidate` |
| `/js/util.js` ETag | none captured | `W/"oasis-c893a2e8e8286b3f"` |
| `/js/util.js` content encoding | none captured | `gzip` |
| `/js/util.js` response size | `970` bytes captured | `515` bytes captured |
| 304 support | fallback static behavior only | covered by `test_map_intelligence_api.py` |

The DCF workbook route also now avoids redundant gzip on an already-compressed
`.xlsx`:

| Asset | Before | After |
|---|---|---|
| `/api/entity/BLK/dcf.xlsx?method=cash_flow` content encoding | `gzip` | `identity` |
| Content length | omitted by gzipped response | `2,695,929` |
| HAR compression | `2,997` bytes | `0` |
| Workbook bytes received by browser | `2,695,929` | `2,695,929` |

The logo image route now avoids redundant gzip on an already-compressed PNG:

| Asset | Before | After |
|---|---|---|
| `/Logo_Dark_BG_96.png` content encoding | `gzip` | `identity` |
| Content length | omitted by gzipped response | `1,612` |
| HAR compression | `7` bytes | `0` |
| Cache-control | `public, max-age=31536000, immutable` | `public, max-age=31536000, immutable` |

The search-intent flow also no longer pulls MapLibre runtime while loading the
full universe:

| Flow | Before | After |
|---|---:|---:|
| Search requests | 12 | 10 |
| Search transfer | 1,563.3 KB | 1,311.0 KB |
| Search MapLibre transfer | ~258.0 KB | 0 KB |

## Browser Flow Guardrails

After the patch:

| Flow | Requests | Transfer | Guardrail |
|---|---:|---:|---|
| Cold first paint | 9 | 352.9 KB | no `/api/universe/bulk`, no `unpkg.com`, no console errors |
| Warm reload | 18 | 0 KB | no `/api/universe/bulk`, no `unpkg.com`, no console errors |
| Search intent | 10 | 1,311.0 KB | `/api/universe/bulk` only after search intent; no MapLibre runtime |
| Map interactions | 116 | 1,353.9 KB | no `/api/universe/bulk`, no `unpkg.com`; headless warning classified separately |
| DCF workbook fetch | 10 | 2,985.9 KB | workbook returns `200`, `ETag`, cache-control, identity encoding |
| Entity drawer | 17 | 1,314.5 KB | `/api/universe/bulk` only after search intent; drawer-specific APIs are small |
| Data quality panel | 10 | 353.6 KB | no `/api/universe/bulk`, no `unpkg.com`, no console errors |
| Report preview | 10 | 354.8 KB | no `/api/universe/bulk`, no `unpkg.com`, no console errors |

## Auth And Map-Slot Guardrails

The local temp-DB Phase 1 baseline passed the acceptance targets:

| Flow | p95 ms | Target |
|---|---:|---:|
| Session validation | 8.283 | `< 50` |
| Map-slot list | 21.896 | `< 100` |
| Map-slot read | 6.181 | `< 100` |
| Map-slot write | 12.850 | `< 200` |
| Map-slot rename | 12.908 | `< 200` |

CSRF rejection remained `403`, and new accounts still received exactly three
map slots.

The real HTTP temp-DB capture passed the app-side targets with and without
Proxyman in the request path:

| Flow | Direct HTTP p95 ms | Proxyman-routed p95 ms | Target | Read |
|---|---:|---:|---:|---|
| Session validation | 11.648 | 12.944 | `< 50` | pass |
| Map-slot list | 41.759 | 29.874 | `< 100` | pass |
| Map-slot read | 9.065 | 11.216 | `< 100` | pass |
| Map-slot write | 35.936 | 43.323 | `< 200` | pass |
| Map-slot rename | 8.257 | 9.086 | `< 200` | pass |

The Proxyman-routed HTTP capture also proves cookie, CSRF, middleware, import,
reset, activate, duplicate, password reset/change, session revoke, logout-all,
account delete, health, readiness, version, and logout-rejection behavior over
real HTTP against a temporary SQLite database.

The route-family probe also covers sandboxed file-backed mutation routes without
changing the real project JSON files, and covers `/api/reliefs/dem/tilejson`
with temporary tilejson path redirection. The current coverage audit shows
68/68 `map_api` routes and 92/92 `server_app` routes covered by local
performance evidence.

The headless MapLibre diagnostic reproduced the `shaderPreludeCode` warning
across three Chromium GL variants while `styleLoaded` and basemap preservation
remained true and no unclassified errors remained.

## Evidence

```text
docs/evidence/performance/03-local-first-paint.har
docs/evidence/performance/04-local-reload.har
docs/evidence/performance/05-local-search-intent.har
docs/evidence/performance/06-local-map-interactions.har
docs/evidence/performance/07-local-dcf-download.har
docs/evidence/performance/12-local-entity-drawer.har
docs/evidence/performance/13-local-data-quality-panel.har
docs/evidence/performance/14-local-report-preview.har
docs/evidence/performance/11-browser-har-summary.json
docs/evidence/performance/07-local-api-latency.json
docs/evidence/performance/06-local-auth-and-map-slots.json
docs/evidence/performance/06-local-auth-and-map-slots-http.json
docs/evidence/performance/06-local-auth-and-map-slots-http-direct.json
docs/evidence/performance/16-performance-coverage-audit.md
docs/evidence/performance/17-route-family-performance-probes.json
docs/evidence/performance/18-headless-maplibre-diagnostic.json
```

## Verification

```bash
python3 scripts/performance_baseline.py --samples 7
python3 scripts/auth_mapslot_performance_baseline.py --samples 25
python3 scripts/auth_mapslot_http_capture.py --samples 20 --proxy-server=http://127.0.0.1:9090
python3 scripts/auth_mapslot_http_capture.py --samples 20 --output-file=06-local-auth-and-map-slots-http-direct.json
python3 scripts/route_family_performance_probe.py --samples 3
node scripts/maplibre_headless_diagnostic.js --proxy-server=http://127.0.0.1:9090
python3 scripts/performance_evidence_audit.py
node scripts/browser_performance_capture.js
node scripts/browser_performance_capture.js --proxy-server=http://127.0.0.1:9090
python3 -m pytest -q test_map_intelligence_api.py test_phase0_launch_safety.py
python3 -m pytest -q
npx playwright test
```

Focused result: `17 passed, 1 warning`.

Full-suite result:

```text
124 passed, 1 skipped, 1 warning
15 Playwright tests passed
```

The larger performance goal remains active because deployed or compose staging
Proxyman capture and further evidence-backed optimization passes are still
required.

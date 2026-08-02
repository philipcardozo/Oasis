# Performance Evidence Coverage Audit

**Generated:** 2026-07-30T05:22:56.702531+00:00
**Commit:** `788dc9b22bb932a6ff035d567cb67622650d4b40`

## Artifact Presence

| Artifact | Status |
|---|---|
| `00-preflight.json` | present |
| `01-route-inventory.json` | present |
| `02-golden-api-snapshots.json` | present |
| `03-local-first-paint.har` | present |
| `04-local-reload.har` | present |
| `05-local-search-intent.har` | present |
| `06-local-auth-and-map-slots.json` | present |
| `06-local-auth-and-map-slots-http.json` | present |
| `06-local-auth-and-map-slots-http-direct.json` | present |
| `06-local-map-interactions.har` | present |
| `07-local-api-latency.json` | present |
| `07-local-dcf-download.har` | present |
| `08-proxyman-findings.md` | present |
| `09-optimization-plan.md` | present |
| `10-before-after-summary.md` | present |
| `11-browser-har-summary.json` | present |
| `12-local-entity-drawer.har` | present |
| `13-local-data-quality-panel.har` | present |
| `14-local-report-preview.har` | present |
| `15-staging-capture-status.json` | present |
| `15-compose-browser-har-summary.json` | present |
| `17-route-family-performance-probes.json` | present |
| `18-headless-maplibre-diagnostic.json` | present |
| `19-compose-auth-map-slots.json` | present |
| `20-compose-route-family-probe.json` | present |
| `21-compose-route-family-proxyman-probe.json` | present |
| `22-compose-backup-restore-drill.json` | present |
| `23-compose-failure-exercises.json` | present |
| `24-compose-map-gate.json` | present |

## Browser Flows

Source summary: `2026-07-30T05:20:54.739Z` via `http://localhost:9090`

| Flow | Requests | Transfer KB | Bulk | unpkg | Console errors |
|---|---:|---:|---|---|---:|
| `15-compose-03-local-first-paint` | 10 | 353 | False | False | 0 |
| `15-compose-04-local-reload` | 20 | 0.6 | False | False | 0 |
| `15-compose-05-local-search-intent` | 11 | 1311.2 | True | False | 0 |
| `15-compose-06-local-map-interactions` | 89 | 1354.1 | False | False | 0 |
| `15-compose-07-local-dcf-download` | 11 | 369.8 | False | False | 0 |
| `15-compose-12-local-entity-drawer` | 18 | 1314.7 | True | False | 0 |
| `15-compose-13-local-data-quality-panel` | 11 | 353.7 | False | False | 0 |
| `15-compose-14-local-report-preview` | 11 | 355 | False | False | 0 |

## Headless MapLibre Diagnostic

- captured: `2026-07-23T07:49:47.595Z`
- variants: `3`
- all style loaded: `True`
- all basemap state preserved: `True`
- unclassified errors: `0`
- conclusion: headless MapLibre/WebGL warnings classified; app state and basemap behavior preserved

## Headed Compose Map Gate

- captured: `2026-07-30T05:21:27.988Z`
- verdict: `pass`
- browser: `chrome` `150.0.7871.188`
- headed: `True`
- proxy: `http://localhost:9090`
- vendored MapLibre requested: `True`
- unpkg requested: `False`
- unexpected failed requests: `0`
- unexpected console errors: `0`
- normal screenshot: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/24-compose-map-gate-normal.png`
- provider-failure screenshot: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/24-compose-map-gate-provider-failure.png`

## Auth And Map Slots

### testclient

- file: `06-local-auth-and-map-slots.json`
- proxy: `None`
- default map slots: `3`
- CSRF rejection status: `403`

| Measurement | p50 ms | p95 ms | Target | Met |
|---|---:|---:|---:|---|
| session validation GET /api/auth/me | 4.727 | 8.283 | 50 | True |
| session list GET /api/auth/sessions | 9.192 | 31.426 |  | None |
| map-slot list GET /api/map-slots | 8.645 | 21.896 | 100 | True |
| map-slot read GET /api/map-slots/{id} | 4.543 | 6.181 | 100 | True |
| map-slot write PUT /api/map-slots/{id} | 6.525 | 12.85 | 200 | True |
| map-slot rename POST /api/map-slots/{id}/rename | 8.832 | 12.908 | 200 | True |
| map-slot export GET /api/map-slots/{id}/export | 6.972 | 9.678 |  | None |

### http_proxyman

- file: `06-local-auth-and-map-slots-http.json`
- proxy: `http://127.0.0.1:9090`
- default map slots: `3`
- CSRF rejection status: `403`
- extra covered one-shot operations: `10`

| Measurement | p50 ms | p95 ms | Target | Met |
|---|---:|---:|---:|---|
| session validation GET /api/auth/me | 6.111 | 12.944 | 50 | True |
| session list GET /api/auth/sessions | 7.583 | 11.048 |  | None |
| map-slot list GET /api/map-slots | 10.182 | 29.874 | 100 | True |
| map-slot read GET /api/map-slots/{id} | 6.459 | 11.216 | 100 | True |
| map-slot write PUT /api/map-slots/{id} | 15.215 | 43.323 | 200 | True |
| map-slot rename POST /api/map-slots/{id}/rename | 6.085 | 9.086 | 200 | True |
| map-slot export GET /api/map-slots/{id}/export | 5.024 | 6.416 |  | None |

### http_direct

- file: `06-local-auth-and-map-slots-http-direct.json`
- proxy: `None`
- default map slots: `3`
- CSRF rejection status: `403`
- extra covered one-shot operations: `10`

| Measurement | p50 ms | p95 ms | Target | Met |
|---|---:|---:|---:|---|
| session validation GET /api/auth/me | 5.882 | 11.648 | 50 | True |
| session list GET /api/auth/sessions | 7.556 | 11.244 |  | None |
| map-slot list GET /api/map-slots | 10.351 | 41.759 | 100 | True |
| map-slot read GET /api/map-slots/{id} | 6.322 | 9.065 | 100 | True |
| map-slot write PUT /api/map-slots/{id} | 12.877 | 35.936 | 200 | True |
| map-slot rename POST /api/map-slots/{id}/rename | 6.281 | 8.257 | 200 | True |
| map-slot export GET /api/map-slots/{id}/export | 4.658 | 6.014 |  | None |

## Route Coverage

Route-family probe: 37 measured routes with 0 skipped routes and 2 sandboxed fixture groups.

- `map_api`: 68/68 routes covered by performance evidence (100.0%).
- `server_app`: 92/92 routes covered by performance evidence (100.0%).
- Route probe measured families: api: 8, assets/due diligence: 12, data quality: 2, entity drawer/model: 3, evidence/overrides: 3, map API: 1, relief/terrain: 5, reports: 2, static data: 1.
- Some route-family coverage uses temporary fixture redirection; see `sandboxed_fixtures` in JSON.
- Compose route-family probes: direct `pass`, Proxyman `pass`.

### Uncovered Server-App Routes

| Methods | Path | Family |
|---|---|---|

## Failure Exercises

- captured: `2026-07-23T19:44:15.521731+00:00`
- verdict: `pass`
- `/readyz` while PostgreSQL stopped: `503`
- worker restart job status: `done`
- `/readyz` after full compose restart: `None`
- post-restart login status: `200`
- post-restart map slots: `3`

## Gaps And Decision

- no public deployed staging URL is configured in .env

**Decision:** local compose performance optimization evidence is current. The remaining acceptance gap is the absent public deployed staging URL; local compose, reverse-proxy, Proxyman, backup/restore, headed-map, route-family, and failure-exercise evidence are present.

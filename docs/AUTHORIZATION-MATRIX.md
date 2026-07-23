# Authorization Matrix

Generated from the live composed app (`server.app:create_app`) on 2026-07-23.
Authentication is never treated as authorization: writes require a session **and**
CSRF; owner-only resources additionally check ownership in the handler.

## Route-class summary (100 route-methods)

| Count | Class | Enforcement |
|------:|-------|-------------|
| 69 | public-read | none (GET data/assets) |
| 9 | owner-only | session + CSRF + ownership check in handler |
| 7 | authenticated | session cookie (e.g. `/api/auth/me`, sessions list) |
| 6 | authenticated + CSRF (write guard) | global middleware on existing map_api writes |
| 5 | public-write (auth) | rate-limited; register/login/verify/reset |
| 3 | public | `/healthz`, `/readyz`, `/version` (minimal disclosure) |
| 1 | public-read (assets) | static catch-all mount, GET only |

## Write routes — all protected (evidence)

The global write-protection middleware requires a valid session + CSRF for every
state-changing method outside `/api/auth/*`. This covers the **pre-existing**
map_api write routes without editing each handler:

| Method | Path | Class |
|--------|------|-------|
| POST | `/api/overrides` | authenticated + CSRF |
| DELETE | `/api/overrides/{id}` | authenticated + CSRF |
| POST | `/api/location/override` | authenticated + CSRF |
| POST | `/api/watchlist/toggle` | authenticated + CSRF |
| POST | `/api/assets/{id}/valuation-assumptions` | authenticated + CSRF |
| POST | `/api/reports/{type}/{id}/generate` | authenticated + CSRF |
| PUT/POST | `/api/map-slots/{id}...` (9) | owner-only (session + CSRF + ownership) |
| POST | `/api/auth/{logout,logout-all,password-change,...}` | authenticated + CSRF (dependency) |
| POST | `/api/auth/{register,login,verify-email,password-reset/*}` | public, rate-limited |

## Public routes (deliberate)

- `/healthz`, `/readyz` (minimal), `/version`
- Static assets and the deliberately public read subset of map/entity data
  (`/api/map/*`, `/api/entity/{id}` reads, `/data/*.geojson`, etc.)

Not exposed publicly: refresh controls (worker-only, no HTTP route), internal
paths, stack traces (generic error handler), user preferences, any write endpoint.

## Classification levels

`public` · `authenticated` · `owner-only` · `organization-member` ·
`organization-admin` · `system-worker` (no HTTP surface — worker process only) ·
`administrative` (none exposed in Phase 1).

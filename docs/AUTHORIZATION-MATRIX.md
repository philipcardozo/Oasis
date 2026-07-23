# Authorization Matrix

Generated from the live composed app (`server.app:create_app`) on 2026-07-23.
Authentication is never treated as authorization: writes require a session **and**
CSRF; owner-only resources additionally check ownership in the handler.

Evidence file: `docs/evidence/phase-1-5/route-authorization-inventory.json`.

## Route-class summary

Development mode assembles 96 app route entries: 95 method routes plus the
catch-all static mount. Secure modes assemble 92 app route entries: 91 method
routes plus the catch-all static mount. There are no duplicate method/path
pairs. Documentation routes are available only outside staging/production.

| Count | Class | Enforcement |
|------:|-------|-------------|
| 61 | public-read | none (GET data/assets) |
| 6 | owner-only + CSRF | session + CSRF + ownership check in handler |
| 6 | authenticated + CSRF (write guard) | global middleware on existing map_api writes |
| 5 | public-write (auth) | rate-limited; register/login/verify/reset |
| 5 | authenticated + CSRF | session + CSRF dependency in auth router |
| 4 | public-dev-docs | OpenAPI/Swagger/ReDoc; disabled in staging/production |
| 3 | owner-only | session + ownership check in handler |
| 3 | public-health-version | `/healthz`, `/readyz`, `/version` (minimal disclosure) |
| 2 | authenticated | session cookie (`/api/auth/me`, sessions list) |
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
| PUT/POST | `/api/map-slots/{id}...` (6 writes) | owner-only (session + CSRF + ownership) |
| POST | `/api/auth/{logout,logout-all,password-change,...}` | authenticated + CSRF (dependency) |
| POST | `/api/auth/{register,login,verify-email,password-reset/*}` | public, rate-limited |

## Public routes (deliberate)

- `/healthz`, `/readyz` (minimal), `/version`
- Static assets and the deliberately public read subset of map/entity data
  (`/api/map/*`, `/api/entity/{id}` reads, `/data/*.geojson`, etc.)
- Development-only docs: `/openapi.json`, `/docs`, `/docs/oauth2-redirect`,
  `/redoc`. These are disabled when `OASIS_MODE` is `staging` or `production`.

Not exposed publicly: refresh controls (worker-only, no HTTP route), internal
paths, stack traces (generic error handler), user preferences, any write endpoint.

## Classification levels

`public` · `authenticated` · `owner-only` · `organization-member` ·
`organization-admin` · `system-worker` (no HTTP surface — worker process only) ·
`administrative` (none exposed in Phase 1).

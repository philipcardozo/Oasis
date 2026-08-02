# OASIS Performance Evidence

Date: 2026-07-30

This index summarizes the current latency/performance evidence gathered for OASIS.
Local development evidence is still kept under `docs/evidence/performance/`; the
compose staging target is `https://localhost:8443`.

## GCP Public Staging

GCP public-staging performance evidence is not captured yet. The next public
run must target the generated Cloud Run `run.app` URL from
`docs/GCP-STAGING-DEPLOYMENT.md`, not `localhost`, and must refresh public
Playwright, route-family, browser/HAR, Proxyman, auth/map-slot, backup/restore,
storage, security-header, and failure-exercise evidence before the private-beta
verdict can change.

## Compose Staging

- Docker: `Docker version 29.6.2, build dfc4efb`
- Docker Compose: `Docker Compose version v5.3.1`
- Branch: `phase1.75/public-staging`
- Commit: `788dc9b22bb932a6ff035d567cb67622650d4b40`
- Start command: `docker compose --env-file .env.staging.local up --build -d`
- Services: `db`, `migrate`, `api`, `worker`, `proxy`
- Published port: Caddy proxy on `https://localhost:8443`
- Migration version: `29995ef61d8e`

## Reverse Proxy

`GET /healthz`, `GET /readyz`, and `GET /version` returned 200 through Caddy
TLS. The local certificate was issued by `Caddy Local Authority - ECC
Intermediate`. Current service state was: `db` healthy, `api` healthy,
`migrate` exited 0, `worker` up, and `proxy` publishing `8443`.

## Proxyman

Proxyman `6.12.0` build `61200` was recording on `http://localhost:9090`.
System proxying and SSL proxying were enabled, and `localhost:8443` was present
in the SSL Proxying include list. A proxied `GET /healthz` returned 200, and the
browser, route-family, and map-gate captures below were refreshed through
`http://localhost:9090` after that rule was enabled.

## Browser Capture

Evidence:

- `docs/evidence/performance/15-compose-browser-har-summary.json`
- `docs/evidence/performance/15-compose-03-local-first-paint.har`
- `docs/evidence/performance/15-compose-04-local-reload.har`
- `docs/evidence/performance/15-compose-05-local-search-intent.har`
- `docs/evidence/performance/15-compose-06-local-map-interactions.har`
- `docs/evidence/performance/15-compose-07-local-dcf-download.har`
- `docs/evidence/performance/24-compose-map-gate.json`
- `docs/evidence/performance/24-compose-map-gate-normal.png`
- `docs/evidence/performance/24-compose-map-gate-provider-failure.png`

Key results from the headed Chrome `2026-07-30T05:20:54.739Z` capture:

- Cold first paint: 10 requests, 0 failed requests, 353 KB transferred, no
  `/api/universe/bulk`, no `unpkg.com`, no sensitive URLs, no external hosts.
- Warm reload: 20 requests and 0.6 KB transferred. The startup JSON resources
  revalidated with 300-byte header-only transfers and 0 encoded body bytes.
- Search intent and entity drawer intentionally loaded `/api/universe/bulk`.
- DCF workbook export returned 200 with
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- No browser flow requested `unpkg.com` or sensitive query URLs.
- The only external hosts were expected map providers during map interaction:
  `basemaps.cartocdn.com`, `fonts.openmaptiles.org`, `s3.amazonaws.com`,
  `services.arcgisonline.com`, `tiles.basemaps.cartocdn.com`, and
  `tiles.openfreemap.org`.

The compose map gate ran in headed Chrome `150.0.7871.188` through Proxyman and
passed: Standard, Dark, and Satellite basemaps loaded or fell back safely,
entity selection worked, reload preserved the preferred basemap, provider
failure did not overwrite the preference, vendored MapLibre 5.6.2 loaded from
OASIS, `unpkg.com` was not requested, and no unexpected console or request
failures remained. The broader headed HAR map-interaction flow records 8
expected `net::ERR_ABORTED` provider fetches while terrain/vector tiles are
cancelled during active basemap switching; the map gate reports 28 expected
provider failures and zero unexpected failed requests or console errors.

## Auth And Map Slots

Evidence:

- `docs/evidence/performance/19-compose-auth-map-slots.json`

The compose proxy path passed registration, SMTP email verification, login,
session validation, map-slot list/read/write, stale-version conflict, cross-user
slot-read denial, password reset, and API-restart persistence. Exactly three map
slots persisted after restart. This sanitized evidence was captured through
Proxyman before the `localhost:8443` SSL include was added; after adding the SSL
include, the proxied healthz, browser, route-family, and map-gate captures were
refreshed.

## Route, Backup, And Failure Evidence

Evidence:

- `docs/evidence/performance/20-compose-route-family-probe.json`
- `docs/evidence/performance/21-compose-route-family-proxyman-probe.json`
- `docs/evidence/performance/22-compose-backup-restore-drill.json`
- `docs/evidence/performance/23-compose-failure-exercises.json`
- `docs/evidence/performance/16-performance-coverage-audit.json`

Direct and Proxyman-routed compose route-family probes passed with 46 measured
representative requests and 0 failures in each mode. The backup/restore drill
passed against PostgreSQL, including checksum and restore into a separate
database. Controlled failure exercises passed: `/readyz` returned 503 while
PostgreSQL was stopped, `/healthz` stayed live, a queued noop job completed
after worker restart, full-stack restart recovered, login succeeded, and three
map slots persisted.

## Verification

- `python3 -m pytest -q`: 274 passed, 1 skipped, 1 warning.
- `npx playwright test --config=/tmp/oasis-playwright-compose.config.js`: 15
  passed against `https://localhost:8443`.
- `npx playwright test`: 15 passed against the default local target.

## Remaining Gaps

- Public deployed staging URL is still not configured.
- The broader private-beta gate remains `NOT APPROVED` until the public staging
  deployment evidence exists.

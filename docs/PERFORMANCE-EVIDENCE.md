# OASIS Performance Evidence

Date: 2026-07-23

This index summarizes the current latency/performance evidence gathered for OASIS.
Local development evidence is still kept under `docs/evidence/performance/`; the
compose staging target is `https://localhost:8443`.

## Compose Staging

- Docker: `Docker version 29.6.2, build dfc4efb`
- Docker Compose: `Docker Compose version v5.3.1`
- Branch: `main`
- Commit: `9fb135fc54d7f3cf3f44ab3a51fe86d4f0bcb01e`
- Start command: `docker compose --env-file .env.staging.local up --build -d`
- Services: `db`, `migrate`, `api`, `worker`, `proxy`
- Published port: Caddy proxy on `https://localhost:8443`
- Migration version: `29995ef61d8e`

## Reverse Proxy

`GET /healthz`, `GET /readyz`, and `GET /version` returned 200 through Caddy
TLS. The local certificate was issued by `Caddy Local Authority - ECC
Intermediate`.

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

Key result: compose first paint made 9 requests, had 0 failed requests, did not
load `/api/universe/bulk`, and did not request `unpkg.com`.

The headed compose map gate ran in Chrome `150.0.7871.129` through Proxyman and
passed: Standard, Dark, and Satellite basemaps loaded or fell back safely,
entity selection worked, reload preserved the preferred basemap, provider
failure did not overwrite the preference, vendored MapLibre 5.6.2 loaded from
OASIS, `unpkg.com` was not requested, and no unexpected console or request
failures remained.

## Auth And Map Slots

Evidence:

- `docs/evidence/performance/19-compose-auth-map-slots.json`

The compose proxy path passed registration, SMTP email verification, login,
session validation, map-slot list/read/write, stale-version conflict, cross-user
slot-read denial, password reset, and API-restart persistence. Exactly three map
slots persisted after restart.

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

## Remaining Gaps

- Public deployed staging URL is still not configured.
- Proxyman MCP recorded HTTPS CONNECT flow visibility; decrypted request detail
  is provided by Playwright HAR because SSL interception state is not controllable
  from the current MCP tool set.

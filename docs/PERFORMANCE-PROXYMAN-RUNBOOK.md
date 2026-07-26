# OASIS Proxyman Performance Runbook

**Purpose:** improve OASIS latency and runtime performance with Proxyman-driven
evidence while preserving every user-visible behavior, navigation, action,
output, API shape, security control, and error semantic.

This runbook is intentionally measurement-first. Do not optimize from instinct.
Capture the current app, prove what is slow, make one low-risk change, and then
compare the same flows again.

## Non-Negotiable Invariants

Any performance patch is invalid if it changes:

| Surface | Must remain unchanged |
|---|---|
| Navigation | URLs, hash/state behavior, panels, drawer actions, search focus, map mode switching |
| API | route availability, status codes, response schemas, error body shape, auth/CSRF behavior |
| Auth | session cookies, CSRF rejection, logout/session revocation, rate limits, secure headers |
| Map Studio | exactly three slots, basemap preference semantics, overlay/terrain persistence, import/export validation |
| Map rendering | Standard/Dark/Satellite behavior, fallback/retry semantics, no CDN MapLibre runtime |
| Data outputs | reports, CSV/XLSX downloads, DCF workbooks, facts-unavailable degraded responses |
| Security | CORS, Host validation, CSP, HSTS, referrer/permissions/no-sniff/frame controls |
| Network isolation | no external dataset downloads from normal API requests; refresh remains explicit |

Architecture may change only behind these contracts.

## Current Local Commands

Use the real project root:

```bash
cd "/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis"
```

Serve the local app:

```bash
python3 map_api.py
open http://127.0.0.1:8788/index.html
```

Run regression suites:

```bash
python3 -m pytest -q
npx playwright test
```

Phase 1 composition root, when testing auth/staging behavior:

```bash
uvicorn server.app:app --host 127.0.0.1 --port 8788
```

## Proxyman Setup

Use Proxyman when available. If the MCP bridge is unavailable, still capture the
traffic through Proxyman manually and save the exported evidence.

1. Launch Proxyman.
2. Enable MCP in `Settings -> MCP` when available.
3. Enable SSL proxying for:
   - `127.0.0.1`
   - `localhost`
   - the staging host, when testing staging
   - approved map tile/glyph hosts
4. Clear the session before each named capture.
5. Export each capture as HAR or Proxyman archive into `docs/evidence/performance/`.
6. Record browser, version, OS, app commit, command used, and whether cache was cold or warm.

If terminal proxy injection is available, launch terminal Codex through Proxyman
or source the generated proxy environment command before running CLI probes.

## Evidence Layout

Store repeatable evidence here:

```text
docs/evidence/performance/
  README.md
  00-preflight.json
  01-route-inventory.json
  02-golden-api-snapshots.json
  03-local-first-paint.har
  04-local-reload.har
  05-local-search-intent.har
  06-local-map-interactions.har
  06-local-auth-and-map-slots.har
  06-local-auth-and-map-slots.json
  06-local-auth-and-map-slots-http.json
  06-local-auth-and-map-slots-http-direct.json
  07-local-api-latency.json
  07-local-dcf-download.har
  08-proxyman-findings.md
  09-optimization-plan.md
  10-before-after-summary.md
  11-browser-har-summary.json
  12-local-entity-drawer.har
  13-local-data-quality-panel.har
  14-local-report-preview.har
  15-staging-capture-status.json
  15-staging-browser-har-summary.json
  16-performance-coverage-audit.json
  16-performance-coverage-audit.md
  17-route-family-performance-probes.json
  18-headless-maplibre-diagnostic.json
  26-public-staging-browser-har-summary.json
```

Large binary exports may be left uncommitted if they are too large. Keep small
JSON summaries and exact filenames/checksums in Git.

When Proxyman is not available through MCP, use the browser fallback:

```bash
node scripts/browser_performance_capture.js
```

To route that capture through Proxyman after manual proxy setup:

```bash
node scripts/browser_performance_capture.js --proxy-server=http://127.0.0.1:<proxyman-port>
```

To capture a deployed or compose staging target without overwriting local HARs:

```bash
node scripts/browser_performance_capture.js \
  --base-url=https://STAGING_HOST \
  --no-start-server=true \
  --proxy-server=http://127.0.0.1:<proxyman-port> \
  --flow-prefix=15-staging \
  --summary-file=15-staging-browser-har-summary.json
```

For a direct, non-Proxyman comparison:

```bash
node scripts/browser_performance_capture.js \
  --base-url=https://STAGING_HOST \
  --no-start-server=true \
  --flow-prefix=15-staging-direct \
  --summary-file=15-staging-browser-har-summary-direct.json
```

## Capture Matrix

| Flow | Required measurements | Guardrails |
|---|---|---|
| Cold first paint | request count, transferred bytes, DOMContentLoaded, largest assets, console errors | no `/api/universe/bulk` before paint |
| Warm reload | 304/cache hits, bytes transferred, redownloaded resources | static assets must keep ETag/cache-control behavior |
| Search intent | time to first result, `/api/universe/bulk` timing, transferred bytes | full universe loads only after search intent |
| Map boot | MapLibre bundle, style, glyph, sprite, tile requests, console/network failures | vendored MapLibre 5.6.2, no `unpkg.com` |
| Basemap switching | Standard/Dark/Satellite timing, retry/fallback requests | preference is never overwritten by provider failure |
| Entity drawer | entity, neighborhood, DCF, comps, events, political, risk timings | facts-unavailable responses stay explicit |
| Data quality panel | dashboard timing, response size, console errors | panel opens without triggering bulk/map runtime |
| Map slots | read/write/rename/reset/export/import latencies | exactly three slots, CSRF and version conflicts preserved |
| Auth | register, verify, login, session validation, logout, reset/change password | cookies, CSRF, rate limits, secure headers unchanged |
| Reports/export | report preview/generate/download, DCF XLSX, CSV/XLSX sizes | output shape and file validity unchanged |
| Worker isolation | normal API requests under blocked outbound network | no SEC/logo/provider downloads from API |
| Security boundary | CORS, Host, HSTS, CSP, no-sniff, frame, safe 500 | raw headers recorded |

## Performance Targets

Use the staging acceptance targets where applicable:

| Measurement | Target |
|---|---|
| Session validation p95 | `< 50 ms` |
| Map-slot read p95 | `< 100 ms` |
| Map-slot write p95 | `< 200 ms` |
| Cold local-only comps | `< 500 ms` |
| First paint | no `/api/universe/bulk` |
| Normal API request path | no external dataset downloads |

Also record local-only context: hardware, browser, Python, Node, app command,
database mode, cache state, and whether Proxyman SSL interception was active.

## Terminal Codex Prompt Pack

Use these prompts literally, in order, unless a newer finding changes the next
best step.

### Prompt 0: Preflight

```text
We are improving OASIS latency/performance with Proxyman evidence and strict
behavior preservation.

Do not edit code yet.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Inspect current state:
- git status --short
- git branch --show-current
- git log --oneline --decorate -12
- README startup commands
- playwright.config.js
- docs/PHASE-0-LAUNCH-SAFETY.md
- docs/IN-FLIGHT-WORK-AUDIT.md
- docs/PHASE-1-5-STAGING-ACCEPTANCE.md
- tests/smoke.spec.js
- tests/phase0.spec.js
- test_map_intelligence_api.py

Produce docs/evidence/performance/00-preflight.json with:
- commit
- branch
- dirty files
- Python version
- Node version
- app startup command
- full regression commands
- current known performance guards
- current behavior invariants

Do not modify product code.
```

### Prompt 1: Route and Behavior Inventory

```text
Create a route and behavior baseline before any optimization.

Do not edit product code.

Generate docs/evidence/performance/01-route-inventory.json containing:
- all FastAPI routes from map_api.app
- all routes from server.app:create_app() when dependencies are available
- method, path, route name, auth classification when discoverable
- static asset routes
- known browser flows that exercise each family of routes

Generate docs/evidence/performance/02-golden-api-snapshots.json containing
small schema-oriented snapshots for representative endpoints:
- /
- /index.html
- /data/universe_core.json
- /api/map/layers
- /api/bootstrap/signals
- /api/map/entities.geojson?bbox=-180,-90,180,90
- /api/map/relationships.geojson?bbox=-180,-90,180,90
- /api/universe/bulk
- /api/entity/GM
- /api/entity/GM/reverse-dcf
- /api/entity/GM/comps?cap=8
- /api/entity/GM/events
- /api/entity/GM/risk
- /api/data-quality/dashboard
- /api/reports/asset/asset%3Ademo-farm-iowa

Snapshots must avoid committing huge payload bodies. Store status, headers of
interest, content length, top-level keys, selected scalar values, array counts,
and SHA-256 of the body.

Do not change behavior.
```

### Prompt 2: Proxyman Browser Baseline

```text
Start Proxyman and clear the current session.

If Proxyman MCP is available, use it for setup. If not, manually configure the
browser to use Proxyman and export HAR/archive evidence.

Start OASIS with:
python3 map_api.py

If Proxyman is unavailable through MCP, run the fallback browser capture:
node scripts/browser_performance_capture.js

If Proxyman manual proxy is available, route Chromium through it:
node scripts/browser_performance_capture.js --proxy-server=http://127.0.0.1:<proxyman-port>

Use a fresh browser profile or disabled cache for the cold run.

Capture:
1. cold /index.html first paint
2. warm reload
3. search focus and query "NVDA"
4. switch Standard -> Dark -> Satellite -> Standard
5. fetch DCF workbook
6. open entity drawer for GM
7. open Data Quality panel
8. fetch report preview

Save:
- docs/evidence/performance/03-local-first-paint.har
- docs/evidence/performance/04-local-reload.har
- docs/evidence/performance/05-local-search-intent.har
- docs/evidence/performance/06-local-map-interactions.har
- docs/evidence/performance/07-local-dcf-download.har
- docs/evidence/performance/12-local-entity-drawer.har
- docs/evidence/performance/13-local-data-quality-panel.har
- docs/evidence/performance/14-local-report-preview.har
- docs/evidence/performance/11-browser-har-summary.json
- docs/evidence/performance/08-proxyman-findings.md

Record request count, transferred bytes, slowest 20 requests, duplicate
requests, cache misses, missing compression, external hosts, console errors,
whether /api/universe/bulk appeared before first paint, and whether drawer,
data-quality, and report surfaces introduce new heavyweight requests.

Do not edit code.
```

### Prompt 3: API Latency Baseline

```text
Measure local API latency without changing product code.

Run enough samples to report p50/p95 for:
- GET /
- GET /index.html
- GET /data/universe_core.json
- GET /api/bootstrap/signals
- GET /api/map/layers
- GET /api/map/entities.geojson?bbox=-180,-90,180,90
- GET /api/map/relationships.geojson?bbox=-180,-90,180,90
- GET /api/universe/bulk
- GET /api/entity/GM
- GET /api/entity/GM/reverse-dcf
- GET /api/entity/GM/comps?cap=8
- GET /api/entity/GM/events
- GET /api/entity/GM/risk
- GET /api/data-quality/dashboard
- GET /api/reports/asset/asset%3Ademo-farm-iowa
- POST report generation endpoint if safe in a temp/generated-output context
- GET DCF workbook endpoint

Capture:
- cold and warm timings where applicable
- status code
- response bytes
- content-encoding
- cache-control
- etag/304 behavior
- body SHA-256 for representative first responses

Save docs/evidence/performance/07-local-api-latency.json.

Do not change behavior.
```

### Prompt 4: Auth and Map-Slot Baseline

```text
Measure Phase 1 auth and Map Studio slot flows through server.app.

Use a temporary local SQLite database. Do not use or commit secrets. Do not
change product code.

Capture request/response behavior and latency for:
- register
- email verification using the in-memory/sandbox email backend
- login
- session validation/current-user endpoint
- session list
- map slot list
- map slot read
- map slot write
- rename
- reset
- export
- import
- duplicate
- password reset request/complete
- password change
- session revoke
- logout-all
- account delete
- healthz/readyz/version
- CSRF rejection
- logout

Save:
- docs/evidence/performance/06-local-auth-and-map-slots.har if captured through Proxyman
- docs/evidence/performance/06-local-auth-and-map-slots.json summary

Report p50/p95 for session validation, map-slot read, and map-slot write. Treat
password/account/duplicate/health operations as one-shot route coverage unless
a later staging finding turns them into latency targets. Do not change behavior.

Use the repo-native local baseline helper:

python3 scripts/auth_mapslot_performance_baseline.py --samples 25

Use the real HTTP capture helper when Proxyman needs to see auth/map-slot
traffic through the HTTP stack:

python3 scripts/auth_mapslot_http_capture.py --samples 20 --proxy-server=http://127.0.0.1:<proxyman-port>

For noise comparison, run the same HTTP capture without the proxy:

python3 scripts/auth_mapslot_http_capture.py --samples 20 --output-file=06-local-auth-and-map-slots-http-direct.json
```

### Prompt 5: Findings and Patch Plan

```text
Analyze all evidence in docs/evidence/performance/.

Do not implement yet.

Rank candidate optimizations by:
- measured latency/transfer impact
- behavior-change risk
- security risk
- implementation size
- testability
- rollback ease

Only propose changes that preserve existing outputs and semantics.

Prefer low-risk classes first:
- duplicate request removal
- cache-control/ETag/header fixes
- compression gaps
- lazy/deferred non-critical loads
- DB indexes/query plans
- query/result memoization keyed by file mtime or DB version
- payload trimming only when the consumed schema is already intentionally smaller
- moving request-independent work out of request paths

Save docs/evidence/performance/09-optimization-plan.md.
```

### Prompt 6: One-Slice Optimization

```text
Implement exactly one optimization from the approved plan.

Rules:
- preserve all user-visible behavior
- preserve API schemas, status codes, and error semantics
- preserve auth, CSRF, rate limits, and security headers
- add or update tests proving behavior did not change
- update performance evidence with before/after numbers
- run python3 scripts/performance_baseline.py --samples 7
- run python3 scripts/auth_mapslot_performance_baseline.py --samples 25
- run python3 -m pytest -q
- run npx playwright test
- commit only the focused change and evidence

If a proposed optimization requires changing behavior, stop and report it as
not allowed.
```

### Prompt 7: Before/After Report

```text
Compare the baseline and latest measurements.

Create docs/evidence/performance/10-before-after-summary.md with:
- commit before
- commit after
- exact optimization made
- affected flows
- before/after p50/p95
- before/after transferred bytes
- before/after request count
- tests run
- Proxyman/HAR evidence references
- any residual risk
- explicit statement that navigation/actions/outputs/API schemas were preserved
```

### Prompt 8: Deployed/Staging Proxyman Capture

```text
Run the deployed/staging Proxyman capture without editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- Proxyman running and session cleared
- target URL available as STAGING_URL
- SSL proxying enabled for the staging host and approved map tile/glyph hosts

First record target readiness:
- curl -I "$STAGING_URL/index.html"
- curl -I "$STAGING_URL/healthz" if server.app is deployed
- curl -I "$STAGING_URL/readyz" if server.app is deployed

Run:
node scripts/browser_performance_capture.js \
  --base-url="$STAGING_URL" \
  --no-start-server=true \
  --proxy-server=http://127.0.0.1:9090 \
  --flow-prefix=15-staging \
  --summary-file=15-staging-browser-har-summary.json

Then run the direct comparison:
node scripts/browser_performance_capture.js \
  --base-url="$STAGING_URL" \
  --no-start-server=true \
  --flow-prefix=15-staging-direct \
  --summary-file=15-staging-browser-har-summary-direct.json

Update:
- docs/evidence/performance/08-proxyman-findings.md
- docs/evidence/performance/09-optimization-plan.md
- docs/evidence/performance/10-before-after-summary.md
- docs/evidence/performance/15-staging-capture-status.json
- docs/evidence/performance/16-performance-coverage-audit.md

Report:
- first paint request count/transfer
- reload transfer and cache behavior
- search intent bulk timing
- Map Studio external hosts, slowest tile/glyph/style requests, console errors
- DCF/report/entity-drawer transfer and status
- whether any result justifies a behavior-preserving product-code optimization
```

### Prompt 9: Evidence Coverage Audit

```text
Audit performance evidence coverage before proposing another product-code
optimization.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Run:
python3 scripts/performance_evidence_audit.py

Inspect:
- docs/evidence/performance/16-performance-coverage-audit.md
- docs/evidence/performance/16-performance-coverage-audit.json

Do not make product-code changes unless the audit and Proxyman evidence identify
a specific behavior-preserving optimization with before/after proof. If the
audit says deployed or compose staging evidence is missing, keep larger
architecture/payload changes gated.
```

### Prompt 10: Route-Family Performance Probe

```text
Measure safe lower-traffic route families before proposing another optimization.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Do not edit product code.

Run:
python3 scripts/route_family_performance_probe.py --samples 3
python3 scripts/performance_evidence_audit.py

Inspect:
- docs/evidence/performance/17-route-family-performance-probes.json
- docs/evidence/performance/16-performance-coverage-audit.md

Require all measured routes in 17-route-family-performance-probes.json to have
status_codes [200]. The helper may sandbox file-backed mutation routes by
temporarily redirecting module-level JSON paths; verify real JSON data files are
unchanged if you alter that harness. Treat skipped routes as fixture gaps, not
as optimization evidence.

Do not optimize from this probe alone. Use it to close coverage gaps and decide
which route families need real Proxyman browser or staging evidence next.
```

### Prompt 11: Headless MapLibre Diagnostic

```text
Classify headless MapLibre/WebGL console warnings without editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Run through Proxyman if available:
node scripts/maplibre_headless_diagnostic.js --proxy-server=http://127.0.0.1:9090
python3 scripts/performance_evidence_audit.py

Inspect:
- docs/evidence/performance/18-headless-maplibre-diagnostic.json
- docs/evidence/performance/16-performance-coverage-audit.md

Only treat the headless shader warning as classified if every diagnostic variant
has styleLoaded true, basemapPreserved true, and zero unclassified errors.
```

### Prompt 12: Public Staging DNS/TLS/Security Preflight

```text
Run the public staging preflight without editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- STAGING_URL is set to the approved staging HTTPS URL.
- If Cloudflare Access service-token auth is required, set:
  OASIS_CF_ACCESS_CLIENT_ID
  OASIS_CF_ACCESS_CLIENT_SECRET

Run:
python3 scripts/public_staging_preflight.py \
  --base-url="$STAGING_URL" \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET

Inspect:
- docs/evidence/public-staging/00-public-staging-preflight.json

Verify:
- DNS resolves.
- TLS certificate is valid.
- HTTP redirects to HTTPS.
- /healthz, /readyz, /version, and /index.html are reachable through the
  intended access boundary.
- HSTS has max-age but does not include includeSubDomains or preload.
- CSP, no-sniff, referrer policy, permissions policy, cache, vary, ETag, and
  cookie flags are recorded.

Do not paste secrets, private access URLs, cookies, or full auth headers into
evidence.
```

### Prompt 12.5: Public Staging Infrastructure Evidence Reports

```text
Generate public staging infrastructure reports from structured non-secret
provider evidence. Do not edit product behavior.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- docs/evidence/public-staging/00-public-staging-preflight.json exists.
- docs/evidence/public-staging/01-image-manifest.json exists.
- docs/evidence/public-staging/02-render-deploy.json exists.
- docs/evidence/public-staging/infra-evidence.json exists.

Build docs/evidence/public-staging/infra-evidence.json from Cloudflare, Render,
and migration evidence using only:
- provider names
- booleans for completed checks
- HTTP status codes
- commit IDs and image digests
- environment variable names
- redaction confirmations

The JSON must contain:
- cloudflare_access
- render_services
- migration

Do not include secret values, database URLs, SMTP credentials, storage
credentials, cookies, raw authorization headers, Cloudflare service-token
values, or private token-bearing URLs.

Run:
python3 scripts/public_staging_infra_reports.py --print-template \
  > /tmp/oasis-infra-evidence.template.json

python3 scripts/public_staging_infra_reports.py \
  --input=docs/evidence/public-staging/infra-evidence.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --render-deploy=docs/evidence/public-staging/02-render-deploy.json \
  --image-manifest=docs/evidence/public-staging/01-image-manifest.json \
  --output-dir=docs/evidence/public-staging \
  --summary-output=docs/evidence/public-staging/infra-evidence-summary.json

Inspect:
- docs/evidence/public-staging/02-dns-tls-edge.md
- docs/evidence/public-staging/03-cloudflare-access.md
- docs/evidence/public-staging/04-render-services.md
- docs/evidence/public-staging/05-migration-version.md
- docs/evidence/public-staging/infra-evidence-summary.json

Each report must show `Verdict: pass`, and the summary must validate in the
final audit. Any missing Cloudflare Access boundary, failed preflight, Render
deploy/image mismatch, missing managed Postgres/storage proof, SQLite fallback,
migration revision mismatch, or secret-like value keeps
the report at `Verdict: investigate`.
```

### Prompt 12.75: Public Staging Deployment Automation Evidence

```text
Generate public staging deployment automation evidence from the real GitHub
Actions Deploy run. Do not edit product behavior.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- The Deploy workflow completed successfully for staging.
- docs/evidence/public-staging/00-public-staging-preflight.json exists.
- docs/evidence/public-staging/01-image-manifest.json exists.
- docs/evidence/public-staging/02-render-deploy.json exists.
- GitHub `staging` environment protection and manual approval status were
  checked in the repository settings or the run audit trail.

Run:
python3 scripts/public_staging_deployment_report.py --print-template \
  > /tmp/oasis-deployment-automation-run.template.json

Create docs/evidence/public-staging/deployment-automation-run.json from the
successful GitHub Actions Deploy run using only:
- workflow name
- run ID and run attempt
- event, branch, commit
- environment name
- conclusion/status strings
- step names and success/failure conclusions
- artifact name
- booleans for protected environment, manual approval, staging secret isolation,
  deployment concurrency observed, evidence artifact uploaded, and no production
  deploy

Do not include secrets, token-bearing URLs, authorization headers, private log
URLs, raw provider identifiers, cookies, SMTP credentials, storage credentials,
or database URLs.

Generate:
python3 scripts/public_staging_deployment_report.py \
  --run-evidence=docs/evidence/public-staging/deployment-automation-run.json \
  --image-manifest=docs/evidence/public-staging/01-image-manifest.json \
  --render-deploy=docs/evidence/public-staging/02-render-deploy.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --output=docs/evidence/public-staging/16-deployment-automation.md \
  --summary-output=docs/evidence/public-staging/deployment-automation-summary.json

Inspect:
- docs/evidence/public-staging/16-deployment-automation.md
- docs/evidence/public-staging/deployment-automation-summary.json

Both must show `Verdict: pass`. Any missing protected-environment/manual
approval proof, failed CI step, mutable image, missing SBOM/provenance/scan,
Render image mismatch, preflight failure, missing evidence artifact, production
deploy ambiguity, or secret-like value keeps the final gate unapproved.
```

### Prompt 13: Public Staging Route And Attack-Surface Probe

```text
Probe public staging route families without product-code changes.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Run a safe read-mostly route probe:
python3 scripts/compose_route_family_probe.py \
  --base-url="$STAGING_URL" \
  --samples=3 \
  --verify-tls \
  --output-file=25-public-route-family-probe.json

If Cloudflare Access blocks direct CLI traffic, configure service-token headers
in a temporary local wrapper or use an authenticated Proxyman browser capture
for this gate; do not commit the token values.

Verify:
- public health/version routes are reachable.
- unauthenticated auth/map-slot routes reject as expected.
- no worker-only route is public.
- no internal service port is exposed.
- route count and classification are compared with docs/AUTHORIZATION-MATRIX.md
  and docs/evidence/phase-1-5/route-authorization-inventory.json.
- trusted-host/CORS/CSRF/rate-limit behavior remains explicit.

Generate the route-security evidence report after public preflight, route probe,
and auth/map-slot security evidence are present:

python3 scripts/public_staging_route_security_report.py \
  --route-probe=docs/evidence/performance/25-public-route-family-probe.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --auth-security=docs/evidence/performance/27-public-auth-map-slots.json \
  --output=docs/evidence/public-staging/09-route-security.md \
  --summary-output=docs/evidence/public-staging/route-security-summary.json

The report and summary must end with `Verdict: pass`; otherwise the strict
public gate audit continues to treat route security as unproven.
```

### Prompt 13.25: Public Staging Rate-Limit And Client-IP Evidence

```text
Generate public staging rate-limit evidence without editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- docs/evidence/public-staging/00-public-staging-preflight.json exists.
- docs/evidence/public-staging/route-security-summary.json exists.
- Cloudflare Access/WAF/rate-rule status and logs were reviewed.
- The public staging API replica count is known.

Probe and record rate limiting for:
- login attempts
- registration
- password reset
- search
- financial models
- exports
- map-slot writes
- administrative operations

Also record:
- one API replica plus documented per-process limitation, or multiple replicas
  plus shared/provider-native rate-limit store
- Cloudflare/edge abuse controls
- outer access enforcement
- provider log review
- trusted-proxy/client-IP handling
- spoofed X-Forwarded-For rejection or ignore behavior
- Retry-After presence for app-level 429 responses where expected

Run:
python3 scripts/public_staging_rate_limit_report.py --print-template \
  > /tmp/oasis-rate-limit-evidence.template.json

Create docs/evidence/public-staging/rate-limit-evidence.json from sanitized
public probes and provider evidence. Do not include cookies, authorization
headers, service-token values, tester passwords, raw IP allowlists, private log
URLs, or account identifiers.

Generate:
python3 scripts/public_staging_rate_limit_report.py \
  --input=docs/evidence/public-staging/rate-limit-evidence.json \
  --route-security=docs/evidence/public-staging/route-security-summary.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --output=docs/evidence/public-staging/18-rate-limiting.md \
  --summary-output=docs/evidence/public-staging/rate-limit-summary.json

Inspect:
- docs/evidence/public-staging/18-rate-limiting.md
- docs/evidence/public-staging/rate-limit-summary.json

Both must show `Verdict: pass`. If public staging has more than one API replica,
the summary must prove a shared limiter store or provider-native equivalent.
Otherwise the private-beta gate remains unapproved.
```

### Prompt 13.3: Public Staging Object Storage Evidence

```text
Generate public staging object-storage evidence without editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- docs/evidence/public-staging/infra-evidence-summary.json exists.
- docs/evidence/public-staging/ops-evidence-summary.json exists.
- The staging object-storage provider, bucket/namespace policy, lifecycle
  policy, and export failure behavior were checked.

Verify and record:
- Cloudflare R2 or approved S3-compatible staging backend
- separate staging bucket or namespace
- private default object access
- server-side encryption
- no public bucket listing
- provider-managed least-privilege credentials
- no browser-exposed raw storage credentials
- expiring signed download/operation authorization
- application ownership checks before object access
- lifecycle expiration for temporary/private artifacts
- generated exports, approved logos, future report artifacts, and temporary
  private files are supported
- max export size limit and content-type validation
- storage-unavailable export behavior is accurate
- partial output is not offered
- retry behavior is bounded
- storage errors do not leak secrets

Run:
python3 scripts/public_staging_storage_report.py --print-template \
  > /tmp/oasis-storage-evidence.template.json

Create docs/evidence/public-staging/storage-evidence.json from sanitized
provider settings, public probes, and export failure evidence. Do not include
bucket account IDs, access keys, secret keys, raw signed URLs, cookies,
authorization headers, service-token values, private log URLs, screenshots with
credentials, or account identifiers.

Generate:
python3 scripts/public_staging_storage_report.py \
  --input=docs/evidence/public-staging/storage-evidence.json \
  --infra-summary=docs/evidence/public-staging/infra-evidence-summary.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --output=docs/evidence/public-staging/19-object-storage.md \
  --summary-output=docs/evidence/public-staging/storage-summary.json

Inspect:
- docs/evidence/public-staging/19-object-storage.md
- docs/evidence/public-staging/storage-summary.json

Both must show `Verdict: pass`. Any public listing, raw browser credential,
missing signed-expiry/ownership check, missing size/content-type limit, or
unbounded storage-failure behavior keeps the private-beta gate unapproved.
```

### Prompt 13.5: Public Staging Auth And Map-Slot Probe

```text
Generate deployed public auth, email-token, CSRF, and map-slot evidence without
editing product code.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- STAGING_URL is set to the approved staging HTTPS URL.
- The two tester emails are allowed by OASIS_REGISTRATION_ALLOWED_EMAILS.
- A disposable lifecycle tester email is also allowed by
  OASIS_REGISTRATION_ALLOWED_EMAILS.
- If Cloudflare Access service-token auth is required, set:
  OASIS_CF_ACCESS_CLIENT_ID
  OASIS_CF_ACCESS_CLIENT_SECRET
- Use fresh tester accounts when proving email verification delivery.

First request the registration verification and password reset emails:

export OASIS_PUBLIC_TESTER_A_EMAIL=...
export OASIS_PUBLIC_TESTER_A_PASSWORD=...
export OASIS_PUBLIC_TESTER_B_EMAIL=...
export OASIS_PUBLIC_TESTER_B_PASSWORD=...
export OASIS_PUBLIC_LIFECYCLE_EMAIL=...
export OASIS_PUBLIC_LIFECYCLE_PASSWORD=...
export OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD=...

python3 scripts/public_staging_auth_map_slots_probe.py \
  --base-url="$STAGING_URL" \
  --proxy-server=http://127.0.0.1:9090 \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET

This first run is expected to write an investigate verdict until the delivered
email tokens are supplied. Do not paste token values into docs, commits,
Proxyman exports, screenshots, or terminal summaries.

After collecting the token values from the delivered emails, rerun:

export OASIS_PUBLIC_TESTER_A_VERIFY_TOKEN=...
export OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN=...
export OASIS_PUBLIC_LIFECYCLE_VERIFY_TOKEN=...
export OASIS_PUBLIC_TESTER_A_RESET_TOKEN=...
export OASIS_PUBLIC_TESTER_A_RESET_PASSWORD=...

python3 scripts/public_staging_auth_map_slots_probe.py \
  --base-url="$STAGING_URL" \
  --proxy-server=http://127.0.0.1:9090 \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET

Inspect:
- docs/evidence/performance/27-public-auth-map-slots.json

Generate:

python3 scripts/public_staging_auth_email_report.py \
  --auth-map-slots=docs/evidence/performance/27-public-auth-map-slots.json \
  --output=docs/evidence/public-staging/06-auth-email.md \
  --summary-output=docs/evidence/public-staging/auth-email-summary.json

python3 scripts/public_staging_email_delivery_report.py --print-template \
  > /tmp/oasis-email-delivery-evidence.template.json

Create docs/evidence/public-staging/email-delivery-evidence.json from
sanitized provider settings, delivered-message status, DNS/sender-domain
configuration, and a controlled delivery-failure retry probe. Do not include
full email addresses, raw message bodies with tokens, SMTP credentials, provider
account IDs, private log URLs, cookies, or authorization headers.

python3 scripts/public_staging_email_delivery_report.py \
  --input=docs/evidence/public-staging/email-delivery-evidence.json \
  --auth-email-summary=docs/evidence/public-staging/auth-email-summary.json \
  --infra-summary=docs/evidence/public-staging/infra-evidence-summary.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --output=docs/evidence/public-staging/20-email-delivery.md \
  --summary-output=docs/evidence/public-staging/email-delivery-summary.json

Verify:
- registration and verification returned expected generic/success responses
- password reset request and completion succeeded
- session cookie is Secure and HttpOnly
- session and CSRF cookies are Secure, SameSite=Lax, Path=/, and host-only
- CSRF rejection is 403
- both users can log in
- exactly three map slots exist for the tester
- stale-version map-slot write returns 409
- cross-user map-slot read is denied with 403 or 404
- direct fourth-slot creation and `slot_number: 4` import attempts are rejected
- disposable lifecycle user can list sessions, revoke a second session, change
  password, prove the old password fails, login with the new password, logout
  all sessions, delete the account, and prove the deleted account cannot log in
- verification and password-reset tokens are rejected when reused
- unknown-account password reset returns the same generic response shape as a
  known-account reset request
- staging/sandbox sender identity, SPF/DKIM/DMARC, token redaction, public
  hostname links, and bounded worker retry for delivery failure are proven
- no passwords, tokens, cookies, authorization values, or complete emails are
  stored in the evidence file

Leave --enforce-app-targets off for external internet timing. Only pass
--enforce-app-targets from a same-region/application-layer measurement context
where internet latency has been separated.
```

### Prompt 14: Public Staging Proxyman Browser Matrix

```text
Capture real public staging browser behavior through Proxyman.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- Proxyman running with session cleared.
- SSL proxying enabled for the staging host and approved map hosts.
- Browser can pass Cloudflare Access.

Run Chrome capture:
node scripts/browser_performance_capture.js \
  --base-url="$STAGING_URL" \
  --no-start-server=true \
  --proxy-server=http://127.0.0.1:9090 \
  --flow-prefix=26-public-staging \
  --summary-file=26-public-staging-browser-har-summary.json

Run the same Chrome capture without Proxyman to separate direct internet/browser
latency from Proxyman-routed capture overhead:
node scripts/browser_performance_capture.js \
  --base-url="$STAGING_URL" \
  --no-start-server=true \
  --flow-prefix=26-public-staging-direct \
  --summary-file=26-public-staging-direct-browser-har-summary.json

The direct capture must use the same HTTPS `$STAGING_URL`, must not pass
`--proxy-server`, and must show clean first-paint/request health independently
of the Proxyman-routed capture. Both captures must include the same eight
browser flows: first paint, reload, search intent, map interactions, DCF
workbook fetch, entity drawer, data-quality panel, and report preview. Every
flow row must reference its saved HAR under `docs/evidence/performance/` and
must record zero sensitive URL query values.

Repeat manually or with equivalent tooling for:
- Brave or Edge
- Firefox
- Safari on macOS
- Mobile Safari where available
- Chrome on Android where available

Verify:
- application shell
- registration, verification, login, session persistence, password reset, logout
- Standard, Dark, and disabled/failed Satellite behavior
- search, entity selection, drawer/rail interactions
- exactly three Map Studio slots
- slot sync, version conflict, export/import
- responsive layout, keyboard navigation, basic accessibility
- no reusable authentication token in localStorage
- no unexpected console errors
- no /api/universe/bulk during first paint
- no unpkg.com

Record browser/OS versions and manual browser checks in:
- docs/evidence/public-staging/browser-matrix.json

Record supplemental public performance evidence in:
- docs/evidence/public-staging/performance-supplemental.json

Start from:
python3 scripts/public_staging_performance_report.py --print-supplemental-template \
  > /tmp/oasis-performance-supplemental.template.json

Fill it from at least two external network locations and provider/runtime
metrics. It must include DNS, TCP, TLS, TTFB, initial transferred bytes, initial
request count, map initialization, Web Vitals (`lcp_ms`, `inp_ms`, `cls`,
`fcp_ms`, `ttfb_ms`, `tbt_ms`), search p50/p95, comps p50/p95, export-job
creation p50/p95, API CPU/memory, worker CPU/memory, database connections,
queue depth, and error rate. Do not include cookies, authorization headers,
private provider URLs, account IDs, or raw telemetry links.

Then generate strict browser and map-provider reports:

python3 scripts/public_staging_browser_reports.py \
  --browser-matrix=docs/evidence/public-staging/browser-matrix.json \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --browser-output=docs/evidence/public-staging/07-browser-matrix.md \
  --map-output=docs/evidence/public-staging/08-map-provider-capture.md \
  --summary-output=docs/evidence/public-staging/browser-map-summary.json

Generate the public performance evidence report:

python3 scripts/public_staging_performance_report.py \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --direct-summary=docs/evidence/performance/26-public-staging-direct-browser-har-summary.json \
  --auth-map-slot=docs/evidence/performance/27-public-auth-map-slots.json \
  --route-probe=docs/evidence/performance/25-public-route-family-probe.json \
  --supplemental=docs/evidence/public-staging/performance-supplemental.json \
  --output=docs/evidence/public-staging/15-performance.md \
  --summary-output=docs/evidence/public-staging/performance-evidence-summary.json
```

### Prompt 14.5: Public Staging Licensing Gate Evidence

```text
Generate licensing gate evidence after public browser/map-provider evidence is
present. Do not edit product behavior or enable unresolved providers.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Prerequisites:
- docs/evidence/public-staging/browser-map-summary.json exists and has pass
  evidence for disabled providers unused, no unpkg.com, no provider credentials,
  and approved map hosts only.
- OASIS_FEATURE_SATELLITE=false, OASIS_FEATURE_PRICES=false, and
  OASIS_FEATURE_LOGOS=false are confirmed in the public staging environment.

Run:
python3 scripts/public_staging_licensing_report.py --print-template \
  > /tmp/oasis-licensing-evidence.template.json

Create docs/evidence/public-staging/licensing-evidence.json from current
official source reviews using only:
- current official source URL
- review date
- commercial-use permission summary
- caching, redistribution, attribution, and offline-use summary
- account/API-key requirement boolean
- replacement provider
- enabled_in_public_staging boolean
- status: approved, disabled, not_selected, or investigate

Cover:
- Esri World Imagery
- CARTO styles and tiles
- Yahoo Finance and yfinance
- company logos
- news sources
- political-trading feeds
- property and parcel data
- other commercial datasets

Do not include account IDs, API keys, cookies, token-bearing URLs, screenshots
with credentials, raw provider authorization headers, or copied full terms text.

Generate:
python3 scripts/public_staging_licensing_report.py \
  --input=docs/evidence/public-staging/licensing-evidence.json \
  --browser-map-summary=docs/evidence/public-staging/browser-map-summary.json \
  --output=docs/evidence/public-staging/17-licensing-gates.md \
  --summary-output=docs/evidence/public-staging/licensing-summary.json

Inspect:
- docs/evidence/public-staging/17-licensing-gates.md
- docs/evidence/public-staging/licensing-summary.json

Both must show `Verdict: pass`. Licensing uncertainty can pass private beta only
when the affected provider is disabled and unused in browser/provider evidence.
Any stale review, unofficial source URL, enabled unresolved provider, missing
replacement, missing feature-flag proof, or unexpected provider host keeps the
final audit unapproved.
```

### Prompt 15: Public Staging Auth, Worker, Backup, Rollback Gate

```text
Complete the public private-beta gate checks without changing product behavior.

Work in:
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis

Using the real staging URL and provider dashboards/logs, verify and record:
- authentication email delivery for registration verification and password reset
- secure session cookie flags, SameSite/path/domain, session rotation, no
  reusable localStorage token, CSRF rejection
- two users, exactly three map slots per user, cross-user denial, conflict
  handling, direct fourth-slot denial, API restart persistence, deploy revision
  compatibility
- controlled noop worker job claim/progress/completion/failure/retry/restart
- API remains responsive while worker runs
- API normal user requests perform zero external acquisition
- object storage private export behavior and bounded failure behavior
- PostgreSQL backup restore into a separate database
- API replacement and failed-health deployment rollback
- section 23 failure exercises for database, worker, API, failed deploy, map,
  object storage, and email failure behavior
- observability signals and alert definitions
- licensing-sensitive providers remain disabled

Record:
- docs/evidence/public-staging/06-auth-email.md
- docs/evidence/public-staging/infra-evidence.json
- docs/evidence/public-staging/ops-evidence.json
- docs/evidence/public-staging/storage-evidence.json
- docs/evidence/public-staging/failure-exercises-evidence.json

Then generate strict infrastructure, operation, object-storage, and
failure-exercise reports:

python3 scripts/public_staging_infra_reports.py --print-template \
  > /tmp/oasis-infra-evidence.template.json

python3 scripts/public_staging_infra_reports.py \
  --input=docs/evidence/public-staging/infra-evidence.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --render-deploy=docs/evidence/public-staging/02-render-deploy.json \
  --image-manifest=docs/evidence/public-staging/01-image-manifest.json \
  --output-dir=docs/evidence/public-staging

python3 scripts/public_staging_ops_reports.py --print-template \
  > /tmp/oasis-ops-evidence.template.json

python3 scripts/public_staging_ops_reports.py \
  --input=docs/evidence/public-staging/ops-evidence.json \
  --output-dir=docs/evidence/public-staging \
  --summary-output=docs/evidence/public-staging/ops-evidence-summary.json

python3 scripts/public_staging_storage_report.py --print-template \
  > /tmp/oasis-storage-evidence.template.json

python3 scripts/public_staging_storage_report.py \
  --input=docs/evidence/public-staging/storage-evidence.json \
  --infra-summary=docs/evidence/public-staging/infra-evidence-summary.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --output=docs/evidence/public-staging/19-object-storage.md \
  --summary-output=docs/evidence/public-staging/storage-summary.json

python3 scripts/public_staging_failure_exercises_report.py --print-template \
  > /tmp/oasis-failure-exercises-evidence.template.json

python3 scripts/public_staging_failure_exercises_report.py \
  --input=docs/evidence/public-staging/failure-exercises-evidence.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --browser-map-summary=docs/evidence/public-staging/browser-map-summary.json \
  --storage-summary=docs/evidence/public-staging/storage-summary.json \
  --email-delivery-summary=docs/evidence/public-staging/email-delivery-summary.json \
  --output=docs/evidence/public-staging/21-failure-exercises.md \
  --summary-output=docs/evidence/public-staging/failure-exercises-summary.json

This writes:
- docs/evidence/public-staging/02-dns-tls-edge.md
- docs/evidence/public-staging/03-cloudflare-access.md
- docs/evidence/public-staging/04-render-services.md
- docs/evidence/public-staging/05-migration-version.md
- docs/evidence/public-staging/10-worker-jobs.md
- docs/evidence/public-staging/11-network-isolation.md
- docs/evidence/public-staging/12-backup-restore.md
- docs/evidence/public-staging/13-failure-rollback.md
- docs/evidence/public-staging/14-observability-alerts.md
- docs/evidence/public-staging/ops-evidence-summary.json
- docs/evidence/public-staging/19-object-storage.md
- docs/evidence/public-staging/storage-summary.json
- docs/evidence/public-staging/21-failure-exercises.md
- docs/evidence/public-staging/failure-exercises-summary.json

Final verdict stays NOT APPROVED unless every public-staging acceptance item is
proven by current evidence.

Each public-staging Markdown evidence file must include `Verdict: pass` only
after that file's checks are actually proven. Use `Verdict: investigate` while
the evidence is partial or failing.

Run the strict gate audit last:

python3 scripts/public_staging_gate_audit.py

Use the generated `final_response` checklist in
docs/evidence/public-staging/99-public-staging-gate-audit.json, plus the
Markdown checklist in `99-public-staging-gate-audit.md`, as the source for the
22-item final release report and remaining risks.
```

## First Optimization Hypotheses

These are hypotheses only; require evidence before implementation.

| Hypothesis | Why it may matter | Required proof before patch |
|---|---|---|
| Some large GeoJSON endpoints are fetched earlier than needed | could inflate first interaction cost | Proxyman waterfall shows request before user intent |
| Some API responses miss gzip or 304 behavior | unnecessary transfer bytes | headers/HAR show body re-download |
| Session validation may hit the DB more often than necessary | impacts every authenticated navigation | p95 above target and query evidence |
| Map slot reads/writes may be doing unnecessary serialization or queries | private beta hot path | measured p95 above target |
| Terrain/status responses may be oversized | existing doc notes `/api/reliefs/dem/status` can be large | HAR confirms user-visible flow pulls it unnecessarily |
| Duplicate bootstrap/API requests occur after reload or mode switch | easy low-risk savings | HAR shows identical duplicate GETs |

## Exit Criteria for a Performance Patch

A performance patch is ready only when:

1. Baseline evidence exists for the affected flow.
2. Before/after evidence uses the same command, browser, cache state, and route.
3. Tests pass.
4. The golden API snapshot still matches expected schema/count/hash rules.
5. Proxyman/HAR shows the intended latency, request count, or transfer improvement.
6. `python3 scripts/performance_evidence_audit.py` has been regenerated and the
   audit agrees the patch improved the intended covered flow without opening a
   new evidence gap.
7. The patch has a focused commit and rollback is obvious.

# Optimization Plan

**Captured:** 2026-07-23  
**Commit:** `9fb135fc54d7f3cf3f44ab3a51fe86d4f0bcb01e`  
**Evidence:** local route/snapshot/latency baseline, Playwright HAR fallback,
Proxyman-routed Chromium capture through `http://127.0.0.1:9090`, and local
temp-DB auth/map-slot p95 baseline. Browser capture now includes first paint,
reload, search intent, map interactions, DCF download, entity drawer hydration,
data-quality panel, and report preview. Auth/map-slot capture now includes both
TestClient baseline and real HTTP runs with and without Proxyman. Staging
capture readiness is tracked in `15-staging-capture-status.json`. Evidence
coverage and route-family gaps are summarized in
`16-performance-coverage-audit.md`, with safe lower-traffic route timings in
`17-route-family-performance-probes.json`.

## Ranked Candidates

| Rank | Candidate | Expected impact | Risk | Evidence needed before patch |
|---:|---|---|---|---|
| 1 | Verify no large decoded payload is pulled before user intent | high if violated | low | Proxyman first-paint HAR showing `/api/universe/bulk`, full entities, or terrain/status before intent |
| 2 | Fix missing cache/compression/304 behavior on any response in hot flows | high transfer savings for large responses, low for small assets | low | HAR showing body redownload or missing `content-encoding`/`etag` |
| 3 | Remove unnecessary competing requests after reload, search, or basemap switching | partly done | low | Search no longer pulls MapLibre runtime; more duplicate candidates need staging evidence |
| 4 | Defer oversized map/status payloads that are not needed for first interaction | medium/high | medium | HAR proving route is requested early and UI does not need it yet |
| 5 | Add DB/session query optimizations for Phase 1 auth/map slots | low locally, maybe medium in staging | medium | staging p95 above target plus query evidence; local p95 already passes |
| 6 | Optimize DCF workbook transfer/revalidation path | partly done | low | `.xlsx` now skips redundant gzip; repeated full downloads still need deployed evidence |
| 7 | Trim or partition large GeoJSON/universe payloads | high | high | browser proof that current consumers can preserve exact visible results with lazy partitioning |

## First Allowed Patch Shape

The first applied patch was the safest HAR-proven case: add an explicit cached
static route for `/js/util.js`, matching the other first-party JavaScript assets.
It changed headers only and preserved the file bytes/behavior.

The next safest patch is whichever Proxyman proves is both visible in the
waterfall and behavior-preserving:

- header-only cache/compression fix
- duplicate request guard
- moving an already non-critical request behind existing user intent
- TestClient/HAR evidence improvements

Do not start with payload partitioning, route rewrites, or schema changes. Those
may be valid later, but only after golden snapshots and browser evidence prove
exact compatibility.

## Regression Gates

Run after every optimization:

```bash
python3 scripts/performance_baseline.py --samples 7
python3 -m pytest -q
npx playwright test
```

The patch must also update:

```text
docs/evidence/performance/08-proxyman-findings.md
docs/evidence/performance/10-before-after-summary.md
```

## Current Decision

Four small product-code optimizations are implemented and verified by
Proxyman-routed HAR evidence: `/js/util.js` now has gzip, `ETag`, and explicit
`Cache-Control`; DCF `.xlsx` downloads now skip redundant gzip and expose the
raw workbook `Content-Length`; the logo PNG now skips pointless gzip while
preserving immutable caching; search intent no longer competes with background
MapLibre warmup.

No larger product-code optimization is approved from this pass alone. The next
step is deployed/staging Proxyman capture, especially for map provider/tile
traffic, reverse-proxy effects, staging authenticated session/map-slot latency,
and any duplicate request candidates. The newly captured entity drawer,
data-quality, report-preview, direct HTTP auth, direct HTTP map-slot, extra
temp-DB auth/account operations, and route-family probe flows are small/clean
enough that they should remain guardrails, not optimization targets, unless
staging evidence contradicts them. Docker is now available locally and compose
staging evidence exists under `15-compose-*`; no public deployed staging URL is
configured yet, so decisions that depend on real deployment/CDN behavior must
wait for public staging evidence. The coverage
audit now shows local performance evidence covers 100% of `map_api` and
`server_app` routes. DEM tilejson and file-backed mutation routes are covered
with temporary fixture/path redirection, so they are guardrails rather than a
claim that local terrain tiles are generated.

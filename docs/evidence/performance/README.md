# Performance Evidence

This directory stores Proxyman, HAR, and script-generated performance evidence
for behavior-preserving OASIS latency work.

Keep evidence small and repeatable in Git. For large Proxyman archives or HAR
files, record the filename, SHA-256, capture date, browser, OS, app commit, and
storage location in a small Markdown or JSON summary.

Expected files are described in:

```text
docs/PERFORMANCE-PROXYMAN-RUNBOOK.md
```

Minimum committed evidence for each optimization:

| File | Purpose |
|---|---|
| `00-preflight.json` | commit, branch, runtime versions, startup/test commands |
| `01-route-inventory.json` | route inventory before behavior-sensitive changes |
| `02-golden-api-snapshots.json` | status/header/schema/hash snapshots for representative endpoints |
| `06-local-auth-and-map-slots.json` | temp-DB auth/session/map-slot p50/p95 timings |
| `06-local-auth-and-map-slots-http.json` | temp-DB auth/session/map-slot timings over real HTTP through Proxyman |
| `06-local-auth-and-map-slots-http-direct.json` | same real HTTP auth/session/map-slot capture without Proxyman for noise comparison |
| `07-local-api-latency.json` | p50/p95/status/bytes/header timings |
| `08-proxyman-findings.md` | human-readable network findings from Proxyman/HAR |
| `09-optimization-plan.md` | ranked, evidence-backed patch plan |
| `10-before-after-summary.md` | final comparison for each committed optimization |
| `11-browser-har-summary.json` | compact summary generated from browser/HAR flows |
| `12-local-entity-drawer.har` | browser/Proxyman evidence for search-driven drawer hydration |
| `13-local-data-quality-panel.har` | browser/Proxyman evidence for Data Quality panel traffic |
| `14-local-report-preview.har` | browser/Proxyman evidence for report-preview traffic |
| `15-staging-capture-status.json` | current deployed/compose staging capture readiness and exact commands |
| `15-staging-*.har` / `15-staging-browser-har-summary.json` | reserved for deployed or compose staging Proxyman captures |
| `16-performance-coverage-audit.json` | machine-readable coverage/gap audit across performance evidence |
| `16-performance-coverage-audit.md` | human-readable evidence coverage audit and next-decision summary |
| `17-route-family-performance-probes.json` | safe lower-traffic and sandboxed write-route p50/p95 probes counted by the coverage audit |
| `18-headless-maplibre-diagnostic.json` | headless MapLibre/WebGL warning classification across Chromium GL variants |

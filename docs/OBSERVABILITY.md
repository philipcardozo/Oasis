# Observability

OpenTelemetry-first, provider-neutral (Datadog/Dynatrace/Grafana can be added
later without changing instrumentation).

## Logs
Structured JSON in staging/production (human-readable in dev). Each log carries a
correlation ID (`server/observability.py`), propagated across API and worker
jobs. `redact()` strips authorization/cookie/token/secret/password fields.

## Never logged
Passwords, session/reset/verify tokens, DB credentials, full auth headers, full
export contents, and — by default — user research queries.

## Signals to emit (roadmap: wire to an OTel collector)
request duration/status/route-template, DB query timing, job duration/result,
external refresh metrics, cache hit/miss, export failures, auth failures,
rate-limit events, dataset freshness, disk usage.

## Health
- `/healthz` liveness (no DB work).
- `/readyz` readiness (DB + analytical store; never external services).
- `/version` build metadata.

## Error reporting
Capture exceptions with environment, release, request/correlation ID, sanitized
route context, user ID only where policy permits, and no secret payloads.

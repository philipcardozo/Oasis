# Staging Observability

## Signals

Collect at minimum:

- request count, status, duration, and route template
- authentication failures
- rate-limit events
- database connection usage and query latency
- worker job state, duration, and failures
- export failures
- cache hit/miss behavior
- dataset freshness
- storage quota pressure
- deployment revision from `/version`
- API and worker health

## Alerts

Create alerts for:

- API readiness failure
- elevated 5xx rate
- authentication failure spike
- database connection exhaustion
- worker queue backlog
- worker failure
- backup failure
- storage quota pressure
- certificate expiration
- high response latency

## Redaction

Do not log passwords, reset/verify tokens, cookies, authorization headers,
database URLs, SMTP credentials, R2 credentials, or private research content.

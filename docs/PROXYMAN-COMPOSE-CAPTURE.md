# Proxyman Compose Capture

Date: 2026-07-30

Compose staging ran at `https://localhost:8443` with Chromium routed through
Proxyman at `http://localhost:9090`.

GCP public-staging Proxyman evidence is still pending. Once the Cloud Run
`run.app` URL exists, repeat the browser/HAR, route-family, and map/auth probes
through Proxyman against that public URL and store the evidence separately from
the compose-local capture.

## Result

The compose stack started successfully after local-staging deployment-config
fixes:

- Caddy local TLS now names `localhost:8443` and `127.0.0.1:8443`, allowing
  Caddy to issue a local certificate for the compose target.
- The worker service disables the API image healthcheck, because the worker is a
  non-HTTP process by design.
- The migrate service now receives the same local SMTP configuration as the app
  services, including `OASIS_EMAIL_FROM`, `OASIS_SMTP_HOST`,
  `OASIS_SMTP_PORT`, and `OASIS_SMTP_STARTTLS`, so staging validation matches
  the running API/worker environment.

Proxyman `6.12.0` build `61200` was recording, system proxying was enabled on
port `9090`, SSL proxying was enabled, and `localhost:8443` was present in the
SSL Proxying include list. A proxied `GET https://localhost:8443/healthz`
returned 200 with Caddy/Uvicorn response headers.

## Captures

- Browser/HAR summary: `docs/evidence/performance/15-compose-browser-har-summary.json`
- Auth/map-slot probe: `docs/evidence/performance/19-compose-auth-map-slots.json`
- Route-family proxy probe: `docs/evidence/performance/21-compose-route-family-proxyman-probe.json`
- Headed Chrome map gate: `docs/evidence/performance/24-compose-map-gate.json`
- Backup/restore drill: `docs/evidence/performance/22-compose-backup-restore-drill.json`
- Failure exercises: `docs/evidence/performance/23-compose-failure-exercises.json`
- Machine-readable status: `docs/evidence/performance/15-staging-capture-status.json`

## Proxyman Visibility

Proxyman MCP verified recording state, port, system proxying, SSL proxying, and
the `localhost:8443` SSL include. The refreshed browser/HAR capture, route-family
proxy probe, and map gate used `http://localhost:9090`. Earlier Chromium launch
with `http://127.0.0.1:9090` failed with `ERR_PROXY_CONNECTION_FAILED`, while
`curl` and Python `requests` succeeded through that address; the final browser
commands therefore used `http://localhost:9090`.

## Verdict

Performance compose capture is current for the local staging target. The broader
private beta gate still needs a public deployed staging URL, but the local
compose reverse-proxy, Proxyman, route-family, headed-map, backup/restore, and
failure-exercise evidence is now present.

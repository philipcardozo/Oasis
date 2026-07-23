# Proxyman Compose Capture

Date: 2026-07-23

Compose staging ran at `https://localhost:8443` with Chromium routed through
Proxyman at `http://127.0.0.1:9090`.

## Result

The compose stack started successfully after two deployment-config fixes:

- Caddy local TLS now names `localhost:8443` and `127.0.0.1:8443`, allowing
  Caddy to issue a local certificate for the compose target.
- The worker service disables the API image healthcheck, because the worker is a
  non-HTTP process by design.

The SMTP compose path also needed `OASIS_SMTP_PORT` and
`OASIS_SMTP_STARTTLS` pass-through so local staging can use a plain temporary
SMTP sink while production keeps STARTTLS enabled by default.

## Captures

- Browser/HAR summary: `docs/evidence/performance/15-compose-browser-har-summary.json`
- Auth/map-slot probe: `docs/evidence/performance/19-compose-auth-map-slots.json`
- Route-family proxy probe: `docs/evidence/performance/21-compose-route-family-proxyman-probe.json`
- Headed Chrome map gate: `docs/evidence/performance/24-compose-map-gate.json`
- Backup/restore drill: `docs/evidence/performance/22-compose-backup-restore-drill.json`
- Failure exercises: `docs/evidence/performance/23-compose-failure-exercises.json`
- Machine-readable status: `docs/evidence/performance/15-staging-capture-status.json`

## Proxyman Visibility

Proxyman MCP recorded localhost and map-provider HTTPS CONNECT flows during the
compose browser run. The current MCP tool set does not expose a way to enable or
verify SSL proxying rules, so decrypted request/response detail is taken from the
Playwright HAR files generated during the same proxied browser run.

## Verdict

Performance compose capture is current for the local staging target. The broader
private beta gate still needs a public deployed staging URL, but the local
compose reverse-proxy, Proxyman, route-family, headed-map, backup/restore, and
failure-exercise evidence is now present.

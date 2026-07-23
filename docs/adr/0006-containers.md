# ADR-0006: Container topology

## Status: accepted

## Decision
One multi-stage image; API and worker differ only by command. Non-root runtime,
healthcheck, no dev reload. Postgres + Caddy in compose for staging simulation.

## Rationale
Shared image = one build, consistent deps, smaller attack surface. Separate
commands enforce the API/worker process boundary. Caddy gives TLS + forwarded
headers without double-compressing the app's pre-gzipped assets.

## Changes this if
Kubernetes/Helm becomes the deploy target → same image, replace compose with a
chart; boundaries are unchanged.

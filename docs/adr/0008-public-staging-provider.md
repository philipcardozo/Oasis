# ADR-0008: Public staging provider

## Status: accepted

## Decision
Use Render for the first public staging deployment: one Docker web service for
the API, one Docker worker service, and Render PostgreSQL. Use Cloudflare for
DNS/edge/private access and R2 storage.

## Rationale
Render preserves the existing container architecture with low operational
burden: Docker services, workers, managed PostgreSQL, private networking,
secrets, health checks, deploy hooks, logs, and rollbacks. The current OASIS
image can run without an application rewrite.

Cloudflare remains the better edge layer for DNS, Access, WAF/rate controls, and
R2 S3-compatible object storage.

Rejected alternatives:

- AWS, Google Cloud, Azure: strong, but more infrastructure surface for this
  private-beta gate.
- Fly.io: good Docker ergonomics, but Fly Postgres is operationally closer to
  self-managed Postgres.
- Railway/DigitalOcean: viable, but Render has the simpler API/worker/Postgres
  path for the current repo.
- Hetzner plus managed services: lower compute cost, higher ops burden.

References:

- Render Blueprints: https://render.com/docs/blueprint-spec
- Render deploy hooks: https://render.com/docs/deploy-hooks

## Changes this if
The beta needs multi-region traffic, stricter enterprise networking, or a shared
rate-limit/queue service before launch.

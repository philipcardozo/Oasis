# Architecture Decision Records

- ADR-0001 Authentication architecture — first-party accounts
- ADR-0002 Session architecture — opaque server-side sessions in cookies
- ADR-0003 Transactional database — PostgreSQL + SQLAlchemy + Alembic
- ADR-0004 Job queue — DB-backed jobs (Redis/RQ deferred)
- ADR-0005 Object storage — local/S3 abstraction, private by default
- ADR-0006 Container topology — one image, API/worker roles, Caddy proxy
- ADR-0007 Observability — OpenTelemetry-first, provider-neutral
- ADR-0008 Public staging provider — Render plus Cloudflare edge
- ADR-0009 Edge access control — Cloudflare Access before OASIS auth
- ADR-0010 Managed PostgreSQL — Render PostgreSQL for staging
- ADR-0011 Container registry — GHCR immutable images and attestations
- ADR-0012 Public staging object storage — Cloudflare R2 via S3 adapter
- ADR-0013 Staging email provider — Postmark SMTP
- ADR-0014 Deployment automation — protected GitHub Actions staging deploy

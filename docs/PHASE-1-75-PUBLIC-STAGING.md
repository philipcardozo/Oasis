# OASIS Phase 1.75 Public Staging Gate

Date: 2026-07-23

Verdict: NOT APPROVED

Phase 1.75 is the gate between local compose acceptance and a controlled
authenticated private beta. The repository now contains the public-staging
scaffold, deployment workflow, HSTS-safe staging configuration, and preflight
verification helper. The gate is not approved until a real staging hostname is
provisioned and the evidence below is captured from that public URL.

## Selected Architecture

Provider split:

- Cloudflare: DNS, TLS edge, WAF/rate rules, Access private-beta boundary, R2
  S3-compatible object storage.
- Render: API web service, worker service, managed PostgreSQL, service secrets,
  logs, health checks, image-backed deploys, rollback.
- GitHub Actions + GHCR: tests, image build, SBOM/provenance, vulnerability scan,
  immutable image publication, protected staging deploy workflow.
- Postmark SMTP: staging transactional email for registration verification and
  password reset.

The current branch is `phase1.75/public-staging`. The staging deployment should
use `main` after review/merge.

## Implemented In Repo

- `render.yaml` defines image-backed `oasis-api-staging` and
  `oasis-worker-staging` services plus isolated Render PostgreSQL.
- `.github/workflows/deploy.yml` runs tests, validates migrations, publishes an
  immutable GHCR image with SBOM/provenance, scans it, triggers Render deploy
  through the Render API using the exact image digest, and runs public preflight.
- `scripts/render_deploy_image.py` deploys the tested image to API first, waits
  for terminal success, then deploys the worker with the same image.
- `scripts/public_staging_preflight.py` records DNS, TLS, HTTP-to-HTTPS redirect,
  headers, `/healthz`, `/readyz`, and `/version`.
- `server.config.Settings.hsts_header` makes staging HSTS explicit and avoids
  `includeSubDomains`/`preload` by default.
- `server.health` now falls back to `RENDER_GIT_COMMIT` for `/version` commit
  reporting when `OASIS_BUILD_COMMIT` is not set.

## Required Environment

GitHub environment `staging`:

- variable: `STAGING_URL`
- secret: `RENDER_API_KEY`
- secret: `RENDER_API_SERVICE_ID`
- secret: `RENDER_WORKER_SERVICE_ID`
- secret: `OASIS_CF_ACCESS_CLIENT_ID`
- secret: `OASIS_CF_ACCESS_CLIENT_SECRET`

Render workspace:

- registry credential named `ghcr-oasis` with read access to
  `ghcr.io/philipcardozo/oasis`.
- image-backed services initially configured with
  `ghcr.io/philipcardozo/oasis:staging-bootstrap`; CI replaces this with the
  tested digest for every deploy.

Render environment group `oasis-staging-shared`:

- `OASIS_PUBLIC_BASE_URL=https://staging.<approved-domain>`
- `OASIS_API_BASE_URL=https://staging.<approved-domain>`
- `OASIS_ALLOWED_ORIGINS=https://staging.<approved-domain>`
- `OASIS_TRUSTED_HOSTS=staging.<approved-domain>`
- Postmark SMTP settings.
- Cloudflare R2 bucket, endpoint, and least-privilege access keys.

Do not commit any real secret or private token-bearing URL.

## Evidence To Capture

Store public-staging evidence in `docs/evidence/public-staging/`:

- `00-public-staging-preflight.json`
- `01-image-manifest.json`
- `02-dns-tls-edge.md`
- `03-cloudflare-access.md`
- `04-render-services.md`
- `05-migration-version.md`
- `06-auth-email.md`
- `07-browser-matrix.md`
- `08-map-provider-capture.md`
- `09-route-security.md`
- `10-worker-jobs.md`
- `11-network-isolation.md`
- `12-backup-restore.md`
- `13-failure-rollback.md`
- `14-observability-alerts.md`
- `15-performance.md`

## Acceptance Status

Current status:

- Public hostname: missing.
- Public TLS: missing.
- Outer access control: scaffolded, not verified.
- Managed PostgreSQL: scaffolded, not provisioned.
- API/worker separation: scaffolded, not deployed.
- Exact image digest deployment: workflow scaffolded, not run.
- Email delivery: selected, not verified.
- Object storage: selected, not verified.
- Browser matrix: pending public URL.
- Backup/restore: pending managed PostgreSQL drill.
- Rollback: pending deployed revision.
- Alerts: pending provider setup.
- Performance: local/compose evidence exists; public latency evidence pending.

Private-beta verdict remains `NOT APPROVED`.

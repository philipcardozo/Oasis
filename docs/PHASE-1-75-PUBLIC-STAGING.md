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
- `render.yaml` runs `python -m alembic upgrade head && python -m
  server.migration_check --expected 29995ef61d8e` as the API predeploy step, so
  migration failure or revision mismatch stops the release before the worker
  deploy.
- `scripts/render_deploy_image.py` deploys the tested image to API first, waits
  for terminal success after the migration check, then deploys the worker with
  the same image.
- `scripts/public_staging_preflight.py` records DNS, TLS, HTTP-to-HTTPS redirect,
  headers, `/healthz`, `/readyz`, and `/version`.
- `server.config.Settings.hsts_header` makes staging HSTS explicit and avoids
  `includeSubDomains`/`preload` by default.
- `server.health` now falls back to `RENDER_GIT_COMMIT` for `/version` commit
  reporting when `OASIS_BUILD_COMMIT` is not set.
- Secure-mode config now fails fast when email is not SMTP, when SMTP host or
  sender values are missing, and when configured S3/R2 storage lacks bucket,
  endpoint, or credentials.

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
- `OASIS_REGISTRATION_ALLOWED_EMAILS` with the approved private-beta tester
  emails, unless the Cloudflare Access policy is the documented sole invitation
  boundary for that drill.
- `OASIS_EMAIL_BACKEND=smtp`, real `OASIS_SMTP_HOST`, non-local
  `OASIS_EMAIL_FROM`, and matching SMTP username/password when the provider
  requires authentication.
- If `OASIS_STORAGE_BACKEND=s3`, set bucket, endpoint, and least-privilege
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.

Do not commit any real secret or private token-bearing URL.

## Evidence To Capture

Store public-staging evidence in `docs/evidence/public-staging/`:

- `00-public-staging-preflight.json`
- `01-image-manifest.json`
- `02-render-deploy.json`
- `16-deployment-automation.md`, generated from the GitHub Actions Deploy run,
  workflow file, image manifest, Render deploy result, and public preflight
  with `scripts/public_staging_deployment_report.py`
- `deployment-automation-summary.json`, generated beside
  `16-deployment-automation.md` for strict protected-environment,
  manual-approval, concurrency, immutable-image, deploy, preflight, and
  artifact-upload checks
- `02-dns-tls-edge.md`, generated from public preflight and infra evidence
  with `scripts/public_staging_infra_reports.py`
- `03-cloudflare-access.md`, generated from sanitized Cloudflare Access
  evidence with `scripts/public_staging_infra_reports.py`
- `04-render-services.md`, generated from sanitized Render service/deploy
  evidence with `scripts/public_staging_infra_reports.py`
- `05-migration-version.md`, generated from the Render predeploy log summary
  and `server.migration_check` evidence with
  `scripts/public_staging_infra_reports.py`
- `infra-evidence-summary.json`, generated beside the infrastructure Markdown
  reports for strict DNS/TLS, Cloudflare Access, Render, secret, Postgres, and
  migration checks
- `06-auth-email.md`
- `auth-email-summary.json`, generated beside `06-auth-email.md` for strict
  email verification, password-reset, secure-cookie, and CSRF checks
- `07-browser-matrix.md`
- `08-map-provider-capture.md`
- `browser-map-summary.json`, generated beside the browser/map Markdown reports
  for strict browser matrix, network-flow, provider-host, and map-license checks
- `09-route-security.md`, generated from public route/preflight/auth evidence
  with `scripts/public_staging_route_security_report.py`
- `route-security-summary.json`, generated beside `09-route-security.md` for
  strict CSRF, cross-user, route-inventory, header, and rate-limit-class checks
- `10-worker-jobs.md`
- `11-network-isolation.md`
- `12-backup-restore.md`
- `13-failure-rollback.md`
- `14-observability-alerts.md`
- `ops-evidence-summary.json`, generated beside the ops Markdown reports for
  strict worker, network-isolation, backup, rollback, observability, and alert checks
- `15-performance.md`, generated from public staging HAR/probe summaries with
  `scripts/public_staging_performance_report.py`
- `performance-evidence-summary.json`, generated beside `15-performance.md`
  for strict Proxyman, direct-comparison, DNS/TLS, and app-layer p95 validation
- `17-licensing-gates.md`, generated from current official-source licensing
  review metadata and browser/map provider evidence with
  `scripts/public_staging_licensing_report.py`
- `licensing-summary.json`, generated beside `17-licensing-gates.md` for strict
  feature-flag, disabled-provider, official-source, and browser-provider checks
- `99-public-staging-gate-audit.json`
- `99-public-staging-gate-audit.md`

Every public-staging Markdown evidence file must include an explicit
`Verdict: pass` line after the evidence is complete. Use
`Verdict: investigate` for partial or failed evidence; the strict audit will not
count that file as proven.

## Acceptance Status

Current status:

- Public hostname: missing.
- Public TLS: missing.
- Outer access control: scaffolded, not verified.
- OASIS registration allowlist: implemented, not configured/proven publicly.
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

Run the strict audit before changing that verdict:

```bash
python3 scripts/public_staging_gate_audit.py
```

# OASIS GCP Staging Deployment

Date: 2026-08-02

Verdict: NOT DEPLOYED

This runbook preserves the current Docker architecture while targeting Google
Cloud staging:

```text
Cloud Run service: oasis-staging API/web
Cloud Run worker pool: oasis-staging-worker continuous worker
Cloud Run job: oasis-staging-migrate migrations
Cloud SQL PostgreSQL: oasis-staging-postgres
Artifact Registry: us-east1 Docker images
Secret Manager: session, database, and SMTP credentials
Cloud Storage: private export/object bucket mounted at /app/outputs
Region: us-east1
```

The first GCP staging URL should be the generated `run.app` URL. A custom
domain can be added later after the base public staging gates pass.

## Current Container Contract

Actual Compose services:

```text
db
migrate
api
proxy
worker
```

Actual role commands:

```text
migrate: python -m alembic upgrade head
api: Dockerfile CMD, uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8788}
worker: python -m server.worker
```

The API image now reads Cloud Run `PORT` and falls back to `8788` when `PORT`
is absent. The same image can run the API, migration job, and worker pool. The
FastAPI app serves the frontend/static assets directly, so Caddy is not required
on Cloud Run.

Do not write required persistent staging state to the container filesystem:

```text
accounts, sessions, map slots: Cloud SQL PostgreSQL
exports/generated objects: Cloud Storage mounted at /app/outputs
secrets: Secret Manager
analytical read-only seed store: image contents or mounted read-only dataset
```

For GCP, use the existing local storage backend over the Cloud Storage mount:

```text
OASIS_STORAGE_BACKEND=local
OASIS_STORAGE_DIR=/app/outputs/storage
```

This keeps persistent exports outside the container filesystem without adding a
new storage SDK dependency to the application.

## Provider Gates

Set:

```bash
export OASIS_DEPLOY_PROVIDER=gcp
```

The GCP config contract requires these non-secret values:

```text
GCP_PROJECT_ID
GCP_REGION=us-east1
GCP_ARTIFACT_REPOSITORY
GCP_CLOUD_RUN_SERVICE
GCP_CLOUD_RUN_WORKER_POOL
GCP_CLOUD_SQL_INSTANCE
GCP_STORAGE_BUCKET
STAGING_URL
```

Under `OASIS_DEPLOY_PROVIDER=gcp`, Render service IDs and Cloudflare Access
service-token secrets are not required by readiness. Database URL, session
secret, and SMTP password stay in Secret Manager, not GitHub secrets.

Run the GCP checklist:

```bash
python3 scripts/public_staging_setup_checklist.py --provider=gcp
python3 scripts/public_staging_config_contract.py --provider=gcp
python3 scripts/public_staging_readiness.py --allow-not-ready
```

## Manual Bootstrap

Use globally unique names:

```bash
export PROJECT_ID="oasis-staging-CHANGE-ME"
export REGION="us-east1"
export AR_REPO="oasis"
export IMAGE_NAME="oasis"
export API_SERVICE="oasis-staging"
export WORKER_POOL="oasis-staging-worker"
export MIGRATE_JOB="oasis-staging-migrate"
export SQL_INSTANCE="oasis-staging-postgres"
export DB_NAME="oasis"
export DB_USER="oasis_app"
export STORAGE_BUCKET="${PROJECT_ID}-oasis-staging"
```

Authenticate, create/select the project, link billing, and create a budget
before Cloud SQL or the worker pool is enabled.

Enable APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

Create service accounts:

```bash
gcloud iam service-accounts create oasis-api --display-name="OASIS staging API"
gcloud iam service-accounts create oasis-worker --display-name="OASIS staging worker"
gcloud iam service-accounts create oasis-migrate --display-name="OASIS staging migrations"
```

Grant the runtime identities Cloud SQL Client and Secret Manager Secret
Accessor. Grant only bucket-scoped object access for the API and worker service
accounts.

## Image Build

Use Cloud Build so the image architecture matches Cloud Run:

```bash
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:$(git rev-parse HEAD)"
gcloud builds submit --tag "$IMAGE" .
```

Local exact-image smoke:

```bash
docker pull "$IMAGE"
docker run --rm -e PORT=8080 -p 8080:8080 "$IMAGE"
curl -i http://localhost:8080/healthz
```

## Cloud Run Deployment

The manual workflow is codified in `.github/workflows/deploy-gcp.yml`:

```text
checkout
authenticate with Workload Identity Federation
set up gcloud
run config contract and readiness
install/test
build image with Cloud Build
deploy migration job
execute migration
deploy API as candidate revision with no traffic
run public preflight against candidate URL
run public Playwright against candidate URL
deploy worker pool
shift API traffic to candidate after gates pass
upload sanitized evidence
```

The migration command is exactly:

```text
python -m alembic upgrade head
```

The worker command is exactly:

```text
python -m server.worker
```

Cloud Run service and worker pool deployments mount Cloud Storage at
`/app/outputs`; keep `OASIS_STORAGE_DIR=/app/outputs/storage`.

## GitHub Environment

Create GitHub environment `staging` with these variables:

```text
OASIS_DEPLOY_PROVIDER=gcp
GCP_PROJECT_ID=<project>
GCP_REGION=us-east1
GCP_ARTIFACT_REPOSITORY=oasis
GCP_CLOUD_RUN_SERVICE=oasis-staging
GCP_CLOUD_RUN_WORKER_POOL=oasis-staging-worker
GCP_CLOUD_SQL_INSTANCE=oasis-staging-postgres
GCP_STORAGE_BUCKET=<bucket>
STAGING_URL=<generated run.app URL>
GCP_WORKLOAD_IDENTITY_PROVIDER=<provider resource name>
GCP_DEPLOY_SERVICE_ACCOUNT=oasis-deployer@<project>.iam.gserviceaccount.com
```

Do not create or upload a JSON service-account key.

## Acceptance Evidence

After the public `run.app` URL exists:

```bash
export OASIS_DEPLOY_PROVIDER=gcp
export STAGING_URL="$(gcloud run services describe "$API_SERVICE" --region="$REGION" --format='value(status.url)')"

python3 scripts/public_staging_config_contract.py --provider=gcp
python3 scripts/public_staging_readiness.py
python3 scripts/public_staging_deployment_report.py
python3 scripts/public_staging_gate_audit.py

PLAYWRIGHT_BASE_URL="$STAGING_URL" npx playwright test
OASIS_PUBLIC_PLAYWRIGHT_BASE_URL="$STAGING_URL" npx playwright test --config=playwright.public.config.js
```

Then run the public full-verification plan, route-family probes, Proxyman
captures, browser matrix, auth/email/map-slot probes, backup/restore drill,
storage report, security headers, failure exercises, and final audit against
the real `run.app` URL.

Do not change `docs/PHASE-1-5-STAGING-ACCEPTANCE.md` to
`APPROVED FOR CONTROLLED PRIVATE BETA` until the strict final audit returns an
approved verdict from real public GCP evidence.

## Cost Controls

Use these staging defaults:

```text
API min instances: 0
API max instances: 3
Worker pool instances: 1 while testing, 0 when idle
Cloud SQL: smallest single-zone shared-core PostgreSQL shape available
Storage: lifecycle-delete expired exports
Artifact Registry: delete old image tags/digests
Budget: project-scoped alerts before Cloud SQL is created
Region: us-east1 for every resource
```


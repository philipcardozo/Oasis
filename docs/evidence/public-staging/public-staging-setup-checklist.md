# Public Staging Setup Checklist

Captured: 2026-08-02T07:56:11Z
Branch: `deploy/gcp-staging`
Commit: `e5e75b9d979d3a1352b622eb49498e0f53aad00f`
Provider: `gcp`
Verdict: **operator_setup_required**

This generated checklist is not public-staging proof and contains no secret values.

## GitHub Staging Environment

Required variable:

- `OASIS_DEPLOY_PROVIDER`
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCP_ARTIFACT_REPOSITORY`
- `GCP_CLOUD_RUN_SERVICE`
- `GCP_CLOUD_RUN_WORKER_POOL`
- `GCP_CLOUD_SQL_INSTANCE`
- `GCP_STORAGE_BUCKET`
- `STAGING_URL`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOY_SERVICE_ACCOUNT`

Required secrets:


Secret-free command skeletons:

```bash
gh variable set STAGING_URL --env staging --body "https://<generated-run-app-url>"
```
```bash
gh variable set OASIS_DEPLOY_PROVIDER --env staging --body "<oasis_deploy_provider>"
```
```bash
gh variable set GCP_PROJECT_ID --env staging --body "<gcp_project_id>"
```
```bash
gh variable set GCP_REGION --env staging --body "<gcp_region>"
```
```bash
gh variable set GCP_ARTIFACT_REPOSITORY --env staging --body "<gcp_artifact_repository>"
```
```bash
gh variable set GCP_CLOUD_RUN_SERVICE --env staging --body "<gcp_cloud_run_service>"
```
```bash
gh variable set GCP_CLOUD_RUN_WORKER_POOL --env staging --body "<gcp_cloud_run_worker_pool>"
```
```bash
gh variable set GCP_CLOUD_SQL_INSTANCE --env staging --body "<gcp_cloud_sql_instance>"
```
```bash
gh variable set GCP_STORAGE_BUCKET --env staging --body "<gcp_storage_bucket>"
```
```bash
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --env staging --body "<gcp_workload_identity_provider>"
```
```bash
gh variable set GCP_DEPLOY_SERVICE_ACCOUNT --env staging --body "<gcp_deploy_service_account>"
```

Manual requirements:

- Run python3 scripts/public_staging_github_environment.py to enforce required reviewer and main branch deployment policy.
- Keep production deployment absent from this workflow.

## GCP

- Use project-scoped staging resources in us-east1.
- Create Artifact Registry repository oasis in us-east1.
- Create Cloud SQL PostgreSQL instance oasis-staging-postgres in us-east1.
- Create Secret Manager secrets for OASIS_SESSION_SECRET, DATABASE_URL, and SMTP credentials.
- Create Cloud Storage bucket for exports and mount it into Cloud Run at /app/outputs.
- Deploy Cloud Run service oasis-staging with min=0 and max=3.
- Deploy Cloud Run worker pool oasis-staging-worker with instances=1 while testing and 0 when idle.
- Run migrations through a Cloud Run Job using python -m alembic upgrade head.
- Use Workload Identity Federation for GitHub Actions; do not create a JSON service-account key.

## Tester Requirements

- Create dedicated tester A, tester B, and lifecycle account email inboxes.
- Set OASIS_PUBLIC_TESTER_A_EMAIL, OASIS_PUBLIC_TESTER_A_PASSWORD, and OASIS_PUBLIC_TESTER_A_RESET_PASSWORD outside Git.
- Set OASIS_PUBLIC_TESTER_B_EMAIL and OASIS_PUBLIC_TESTER_B_PASSWORD outside Git.
- Set OASIS_PUBLIC_LIFECYCLE_EMAIL, OASIS_PUBLIC_LIFECYCLE_PASSWORD, and OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD outside Git.
- Record only verification/reset tokens in environment variables during probes.
- Run python3 scripts/public_staging_browser_matrix_template.py --base-url="$STAGING_URL" before manual browser verification.
- Use installed Chrome, Firefox, and Safari apps to complete the manual browser matrix after STAGING_URL is live.

## Verification Order

- python3 scripts/public_staging_config_contract.py
- python3 scripts/public_staging_readiness.py
- gh workflow run "Deploy GCP" --ref deploy/gcp-staging -f target=staging
- python3 scripts/public_staging_full_verification.py --base-url="$STAGING_URL" --dry-run
- python3 scripts/public_staging_smoke.py --base-url="$STAGING_URL"
- python3 scripts/public_staging_preflight.py --base-url="$STAGING_URL"
- python3 scripts/public_staging_playwright_report.py --base-url="$STAGING_URL"
- python3 scripts/public_staging_full_verification.py --base-url="$STAGING_URL" --proxy-server=http://127.0.0.1:9090
- Run public browser, auth, route, performance, infra, ops, storage, email, licensing, and failure report generators from docs/PUBLIC-STAGING-RUNBOOK.md.
- python3 scripts/public_staging_gate_audit.py

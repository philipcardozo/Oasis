# Public Staging Runbook

## Provision

1. Create Cloudflare hostname `staging.<approved-domain>`.
2. Protect the hostname with Cloudflare Access.
3. Create Cloudflare R2 bucket for staging objects; keep it private.
4. Sync `render.yaml` in Render.
5. Fill Render environment values marked `sync: false`.
6. Create GitHub `staging` environment and required secrets/variables.
7. Create Render registry credential `ghcr-oasis` with GHCR package read access.
8. Add Render API key and API/worker service IDs as GitHub environment secrets.

Secure-mode boot should fail if email/storage values are incomplete. Before the
first deploy, verify:

- `OASIS_EMAIL_BACKEND=smtp`
- `OASIS_SMTP_HOST` is set
- `OASIS_EMAIL_FROM` is non-local
- SMTP username/password are both set when either is required
- R2/S3 bucket, endpoint, access key, and secret key are set when
  `OASIS_STORAGE_BACKEND=s3`

## Deploy

```bash
gh workflow run Deploy --ref main -f target=staging
```

The workflow:

```text
install dependencies
-> validate migrations
-> run Python tests
-> run Playwright tests
-> build/publish immutable GHCR image
-> scan image
-> deploy exact image digest to Render API
-> run API predeploy migration and revision verification
-> wait for API deploy terminal success
-> deploy exact image digest to Render worker and wait
-> run public preflight
```

Render API predeploy runs:

```bash
python -m alembic upgrade head && python -m server.migration_check --expected 29995ef61d8e
```

Copy the non-secret migration log lines and the JSON output from
`server.migration_check` into
`docs/evidence/public-staging/05-migration-version.md`. The verifier must show
`"current": ["29995ef61d8e"]` and `"ok": true`; any mismatch is a failed
release.

## Verify

```bash
export STAGING_URL=https://staging.<approved-domain>
export OASIS_CF_ACCESS_CLIENT_ID=...
export OASIS_CF_ACCESS_CLIENT_SECRET=...

python3 scripts/public_staging_preflight.py \
  --base-url="$STAGING_URL" \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET
```

Then run the Proxyman/browser capture from `docs/PERFORMANCE-PROXYMAN-RUNBOOK.md`
Prompt 8 and the public prompts appended there. After the public browser
capture, generate the performance evidence report:

```bash
python3 scripts/public_staging_performance_report.py \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --output=docs/evidence/public-staging/15-performance.md
```

Generate route-security evidence from the public route probe and auth/security
summaries:

```bash
python3 scripts/public_staging_route_security_report.py \
  --route-probe=docs/evidence/performance/25-public-route-family-probe.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --auth-security=docs/evidence/performance/27-public-auth-map-slots.json \
  --output=docs/evidence/public-staging/09-route-security.md
```

For private-beta registration, set `OASIS_REGISTRATION_ALLOWED_EMAILS` to the
comma-separated tester list before inviting users. Denied registrations return
the same generic response and do not create users or send verification email.

Before any final verdict, run:

```bash
python3 scripts/public_staging_gate_audit.py
```

The script writes `docs/evidence/public-staging/99-public-staging-gate-audit.*`
and returns non-zero until every required evidence item is present and clean.
Markdown evidence files must include `Verdict: pass`; placeholder,
`Verdict: investigate`, or verdict-less files are treated as weak evidence.

## Rotate Secrets

Rotate in this order:

1. Create replacement secret in provider.
2. Deploy API and worker with both old/new accepted where applicable.
3. Verify `/readyz`, login, email, storage, and worker jobs.
4. Revoke old secret.
5. Record rotation date and operator in private ops notes.

Never paste secret values into docs, commits, screenshots, or Proxyman exports.

# Public Staging Runbook

## Provision

1. Create Cloudflare hostname `staging.<approved-domain>`.
2. Protect the hostname with Cloudflare Access.
3. Create Cloudflare R2 bucket for staging objects; keep it private.
4. Sync `render.yaml` in Render.
5. Fill Render environment values marked `sync: false`.
6. Create GitHub `staging` environment and required secrets/variables.
7. Configure Render deploy hooks as GitHub environment secrets.

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
-> trigger Render API deploy
-> trigger Render worker deploy
-> run public preflight
```

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
Prompt 8 and the public prompts appended there.

## Rotate Secrets

Rotate in this order:

1. Create replacement secret in provider.
2. Deploy API and worker with both old/new accepted where applicable.
3. Verify `/readyz`, login, email, storage, and worker jobs.
4. Revoke old secret.
5. Record rotation date and operator in private ops notes.

Never paste secret values into docs, commits, screenshots, or Proxyman exports.

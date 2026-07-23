# Deployment Rollback

## Application Rollback

Render keeps previous successful deploys. Roll back API and worker to the same
previous commit/revision. Verify:

- `/healthz`
- `/readyz`
- `/version`
- login/session persistence
- map slots
- worker job recovery

## Schema Rollback

Prefer forward-compatible migrations. For a failed deploy:

- If migration did not run, roll back application only.
- If migration ran and is forward-compatible, roll back application only after
  verifying old code tolerates the new schema.
- If migration is irreversible or data-destructive, stop traffic and restore
  into a separate database first. Do not overwrite primary staging during the
  first drill.

## Failed Health Check

Render should not shift traffic to an unhealthy replacement. Capture provider
deploy status, previous revision health, and public preflight evidence.

## Command Evidence

Record rollback evidence in `docs/evidence/public-staging/13-failure-rollback.md`
without secrets or private deploy hook URLs.

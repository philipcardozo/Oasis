# Private Beta Operations

## Tester Access

- Add tester email to Cloudflare Access policy.
- Add tester email to `OASIS_REGISTRATION_ALLOWED_EMAILS` or document why the
  Cloudflare Access policy is the sole registration boundary for that drill.
- Invite/register the user inside OASIS.
- Confirm email verification link uses the staging hostname.
- Remove a tester by removing Cloudflare Access permission, revoking OASIS
  sessions, removing the email from `OASIS_REGISTRATION_ALLOWED_EMAILS`, and
  disabling/deleting the account according to the test plan.

## Account Recovery

- Password reset must be requested through the public staging URL.
- Tokens must be single-use, expiring, and absent from logs.
- Session revocation is verified through `/api/auth/sessions`.

## Service Operations

- Restart API in Render only after confirming no migration is running.
- Restart worker independently; API browsing must continue.
- Re-run migrations with `python -m alembic upgrade head` as a controlled release
  step only.
- Trigger refresh jobs only through the worker and only with bounded staging caps.

## Incident Response

- Suspected credential exposure: rotate provider secret, revoke affected sessions,
  check logs for token/cookie/header leakage, and rotate the Render API key or
  registry credential if affected.
- Elevated rate limits/auth failures: tighten Cloudflare rule, inspect OASIS
  structured logs, keep registration closed or invitation-only.
- Map provider outage: keep Standard available; do not enable unresolved providers
  just to make a demo prettier.

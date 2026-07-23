# ADR-0009: Edge access control

## Status: accepted

## Decision
Protect public staging with Cloudflare Access in front of OASIS authentication,
and keep an optional OASIS registration allowlist for private-beta tester
invites.

## Rationale
The staging hostname must not be generally usable by the public. Cloudflare
Access provides an identity-aware outer boundary while preserving the existing
OASIS account/session/CSRF flow inside the boundary.

`OASIS_REGISTRATION_ALLOWED_EMAILS` provides a second, application-level control
for tester onboarding and fallback-host protection. If set, non-allowlisted
registration attempts receive the same generic response but no user or email is
created.

Expected request path:

```text
Internet -> Cloudflare Access/WAF -> Render TLS/web service -> OASIS auth -> API authz
```

CI smoke tests may use Cloudflare Access service-token headers stored as GitHub
environment secrets. The values must never be committed or written to evidence.

Reference: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/

## Changes this if
The approved staging domain cannot use Cloudflare, or testers require VPN-only
network access.

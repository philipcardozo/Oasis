# ADR-0001: Authentication architecture

## Status: accepted (2026-07-23)

## Decision
First-party OASIS-owned accounts with email/password. No managed identity
provider (Auth0/Cognito) for the initial private beta.

## Rationale
OASIS already needs its own user/org/authorization records for map slots and
future billing. A managed IdP would still require those records plus vendor
lock-in and cost, for a single-app cookie-session product. Argon2id + opaque
sessions is well-understood and testable offline.

## Alternatives
- Managed IdP (Auth0/Cognito/Clerk): faster social/SSO, but cost + lock-in +
  still need local records. Revisit for enterprise SSO.
- JWT access tokens in JS: rejected — token theft surface, no server revocation,
  conflicts with the "no tokens in localStorage" requirement.

## Changes this if
Enterprise customers require SAML/OIDC SSO at scale, or social login becomes a
growth requirement → add OIDC alongside first-party accounts (hybrid).

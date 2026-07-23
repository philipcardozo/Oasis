# Authentication

**Architecture:** OASIS-owned first-party accounts. Email/password with
server-managed opaque sessions in secure cookies. OAuth/SSO deferred (ADR-0001).

## Passwords
- Argon2id (`argon2-cffi`), `time_cost=3, memory=64MiB, parallelism=2`.
- Unique salts (library-managed), constant-time verify.
- Rehash-on-login when parameters change (migration support).
- Never logged, never stored in plaintext, never reversibly encrypted. No
  security questions.

## Sessions
- Opaque high-entropy token (`secrets.token_urlsafe(32)`); only its SHA-256 hash
  is stored. Raw token lives solely in an `HttpOnly` cookie — **never localStorage**.
- Record: user, created, last-used, expires, revoked, truncated UA + IP prefix
  (privacy: `/24` v4, `/48` v6). Rotatable; reset/logout-all revoke.
- Cookie: `HttpOnly`, `Secure` (staging/prod), `SameSite=Lax`, `Path=/`, bounded
  `Max-Age`. No reusable tokens in URLs.

## CSRF
Double-submit token signed with the session secret. A readable `oasis_csrf`
cookie must match the `X-CSRF-Token` header on every state-changing browser
request. Enforced by the auth dependencies and the global write-guard.

## Endpoints
`/api/auth`: `register`, `verify-email`, `login`, `logout`, `logout-all`,
`sessions` (GET), `sessions/{id}` (DELETE), `password-reset/request`,
`password-reset/complete`, `password-change`, `me`, `account` (DELETE).

## Enumeration & rate limits
Register and reset return the same message whether or not the email exists.
Login/register/reset are rate-limited (10/5/10 per 60 s by default).

## Account deletion
Anonymizes the user (email rewritten, password unusable, sessions revoked);
`anonymized_at` set. Audit event recorded.

# ADR-0002: Session architecture

## Status: accepted

## Decision
Opaque, high-entropy session tokens stored only as SHA-256 hashes in the DB;
the raw token lives solely in an HttpOnly Secure SameSite=Lax cookie. Double-
submit CSRF for state-changing requests.

## Rationale
Server-side sessions are revocable (logout-all, reset, device management),
auditable, and rotatable — properties stateless JWTs lack. HttpOnly prevents
XSS token theft; hashing at rest limits DB-leak impact.

## Alternatives
- Signed stateless JWT cookies: no server revocation, harder rotation. Rejected.
- Access+refresh token pairs in JS storage: violates no-localStorage rule.

## Changes this if
Session-store read latency becomes a bottleneck at scale → move sessions to
Redis with the same opaque-hash model (not to stateless JWTs).

# Security Threat Model (Phase 1)

## Assets
User credentials & sessions, map configurations, financial/export content,
audit records, third-party API credentials, the SEC/analytical caches.

## Controls in place
| Threat | Control | Test |
|--------|---------|------|
| Credential theft / weak hashing | Argon2id, hashed session tokens, no localStorage tokens | test_phase1_auth |
| Brute force | rate limits on login/register/reset | test_phase1_security::*rate* |
| CSRF | double-submit token on all state-changing browser requests | test_phase1_authz::*csrf* |
| Cross-user access | owner-only checks; write-guard requires session | test_phase1_authz |
| XSS (stored) | angle-bracket stripping on slot name/desc; strict CSP | test_phase1_mapslots |
| XSS (reflected)/clickjacking | CSP (no wildcards, frame-ancestors none) | test_phase1_security |
| Host header / DNS rebinding | TrustedHostMiddleware allowlist | test_phase1_security |
| CORS abuse | explicit-origin credentialed CORS (never '*') | config validation |
| Path traversal (storage) | key rejection + root containment | test_phase1_security |
| SSRF via request path | Phase 0: no external fetch in request paths | test_phase0_* |
| Spreadsheet formula injection | export sanitization (see note) | roadmap |
| User enumeration | uniform register/reset responses | test_phase1_auth |
| Secrets in logs | redaction in observability | test_phase1_security |
| Secrets in Git | .env ignored; gitleaks in CI | ci.yml |
| Dependency compromise | pip-audit + Trivy + SBOM in CI | ci.yml |
| Insecure prod config | fail-fast on missing secrets/wildcards | test_phase1_security |

## Open items (Phase 1 exit / Phase 2)
- Spreadsheet formula-injection sanitization on exports (escape leading =,+,-,@).
- MFA, device management, org SSO (OIDC).
- Rate limiter is per-process; move to a shared store (Redis) for multi-replica.
- OTel signal wiring to a collector.
- Signed download URLs for object storage.

## Trust boundaries
Browser ⇄ API (cookie + CSRF) · API ⇄ DB (least-privilege DB user) ·
Worker ⇄ third parties (ONLY the worker; bounded, rate-limited) ·
Proxy ⇄ API (X-Forwarded-* trusted only when OASIS_TRUST_PROXY=true).

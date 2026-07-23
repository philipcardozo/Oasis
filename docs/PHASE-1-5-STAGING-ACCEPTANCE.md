# OASIS Phase 1.5 Staging Acceptance

Date: 2026-07-23

Verdict: NOT APPROVED

This report records the Phase 1.5 private-beta gate evidence gathered locally. OASIS is not yet approved for controlled private beta because the Docker Compose, PostgreSQL staging, reverse-proxy authentication, backup/restore, worker-isolation, security-boundary, observability, failure-recovery, and deployed performance gates still require a Docker-capable staging host and production-style secrets.

## 1. Commit And Merge History

Authoritative repository:

```text
/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis
```

Required safety commands were run before merge:

```text
git status --short
git branch --show-current
git log --oneline --decorate -20
git diff main...phase1/production-web --stat
```

Pre-merge state:

```text
branch: phase1/production-web
status: clean
phase branch head: d0290c039a077a3c68d73d23e54e1909d1de114a
main head before merge: 651cb90a05f29d211b73fd48b462dda0905249f3
diff main...phase1/production-web: 52 files changed, 3442 insertions, 22 deletions
```

External commit review:

```text
651cb90a05f29d211b73fd48b462dda0905249f3 More calibrations and understanding of the model
```

The commit is present in `main`, `origin/main`, and `phase1/production-web`. It adds foundational server modules: `server/config.py`, `server/db.py`, `server/models.py`, `server/security.py`, and `server/__init__.py`. Pattern scans and file inspection found no raw secrets, generated credentials, local machine paths, unrelated destructive commands, duplicated Phase 1 implementation, or obvious test/security bypasses. It is the base server/auth/data-model substrate that later Phase 1 commits build on.

Merge:

```text
git switch main
git merge --no-ff phase1/production-web -m "merge: Phase 1 production web into main"
```

Merge commit:

```text
2cd8f6a5bcb96297644c131809536d059e926b29
```

## 2. Test Results

Pre-merge:

```text
python3 -m pytest -q
109 passed, 1 skipped, 1 warning in 40.83s

npx playwright test
15 passed
```

Post-merge:

```text
python3 -m pytest -q
109 passed, 1 skipped, 1 warning in 24.40s

npx playwright test
15 passed
```

After the dark-basemap glyph normalization fix:

```text
node --check graph/js/main.js
python3 -m pytest -q test_product_shell.py
3 passed

python3 -m pytest -q
109 passed, 1 skipped, 1 warning in 24.98s

npx playwright test
15 passed
```

After route inventory reconciliation:

```text
python3 -m pytest -q test_phase1_infra.py test_phase1_security.py
23 passed

python3 -m pytest -q
111 passed, 1 skipped, 1 warning in 24.61s

npx playwright test
15 passed
```

After secure licensing feature-gate hardening:

```text
python3 -m pytest -q test_phase1_security.py test_phase1_mapslots.py
27 passed

python3 -m pytest -q
115 passed, 1 skipped, 1 warning in 26.23s

npx playwright test
15 passed
```

After observability request-log hardening:

```text
python3 -m pytest -q test_phase1_security.py
15 passed

python3 -m pytest -q
118 passed, 1 skipped, 1 warning in 58.38s

npx playwright test
15 passed
```

After composed API network-isolation evidence:

```text
python3 -m pytest -q test_phase15_worker_isolation.py
2 passed

python3 -m pytest -q test_phase15_worker_isolation.py test_phase0_launch_safety.py
18 passed

python3 -m pytest -q
120 passed, 1 skipped, 1 warning in 25.14s

npx playwright test
15 passed
```

After security rate-limit evidence:

```text
python3 -m pytest -q test_phase1_security.py
17 passed

python3 -m pytest -q
122 passed, 1 skipped, 1 warning in 25.53s

npx playwright test
15 passed
```

After safe-error response hardening:

```text
python3 -m pytest -q test_phase1_security.py
19 passed

python3 -m pytest -q
124 passed, 1 skipped, 1 warning in 25.73s

npx playwright test
15 passed
```

The direct `pytest -q` shell command was unavailable because the `pytest` console script was not on `PATH`; `python3 -m pytest -q` was used successfully.

## 3. Environment And Host

Local host evidence:

```text
OS: macOS, darwin arm64
Installed Chrome: 150.0.7871.129
Installed Brave: 150.1.92.140
Installed Safari: 26.5.2
Firefox: not found in /Applications
Docker: unavailable; `docker: command not found`
```

The configured Codex workspace `/Users/felipecardozo/Documents/Oasis` is an empty git repository. The populated OASIS repository used for this gate is `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`.

## 4. Real-Browser Map Results

Installed Google Chrome was exercised through the normal Chrome channel, not the preview browser.

Standard basemap:

```text
browser: Google Chrome 150.0.7871.129
mode: globe
activeBasemap: standard
styleLoaded: true
MapLibre canvas: visible, 1440 x 939
unpkg.com requests: none
vendored MapLibre 5.6.2 requested: yes
console errors: none
evidence: docs/evidence/phase-1-5/chrome-standard-maplibre.png
metadata: docs/evidence/phase-1-5/chrome-standard-maplibre.json
```

Dark basemap:

```text
browser: Google Chrome 150.0.7871.129
mode: globe
activeBasemap: dark
styleLoaded: true
MapLibre canvas: visible, 1440 x 939
unpkg.com requests: none
vendored MapLibre 5.6.2 requested: yes
glyph endpoint: https://fonts.openmaptiles.org/{fontstack}/{range}.pbf
unexpected console errors: none
CARTO font requests: none
evidence: docs/evidence/phase-1-5/chrome-dark-maplibre.png
metadata: docs/evidence/phase-1-5/chrome-dark-maplibre.json
```

Follow-up fix: `graph/js/main.js` now normalizes all basemap glyph URLs to the CORS-safe OpenMapTiles endpoint already used by the satellite style. `test_product_shell.py` asserts this guardrail. The previous CARTO font CORS console error is no longer observed in installed Chrome.

Satellite basemap:

```text
browser: Google Chrome 150.0.7871.129
mode: globe
activeBasemap: satellite
styleLoaded: true
MapLibre canvas: visible, 1440 x 939
unpkg.com requests: none
vendored MapLibre 5.6.2 requested: yes
verdict: satellite rendered
evidence: docs/evidence/phase-1-5/chrome-satellite-maplibre.png
metadata: docs/evidence/phase-1-5/chrome-satellite-maplibre.json
```

Not yet verified:

```text
Firefox real-browser verification
Safari/WebKit real-browser verification
Zoom/pan/bearing/pitch manual real-browser verification
Repeated switching in real Chrome beyond automated Playwright coverage
Reload persistence in real Chrome beyond automated Playwright coverage
```

## 5. Docker Compose Results

Not run. Docker is unavailable in this environment:

```text
docker: command not found
```

Blocked gates:

```text
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose logs --no-color
docker images
docker inspect
container non-root verification
PostgreSQL health verification
migration process verification inside compose
API/worker health verification inside compose
reverse-proxy route verification
image size, startup time, idle memory
secret-in-image-history/log checks
volume and writeability checks
```

## 6. PostgreSQL Migration Results

Disposable local Alembic wiring was verified with SQLite:

```text
OASIS_DATABASE_URL=sqlite:////tmp/oasis_phase15_alembic_*.db python3 -m alembic upgrade head
python3 -m alembic current
python3 -m alembic downgrade base
ALEMBIC_DISPOSABLE_OK
current revision observed: 29995ef61d8e (head)
```

This does not satisfy the PostgreSQL migration gate. A new empty staging PostgreSQL database still needs upgrade/downgrade validation, schema inspection, test account creation, map-slot creation, and corruption checks.

## 7. Authentication Results

Automated local tests passed as part of the 109-test suite, including Phase 1 auth tests. Deployed reverse-proxy authentication has not been tested.

Pending deployed checks:

```text
registration
email verification through staging email backend
login
session persistence
logout
logout all devices
password reset
password change
account deletion
session listing
session revocation
browser storage inspection
cookie flags through reverse proxy
CSRF rejection through reverse proxy
session rotation and revocation reuse checks
```

## 8. Authorization Results

Automated local tests passed as part of the 109-test suite, including Phase 1 authorization tests and `docs/AUTHORIZATION-MATRIX.md` coverage. Deployed two-user authorization has not been tested through a reverse proxy.

Pending deployed checks:

```text
User A cannot read/modify User B slots
User A cannot revoke User B sessions
unauthenticated access rejection
admin/worker-only operation rejection
all inherited map_api write routes require auth and CSRF
403/404 behavior does not leak resources
organization role checks
live route inventory matched to docs/AUTHORIZATION-MATRIX.md
```

Route inventory note:

```text
route evidence: docs/evidence/phase-1-5/route-authorization-inventory.json
development server.app route entries: 96
development route methods: 95
development static mounts: 1
staging-secure server.app route entries: 92
staging-secure route methods: 91
staging-secure static mounts: 1
duplicate method/path pairs: none
development docs routes: /openapi.json, /docs, /docs/oauth2-redirect, /redoc
staging/production docs routes: disabled
```

The earlier 100-route local inventory included duplicated FastAPI documentation routes inherited from both `map_api` and `server.app`. `server.app` now owns those routes, keeps one development copy, and disables them in staging/production. The resulting inventory still differs from the objective baseline of 79 routes because the composed Phase 1 app includes health, auth, map-slot, documentation, and static routes in addition to the core map API; the current inventory is documented and covered by focused regression tests. Deployed staging still needs route/authz verification through the reverse proxy.

## 9. Map-Slot Synchronization Results

Automated local tests passed for Phase 1 map slots. Real deployed cross-browser/device synchronization has not been tested.

Pending:

```text
new account receives exactly three slots
slot 1 default OASIS experience
slots 2 and 3 customization
logout persistence
two-browser synchronization
basemap/layer/camera/condition persistence
invalid basemap/layer rejection
stored script neutralization
409 stale update behavior
conflict recovery
import/export validation and size limits
direct fourth-slot creation rejection
```

## 10. Worker Isolation Results

Not verified in containers. Docker is unavailable.

Local composed-API isolation evidence:

```text
evidence: docs/evidence/phase-1-5/composed-api-network-isolation.json
socket attempts during composed API health/financial requests: 0
financial-fact files created during composed API health/financial requests: 0
reverse DCF with empty facts: local unavailable response
comps with empty facts: local unavailable response
DCF export with empty facts: HTTP 503 with explicit refresh guidance
```

Pending:

```text
API container makes no SEC/logo/data-refresh outbound calls
worker explicit refresh jobs
worker quotas/rate limits/retries/timeouts
failed job status
restart/idempotency behavior
container-level network logs or Proxyman/mitmproxy evidence
```

## 11. Backup And Restore Results

Not run. Requires an actual staging PostgreSQL database.

Pending:

```text
representative state creation
PostgreSQL backup
checksum and size
restore into separate empty PostgreSQL instance
login against restored DB
slot/config/authz verification
migration version verification
restore duration
```

## 12. Security Boundary Results

Local secure configuration validation:

```text
staging with missing required security values: CONFIG_FAIL_FAST_OK
reported missing/unsafe values:
  - OASIS_SESSION_SECRET must be >= 32 chars
  - OASIS_DATABASE_URL must be PostgreSQL in secure modes

staging with explicit PostgreSQL-style URL, strong session secret, explicit origins/hosts, secure cookie:
CONFIG_STAGING_OK
```

Secure provider defaults:

```text
evidence: docs/evidence/phase-1-5/secure-feature-gates.json
staging defaults: Esri satellite OFF, yfinance/Yahoo prices OFF, company logos OFF
production defaults: Esri satellite OFF, yfinance/Yahoo prices OFF, company logos OFF
disabled satellite map slots: exactly three defaults remain; slot 3 degrades to Standard Site Analysis
disabled satellite writes: HTTP 422 instead of persisting an Esri-backed basemap
```

Local rate-limit evidence:

```text
evidence: docs/evidence/phase-1-5/security-rate-limits.json
login: 10 failures then HTTP 429
registration: 5 creates then HTTP 429
password reset: 10 accepted requests then HTTP 429
report/export job creation: write limiter returns HTTP 429 with Retry-After: 60
```

Local safe-error evidence:

```text
evidence: docs/evidence/phase-1-5/safe-error-responses.json
unhandled exception response: HTTP 500 {"detail":"internal server error"}
stack trace in response: no
exception text in response: no
security headers on 500 response: yes
intentional HTTP errors preserve intended status/detail
```

Reverse-proxy security boundary tests have not been run because the compose/reverse-proxy stack could not be started.

Pending:

```text
CORS origins
Host-header rejection
CSRF rejection
HSTS
CSP
Referrer-Policy
Permissions-Policy
X-Content-Type-Options
frame restrictions
authenticated caching behavior
request-size limits
secret-free logs
open redirect/path traversal checks
spreadsheet formula injection checks
raw response headers
```

## 13. Observability Results

Not fully verified in staging. CI and code declarations exist, but no deployed log pipeline was exercised.

Local request-log and redaction evidence:

```text
evidence: docs/evidence/phase-1-5/observability-request-logs.json
staging log format: structured JSON enabled
request IDs: accepted from X-Request-ID and returned as X-Request-ID
request log fields: request_id, method, route, status_code, duration_ms
short-circuit auth failures: logged and returned with security headers
redaction: authorization, cookies, tokens, sessions, and passwords redacted in JSON formatting
```

Pending:

```text
deployed structured JSON log capture
reverse-proxy request ID propagation
route-template verification from deployed traffic
controlled error trace from browser to reverse proxy/API/DB or worker/logs
rate-limit events
worker lifecycle
export failures
cache metrics
dataset freshness
disk usage
```

## 14. Failure Recovery Results

Not run. Requires a compose or staging deployment.

Pending:

```text
database unavailable
worker unavailable
map provider unavailable
object storage unavailable
full/nearly-full storage
container restart
```

Automated Playwright tests did verify provider failure handling locally:

```text
preference survives dark provider failure: connection abort
preference survives dark provider failure: HTTP 500
preference survives dark provider failure: invalid JSON
failure shows a retry affordance and does not loop forever
repeated switching keeps preference consistent
```

## 15. Performance Measurements

Automated local Playwright performance gates passed:

```text
does not request /api/universe/bulk during initial paint
loads the full universe only after search intent
cold load stays within the payload budget
reload is served from cache
```

Required deployed performance measurements are still pending:

```text
API container startup
Worker startup
Initial browser transfer
Initial request count
Session validation p50/p95
Map-slot read p50/p95
Map-slot write p50/p95
Search latency
Cold local-only comps latency
Warm comps latency
Export-job creation latency
PostgreSQL connection usage
API idle memory
Worker idle memory
Container image sizes
Backup size
Restore duration
```

Required limits are not yet proven in staging:

```text
Session validation p95 < 50 ms
Map-slot read p95 < 100 ms
Map-slot write p95 < 200 ms
Cold local-only comps < 500 ms
No /api/universe/bulk during first paint: locally passed
No external dataset downloads from API requests: not yet proven in containers
```

## 16. CI/CD Validation

`.github/workflows/ci.yml` declares:

```text
clean Python install on Python 3.11, 3.12, 3.13
compile check
Alembic upgrade/downgrade validation
pytest
Node install
Playwright install and tests
vendored MapLibre/no-CDN check
dependency audit
secret scan with gitleaks
container build
ephemeral Postgres migration in container
SBOM generation
Trivy image scan
```

`.github/workflows/deploy.yml` declares:

```text
automatic staging deploy on main push
production deploy only through workflow_dispatch target=production
production environment gate
manual rollback job
```

Not yet verified:

```text
actual GitHub check run status
protected environment configuration
registry push/deploy implementation beyond placeholder echo commands
rollback against a real previous image
```

## 17. Licensing Feature-Gate State

Existing documentation:

```text
docs/LICENSING-GATES.md
```

Secure configuration now defaults unresolved providers off in both `staging` and `production`. The local map-slot API rejects satellite selections while Esri imagery is disabled, resets disabled satellite defaults to a standard basemap, and still creates exactly three slots for new accounts. Evidence is recorded in:

```text
docs/evidence/phase-1-5/secure-feature-gates.json
```

Staging still needs deployed verification that the frontend and reverse-proxy path observe these settings without calling restricted providers.

Pending current-source licensing verification:

```text
Esri World Imagery
CARTO basemaps and tiles
Yahoo Finance/yfinance
Company logos
News feeds
Political-trading data
Property and parcel data
```

## 18. Evidence References

Generated evidence:

```text
docs/evidence/phase-1-5/chrome-standard-map.png
docs/evidence/phase-1-5/chrome-standard-map.json
docs/evidence/phase-1-5/chrome-standard-maplibre.png
docs/evidence/phase-1-5/chrome-standard-maplibre.json
docs/evidence/phase-1-5/chrome-dark-maplibre.png
docs/evidence/phase-1-5/chrome-dark-maplibre.json
docs/evidence/phase-1-5/chrome-satellite-maplibre.png
docs/evidence/phase-1-5/chrome-satellite-maplibre.json
docs/evidence/phase-1-5/route-authorization-inventory.json
docs/evidence/phase-1-5/secure-feature-gates.json
docs/evidence/phase-1-5/observability-request-logs.json
docs/evidence/phase-1-5/composed-api-network-isolation.json
docs/evidence/phase-1-5/security-rate-limits.json
docs/evidence/phase-1-5/safe-error-responses.json
```

Local command evidence recorded in this report:

```text
git safety commands
external commit inspection
pre/post merge Python tests
pre/post merge Playwright tests
secure config fail-fast checks
disposable Alembic upgrade/downgrade
installed Chrome render checks
Docker availability check
local observability request-log checks
local composed API network-isolation checks
local security rate-limit checks
local safe-error response checks
```

## 19. Remaining Risks

1. Docker is not installed in the current environment, so compose deployment, container isolation, reverse proxy, and staging PostgreSQL gates are unverified.
2. Firefox and Safari real-browser rendering are not verified.
3. Deployed authentication, authorization, map-slot synchronization, backup/restore, security headers, observability, failure recovery, and staging performance targets remain unproven.
4. Deployment workflow still contains placeholder deploy commands and needs real staging/registry integration evidence.
5. Licensing checks require current official source review before commercial launch; disabled providers do not block private beta, but deployed frontend/reverse-proxy behavior still needs explicit verification.

## 20. Final Verdict

```text
NOT APPROVED
```

OASIS has passed the Phase 1 merge, local Python tests, local Playwright tests, secure-config validation, disposable migration wiring, installed-Chrome Standard/Dark/Satellite render checks, local route-inventory reconciliation, local secure licensing feature-gate checks, local observability request-log/redaction checks, local composed API network-isolation checks, local security rate-limit checks, and local safe-error response checks. It is not approved for controlled private beta until the unverified staging-host gates are executed successfully.

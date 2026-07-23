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
evidence: docs/evidence/phase-1-5/chrome-dark-maplibre.png
metadata: docs/evidence/phase-1-5/chrome-dark-maplibre.json
```

Finding: dark basemap produced a CARTO font CORS console error:

```text
Access to fetch at 'https://tiles.basemaps.cartocdn.com/fonts/Noto%20Sans%20Bold/0-255.pbf'
from origin 'http://127.0.0.1:8788' has been blocked by CORS policy
```

The dark map rendered visually, but the Phase 1.5 "no unexpected console errors" gate is not clean until this is triaged or documented as expected provider behavior.

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
server.app assembled routes: 100
map_api routes: 72
unique server.app paths: 93
```

This differs from the objective baseline of 79 routes and must be reconciled before final approval.

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

Pending:

```text
API container makes no SEC/logo/data-refresh outbound calls
API startup creates no financial-fact files
missing facts degrade safely
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

Reverse-proxy security boundary tests have not been run because the compose/reverse-proxy stack could not be started.

Pending:

```text
CORS origins
Host-header rejection
CSRF rejection
rate limiting
HSTS
CSP
Referrer-Policy
Permissions-Policy
X-Content-Type-Options
frame restrictions
authenticated caching behavior
request-size limits
safe errors
secret-free logs
open redirect/path traversal checks
spreadsheet formula injection checks
raw response headers
```

## 13. Observability Results

Not fully verified in staging. CI and code declarations exist, but no deployed log pipeline was exercised.

Pending:

```text
structured JSON logs
request/correlation IDs
route templates
duration/status codes
auth failures
rate-limit events
worker lifecycle
export failures
cache metrics
dataset freshness
disk usage
controlled error trace from browser to logs
redaction checks
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

Secure configuration defaults unresolved providers off only in production; staging still needs explicit feature-flag confirmation before beta.

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
```

## 19. Remaining Risks

1. Docker is not installed in the current environment, so compose deployment, container isolation, reverse proxy, and staging PostgreSQL gates are unverified.
2. Dark basemap renders but emits a CARTO font CORS console error in installed Chrome.
3. Firefox and Safari real-browser rendering are not verified.
4. The route inventory differs from the objective baseline: `server.app` currently assembles 100 routes, not 79.
5. Deployed authentication, authorization, map-slot synchronization, backup/restore, security headers, observability, failure recovery, and staging performance targets remain unproven.
6. Deployment workflow still contains placeholder deploy commands and needs real staging/registry integration evidence.
7. Licensing checks require current official source review before commercial launch; disabled providers do not block private beta, but staging flag state still needs explicit verification.

## 20. Final Verdict

```text
NOT APPROVED
```

OASIS has passed the Phase 1 merge, local Python tests, local Playwright tests, secure-config validation, disposable migration wiring, and installed-Chrome Standard/Dark/Satellite render checks. It is not approved for controlled private beta until the unverified staging-host gates are executed successfully and the dark basemap console error plus route-count discrepancy are resolved or formally accepted.

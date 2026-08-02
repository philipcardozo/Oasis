# Public Staging Runbook

## Provision

1. Create Cloudflare hostname `staging.<approved-domain>`.
2. Protect the hostname with Cloudflare Access.
3. Create Cloudflare R2 bucket for staging objects; keep it private.
4. Sync `render.yaml` in Render.
5. Fill Render environment values marked `sync: false`.
6. Create GitHub `staging` environment and required secrets/variables.
7. Create Render registry credential `ghcr-oasis` with GHCR package read access.
8. Add Render API key and API/worker service IDs as GitHub environment secrets.
9. Confirm the GitHub `staging` environment has a required reviewer and a
   custom deployment branch policy for `main`, or apply it with:

   ```bash
   python3 scripts/public_staging_github_environment.py
   ```

Before dispatching a deploy, run the readiness checker. It records only
presence/absence of external configuration and never stores secret values:

```bash
python3 scripts/public_staging_setup_checklist.py
python3 scripts/public_staging_browser_matrix_template.py --base-url="$STAGING_URL"
python3 scripts/public_staging_config_contract.py
python3 scripts/public_staging_readiness.py
```

For a non-blocking status snapshot while setup is still incomplete:

```bash
python3 scripts/public_staging_readiness.py --allow-not-ready
```

All public-staging evidence that records a `base_url` must use the real
non-local HTTPS staging URL. Local loopback URLs such as `localhost`,
`127.0.0.1`, and `.local` hosts are compose/local evidence only and cannot
prove public DNS, TLS, browser, auth, email, rate-limit, storage, or failure
exercise gates.
Reserved documentation hostnames such as `staging.example.com`,
`staging.example.net`, `.test`, and `.invalid` are placeholders; the generated
readiness, preflight, full verification, smoke, Playwright, browser matrix,
auth/map-slot, infrastructure, route-security, rate-limit, email-delivery, and
object-storage reports reject them before a pass verdict. Readiness records
only sanitized STAGING_URL shape metadata, not the URL value.

The checker writes
`docs/evidence/public-staging/public-staging-readiness-status.json`. Its
`verdict` must be `ready` before the public deploy workflow can produce valid
public-staging evidence.

The setup checklist helper writes
`docs/evidence/public-staging/public-staging-setup-checklist.md` and
`docs/evidence/public-staging/public-staging-setup-checklist.json` with
placeholder `gh variable set` / `gh secret set` command skeletons, Render
environment values, Cloudflare tasks, and tester setup requirements. These
files are operator guidance only and do not count as public-staging proof.

The browser matrix template helper writes
`docs/evidence/public-staging/browser-matrix.template.json` and
`docs/evidence/public-staging/browser-matrix-template.md`. Copy the JSON
template to `docs/evidence/public-staging/browser-matrix.json` only after the
public URL is live, then replace every placeholder with real Chrome, Firefox,
Safari, Edge/Brave, and optional mobile results. The completed matrix must set
`not_public_staging_proof` to `false` and `verdict` to `pass`; leaving the
template values marks the browser matrix as weak evidence.

The config contract helper writes
`docs/evidence/public-staging/public-staging-config-contract.json` and verifies
that `render.yaml` keeps public base URL, allowed origins, trusted hosts, SMTP,
R2/S3 storage credentials, and registration allowlist values outside Git;
generates `OASIS_SESSION_SECRET`; injects PostgreSQL from managed Render
database resources; and keeps Compose API/worker/migration roles wired with the
same production-style env names. Compose public-staging env references for
base URLs, origins, trusted hosts, SMTP identity/secrets, storage backend, and
R2/S3 credentials must be supplied by the environment with no local/default
fallbacks. This is config-contract evidence, not live public-staging proof.

The GitHub Actions Deploy workflow installs the minimal deploy-gate dependency,
runs the config contract, then runs the readiness checker in environment-only
mode immediately after checkout:

```bash
python -m pip install -U pip PyYAML
python3 scripts/public_staging_config_contract.py
python3 scripts/public_staging_readiness.py --mode=github-actions
```

Those gates verify the checked-in Render/Compose contract and the `STAGING_URL`,
Render, and Cloudflare Access values injected from GitHub environment
variables/secrets before application dependency install, image build,
vulnerability scan, or Render deploy.

After the public URL exists, generate the full command plan before running
evidence collection:

```bash
python3 scripts/public_staging_full_verification.py \
  --base-url="$STAGING_URL" \
  --proxy-server=http://127.0.0.1:9090 \
  --dry-run
```

The helper writes
`docs/evidence/public-staging/public-staging-full-verification-plan.md` and
`docs/evidence/public-staging/public-staging-full-verification-run.json`. The
dry-run output is not proof; it is the literal sequence for readiness,
preflight health/readiness/version/header checks, route-family probes,
registration/email/login/map-slot security probes, Proxyman and direct browser
captures, generated reports, backup/restore evidence, storage, email,
licensing, and failure exercises. Once every manual JSON input and browser
matrix is filled from real public evidence, run the same command without
`--dry-run`; then run `python3 scripts/public_staging_gate_audit.py` as the
separate final approval check after the full verification run artifact exists.
The full verification helper rejects explicit non-HTTPS and local loopback base
URLs before writing a plan or running commands; its placeholder URL is allowed
only when no URL is supplied for a dry-run plan. Reserved documentation
hostnames such as `staging.example.com` are not valid full-verification proof.

Secure-mode boot should fail if email/storage values are incomplete. Before the
first deploy, verify:

- `OASIS_EMAIL_BACKEND=smtp`
- `OASIS_SMTP_HOST` is set
- `OASIS_EMAIL_FROM` is non-local
- SMTP username/password are both set when either is required
- R2/S3 bucket, endpoint, access key, and secret key are set when
  `OASIS_STORAGE_BACKEND=s3`

## Deploy

```bash
gh workflow run Deploy --ref main -f target=staging
```

The workflow:

```text
install deploy gate dependencies
-> validate public staging config contract
-> run public staging readiness
-> install dependencies
-> validate migrations
-> run Python tests
-> run Playwright tests
-> build/publish immutable GHCR image
-> scan image
-> deploy exact image digest to Render API
-> run API predeploy migration and revision verification
-> wait for API deploy terminal success
-> deploy exact image digest to Render worker and wait
-> run public preflight
```

After the workflow succeeds, run the first public smoke sequence. This command
checks readiness, public DNS/TLS/security headers, route-family responses, and
the strict gate audit in order. Pass `--proxy-server=http://localhost:9090` when
capturing through Proxyman:

```bash
python3 scripts/public_staging_smoke.py \
  --base-url="$STAGING_URL" \
  --expect-commit="<deployed-commit>"
```

Before the public URL exists, generate only the planned command list:

```bash
python3 scripts/public_staging_smoke.py \
  --base-url="$STAGING_URL" \
  --dry-run
```

The smoke wrapper also rejects non-HTTPS, local loopback, and reserved
documentation base URLs before it writes a plan or dispatches readiness,
preflight, route, or audit commands.

The image evidence is generated by `scripts/public_staging_image_manifest.py`.
It must show `verdict: pass`, a `ghcr.io/...@sha256:...` immutable image
reference, migration/test/scan pass checks, and SBOM/provenance present. A
mutable tag such as `latest`, a digest mismatch, or a failed CI check is not
valid deployment evidence.

The Render deploy evidence is generated by `scripts/render_deploy_image.py`.
It must show `verdict: pass`, the same digest-pinned image as
`01-image-manifest.json`, and exactly two terminal successful deployments:
`api` first, then `worker`. A missing image manifest, mutable image tag,
manifest mismatch, missing worker deploy, timeout, or failed Render terminal
status is not valid deployment evidence.

Render API predeploy runs:

```bash
python -m alembic upgrade head && python -m server.migration_check --expected 29995ef61d8e
```

Copy the non-secret migration log lines and the JSON output from
`server.migration_check` into
`docs/evidence/public-staging/infra-evidence.json`. The verifier must show
`"current_revision": ["29995ef61d8e"]`, `"migration_check_ok": true`, and
`"database_url_redacted": true`; any mismatch is a failed release.

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

The preflight script rejects non-HTTPS and local loopback base URLs before DNS,
TLS, redirect, health, readiness, version, or header probes are attempted.

Run the browser smoke suite against the public URL with no local web server.
The wrapper uses `playwright.public.config.js`, sends only Cloudflare Access
header names from environment variables, and writes sanitized evidence:

```bash
python3 scripts/public_staging_playwright_report.py \
  --base-url="$STAGING_URL" \
  --output=docs/evidence/public-staging/public-playwright-summary.json \
  --markdown-output=docs/evidence/public-staging/22-public-playwright.md
```

The summary must show `verdict: pass`, an HTTPS non-local base URL, zero
unexpected/flaky tests, and all three Playwright projects: Chromium, Firefox,
and WebKit. This does not replace the manual Chrome, Firefox, and Safari matrix;
it proves the automated Playwright rerun requested for the public URL.
The Playwright wrapper rejects explicit non-HTTPS and local loopback base URLs
before launching browsers or parsing a real JSON report; the placeholder URL is
allowed only for dry-run planning when no public URL exists. Reserved
documentation hostnames such as `staging.example.com` are not valid public
Playwright proof.

Generate deployment automation evidence from the GitHub Actions run, workflow
file, image manifest, Render deploy result, and public preflight:

```bash
python3 scripts/public_staging_deployment_report.py --print-template \
  > /tmp/oasis-deployment-automation-run.template.json

# Fill this file from the successful GitHub Actions Deploy run without secrets:
# docs/evidence/public-staging/deployment-automation-run.json

python3 scripts/public_staging_deployment_report.py \
  --run-evidence=docs/evidence/public-staging/deployment-automation-run.json \
  --image-manifest=docs/evidence/public-staging/01-image-manifest.json \
  --render-deploy=docs/evidence/public-staging/02-render-deploy.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --output=docs/evidence/public-staging/16-deployment-automation.md \
  --summary-output=docs/evidence/public-staging/deployment-automation-summary.json
```

The run evidence may include GitHub workflow names, run IDs, run attempts, step
conclusions, commit IDs, artifact names, and booleans for protected staging
environment, manual approval, secret isolation, concurrency, and no production
deploy. Do not include secrets, tokens, authorization headers, private log URLs,
or raw provider identifiers. The generated report and summary must show
`Verdict: pass`; otherwise the CI/CD and immutable deployment gate remains
unproven. The run ID and attempt must be numeric, every recorded commit must be
a full 40-character SHA, and the preflight target must be the real public HTTPS
staging hostname rather than a reserved documentation hostname such as
`staging.example.com`. The printed template is shape guidance only; copied
template run identity is a hard failure.

Generate infrastructure evidence reports from the public preflight, exact image
manifest, Render deploy evidence, and sanitized provider evidence:

```bash
python3 scripts/public_staging_infra_reports.py --print-template \
  > /tmp/oasis-infra-evidence.template.json

python3 scripts/public_staging_infra_reports.py \
  --input=docs/evidence/public-staging/infra-evidence.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --render-deploy=docs/evidence/public-staging/02-render-deploy.json \
  --image-manifest=docs/evidence/public-staging/01-image-manifest.json \
  --output-dir=docs/evidence/public-staging \
  --summary-output=docs/evidence/public-staging/infra-evidence-summary.json
```

The input JSON must contain `cloudflare_access`, `render_services`, and
`migration` sections. It may record provider names, booleans, status codes,
commit IDs, image digests, environment variable names, and redaction status, but
must not include secret values, database URLs, cookies, private token URLs, SMTP
credentials, storage credentials, or raw authorization headers. The script
writes `02-dns-tls-edge.md`, `03-cloudflare-access.md`,
`04-render-services.md`, `05-migration-version.md`, and
`infra-evidence-summary.json`; each report gets `Verdict: pass`, and the
summary validates as pass in the final audit, only when the structured evidence
proves the gate and remains secret-free. Replace template metadata such as
`replace-with-capture-time`; copied infra placeholders are hard failures.

Then run the Proxyman/browser capture from `docs/PERFORMANCE-PROXYMAN-RUNBOOK.md`
Prompt 8 and the public prompts appended there. After the public browser
capture, run the direct comparison against the same public staging URL without
`--proxy-server`; the Proxyman capture must record an explicit local proxy URL
such as `http://127.0.0.1:9090`, and the generated performance report must
include clean proxied and direct browser flow rows for first paint, reload,
search intent, map interactions, DCF workbook fetch, entity drawer,
data-quality panel, and report preview, with a retained `.har` file for every
row under `docs/evidence/performance/`. A path reference without the matching
HAR file is weak evidence in the final audit. Each row must record zero
sensitive URL query values. The Proxyman-routed capture, direct capture,
supplemental performance evidence, and any preflight/auth/route inputs consumed
by the performance report must all use the same real non-local HTTPS staging
URL. Reserved documentation hostnames are rejected before a pass verdict.
Then fill the supplemental public performance evidence file from external
location probes and provider metrics, and generate the performance evidence
report:

```bash
python3 scripts/public_staging_performance_report.py --print-supplemental-template \
  > /tmp/oasis-performance-supplemental.template.json

# Fill this file from external probes and provider metrics:
# docs/evidence/public-staging/performance-supplemental.json

python3 scripts/public_staging_performance_report.py \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --direct-summary=docs/evidence/performance/26-public-staging-direct-browser-har-summary.json \
  --auth-map-slot=docs/evidence/performance/27-public-auth-map-slots.json \
  --route-probe=docs/evidence/performance/25-public-route-family-probe.json \
  --supplemental=docs/evidence/public-staging/performance-supplemental.json \
  --output=docs/evidence/public-staging/15-performance.md \
  --summary-output=docs/evidence/public-staging/performance-evidence-summary.json
```

The supplemental file must record at least two external network locations, DNS,
TCP, TLS, TTFB, initial transferred bytes, initial request count, map
initialization timing, Web Vitals (`lcp_ms`, `inp_ms`, `cls`, `fcp_ms`,
`ttfb_ms`, `tbt_ms`), search/comps/export-job p50 and p95, API and worker CPU
and memory, database connections, queue depth, and error rate. Replace
supplemental template identities such as `replace-with-location-1` and
`replace-with-region-1`; copied placeholder probe names are hard failures. Keep
the file secret-free; do not include cookies, authorization headers, private
provider URLs, or raw telemetry links.

Before recording browser/OS versions, generate the fill-in template:

```bash
python3 scripts/public_staging_browser_matrix_template.py --base-url="$STAGING_URL"
```

After copying `docs/evidence/public-staging/browser-matrix.template.json` to
`docs/evidence/public-staging/browser-matrix.json`, generate browser and
map-provider evidence:

```bash
python3 scripts/public_staging_browser_reports.py \
  --browser-matrix=docs/evidence/public-staging/browser-matrix.json \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --browser-output=docs/evidence/public-staging/07-browser-matrix.md \
  --map-output=docs/evidence/public-staging/08-map-provider-capture.md \
  --summary-output=docs/evidence/public-staging/browser-map-summary.json
```

Both generated reports and the summary must show `Verdict: pass`; otherwise
browser compatibility, real map rendering, map-provider, and unlicensed-provider
gates remain unproven. Each available browser row must also record that no
reusable authentication token is present in `localStorage`. The browser matrix
must have `not_public_staging_proof: false` and `verdict: pass`, the browser
matrix and public HAR summary must use the same non-local HTTPS base URL, and
each network row in the summary must retain its referenced HAR file under
`docs/evidence/performance/`. Placeholder values such as `<record exact browser
version>` or `<record approved public map tile/style host>` are hard failures.
Chrome, Firefox, and Safari are required; Edge/Brave may be recorded when
available but is not a private-beta approval blocker.

Generate licensing evidence after browser/map provider evidence is present:

```bash
python3 scripts/public_staging_licensing_report.py --print-template \
  > /tmp/oasis-licensing-evidence.template.json

# Fill this file from current official source reviews without secrets:
# docs/evidence/public-staging/licensing-evidence.json

python3 scripts/public_staging_licensing_report.py \
  --input=docs/evidence/public-staging/licensing-evidence.json \
  --browser-map-summary=docs/evidence/public-staging/browser-map-summary.json \
  --output=docs/evidence/public-staging/17-licensing-gates.md \
  --summary-output=docs/evidence/public-staging/licensing-summary.json
```

The input JSON must cover Esri World Imagery, CARTO styles/tiles, Yahoo
Finance/yfinance, company logos, news sources, political-trading feeds, property
and parcel data, and other commercial datasets. Record only current official
source URLs, review dates, permission/caching/redistribution/offline-use
summaries, account/API-key requirement booleans, replacement providers, and
whether each provider is enabled in public staging. Unresolved providers may
remain unapproved for private beta only when disabled and unused in the browser
capture. The generated report and summary must show `Verdict: pass`.

Generate deployed auth, email-token, CSRF, and map-slot evidence with two
dedicated tester accounts. The first run sends registration/password-reset
emails and exits with `Verdict: investigate` until the token environment
variables are supplied:

```bash
export OASIS_PUBLIC_TESTER_A_EMAIL=...
export OASIS_PUBLIC_TESTER_A_PASSWORD=...
export OASIS_PUBLIC_TESTER_B_EMAIL=...
export OASIS_PUBLIC_TESTER_B_PASSWORD=...
export OASIS_PUBLIC_LIFECYCLE_EMAIL=...
export OASIS_PUBLIC_LIFECYCLE_PASSWORD=...
export OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD=...

python3 scripts/public_staging_auth_map_slots_probe.py \
  --base-url="$STAGING_URL" \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET
```

The auth/map-slot probe is public-only: it rejects non-HTTPS, local loopback,
and reserved documentation base URLs before registration, email-token, cookie,
map-slot, password-reset, or account-lifecycle calls are made.

After copying only the verification/reset tokens from the delivered emails into
environment variables, rerun:

```bash
export OASIS_PUBLIC_TESTER_A_VERIFY_TOKEN=...
export OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN=...
export OASIS_PUBLIC_LIFECYCLE_VERIFY_TOKEN=...
export OASIS_PUBLIC_TESTER_A_RESET_TOKEN=...
export OASIS_PUBLIC_TESTER_A_RESET_PASSWORD=...

python3 scripts/public_staging_auth_map_slots_probe.py \
  --base-url="$STAGING_URL" \
  --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
  --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET
```

The script writes
`docs/evidence/performance/27-public-auth-map-slots.json` without passwords,
tokens, cookies, authorization values, or complete email addresses.

Generate the public auth/email evidence report:

```bash
python3 scripts/public_staging_auth_email_report.py \
  --auth-map-slots=docs/evidence/performance/27-public-auth-map-slots.json \
  --output=docs/evidence/public-staging/06-auth-email.md \
  --summary-output=docs/evidence/public-staging/auth-email-summary.json
```

The report and summary must show `Verdict: pass`; otherwise email verification,
password reset, secure-cookie, SameSite/path/domain cookie attributes, session
rotation, CSRF, session listing/revocation, password change, logout-all, and
account deletion evidence remains unproven. Use the dedicated lifecycle account
for destructive account-deletion proof, not the two map-slot tester accounts.
The auth/email summary must record the same real public staging URL as the
source auth/map-slot probe; reserved documentation hostnames are rejected before
a pass verdict.
The public probe also retries used verification and password-reset tokens and
sends an unknown-account reset request; token reuse must be rejected and
known/unknown reset responses must keep the same generic shape. It also
attempts direct fourth-slot creation and `slot_number: 4` import; both attempts
must be rejected.

Generate transactional-email delivery evidence after auth, infra, and ops
summaries exist:

```bash
python3 scripts/public_staging_email_delivery_report.py --print-template \
  > /tmp/oasis-email-delivery-evidence.template.json

# Fill this file from provider settings, delivered messages, and failure probes:
# docs/evidence/public-staging/email-delivery-evidence.json

python3 scripts/public_staging_email_delivery_report.py \
  --input=docs/evidence/public-staging/email-delivery-evidence.json \
  --auth-email-summary=docs/evidence/public-staging/auth-email-summary.json \
  --infra-summary=docs/evidence/public-staging/infra-evidence-summary.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --output=docs/evidence/public-staging/20-email-delivery.md \
  --summary-output=docs/evidence/public-staging/email-delivery-summary.json
```

Record only sanitized evidence: provider name, sender-domain alias, DNS
alignment booleans, message-ID presence, public-hostname link checks,
token-redaction checks, unknown-account reset parity, and bounded retry/failure
status. Do not include full email addresses, raw message bodies with tokens,
SMTP credentials, provider account IDs, private log URLs, cookies, or
authorization headers. The generated report and summary must show
`Verdict: pass`; otherwise transactional email delivery remains unproven.
Replace template identity values such as `transactional email sandbox` and
`staging sender domain`; copied aliases are hard failures.

Generate route-security evidence from the public route probe and auth/security
summaries:

```bash
python3 scripts/public_staging_route_security_report.py \
  --route-probe=docs/evidence/performance/25-public-route-family-probe.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --auth-security=docs/evidence/performance/27-public-auth-map-slots.json \
  --output=docs/evidence/public-staging/09-route-security.md \
  --summary-output=docs/evidence/public-staging/route-security-summary.json
```

The route probe, preflight, and auth/security inputs must all record the same
real non-local HTTPS staging base URL. Local compose URLs, reserved
documentation hostnames, and mismatched hostnames fail this evidence gate even
if individual status checks pass.

Generate public proxy/rate-limit evidence:

```bash
python3 scripts/public_staging_rate_limit_report.py --print-template \
  > /tmp/oasis-rate-limit-evidence.template.json

# Fill this file from public staging probes and provider/edge logs:
# docs/evidence/public-staging/rate-limit-evidence.json

python3 scripts/public_staging_rate_limit_report.py \
  --input=docs/evidence/public-staging/rate-limit-evidence.json \
  --route-security=docs/evidence/public-staging/route-security-summary.json \
  --preflight=docs/evidence/public-staging/00-public-staging-preflight.json \
  --output=docs/evidence/public-staging/18-rate-limiting.md \
  --summary-output=docs/evidence/public-staging/rate-limit-summary.json
```

The input JSON must record the public staging API replica count, whether a
shared limiter store is used, the temporary single-replica limitation if
applicable, Cloudflare WAF/rate rules, outer access enforcement, provider log
review, trusted-proxy/client-IP handling, and route-family probes for login,
registration, password reset, search, financial models, exports, map-slot
writes, and administrative operations. The generated report and summary must
show `Verdict: pass`; otherwise rate limiting through the public proxy remains
unproven. Multiple API replicas require a shared limiter store or provider-native
equivalent. The rate-limit report rejects reserved documentation hostnames in
both the direct input and the preflight cross-check.

Generate object-storage evidence after infra and operations summaries exist:

```bash
python3 scripts/public_staging_storage_report.py --print-template \
  > /tmp/oasis-storage-evidence.template.json

# Fill this file from public staging probes and provider settings:
# docs/evidence/public-staging/storage-evidence.json

python3 scripts/public_staging_storage_report.py \
  --input=docs/evidence/public-staging/storage-evidence.json \
  --infra-summary=docs/evidence/public-staging/infra-evidence-summary.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --output=docs/evidence/public-staging/19-object-storage.md \
  --summary-output=docs/evidence/public-staging/storage-summary.json
```

The input JSON must record only sanitized provider and probe evidence: staging
bucket/namespace alias, provider name, booleans for private default access,
server-side encryption, lifecycle expiration, expiring signed authorization,
ownership checks, public-listing denial, browser credential absence,
least-privilege secret management, size limits, content-type validation, and
bounded export behavior when storage is unavailable. Do not include bucket
account IDs, raw object URLs with tokens, access keys, secret keys, cookies,
authorization headers, screenshots with credentials, or private token-bearing
URLs. The generated report and summary must show `Verdict: pass`; otherwise
object storage remains unproven even when broader infra/ops summaries pass.
The object-storage report rejects reserved documentation hostnames before a pass
verdict.

Generate operations evidence reports from structured public/provider evidence:

```bash
python3 scripts/public_staging_ops_reports.py --print-template \
  > /tmp/oasis-ops-evidence.template.json

python3 scripts/public_staging_ops_reports.py \
  --input=docs/evidence/public-staging/ops-evidence.json \
  --output-dir=docs/evidence/public-staging \
  --summary-output=docs/evidence/public-staging/ops-evidence-summary.json
```

The input JSON must contain `worker_jobs`, `network_isolation`,
`backup_restore`, `failure_rollback`, and `observability_alerts` sections. The
script writes `10-worker-jobs.md`, `11-network-isolation.md`,
`12-backup-restore.md`, `13-failure-rollback.md`, and
`14-observability-alerts.md`, plus `ops-evidence-summary.json`. Each report gets
`Verdict: pass`, and the summary validates as pass in the final audit, only when
the required structured checks are present, true, and secret-free. Replace
template values such as `replace-with-final-status`,
`replace-with-separate-restore-database-name`, and rollback revision
placeholders; copied ops template fields are hard failures. The
`failure_rollback` section must explicitly prove API restart behavior:
post-restart `/readyz` succeeds, the login/session remains valid, and all three
map slots persist after the API service restart. Otherwise persistence after
API restart remains unproven.

Generate dedicated controlled failure-exercise evidence after ops, browser/map,
object-storage, and email-delivery summaries exist:

```bash
python3 scripts/public_staging_failure_exercises_report.py --print-template \
  > /tmp/oasis-failure-exercises-evidence.template.json

# Fill this file from controlled staging failure drills:
# docs/evidence/public-staging/failure-exercises-evidence.json

python3 scripts/public_staging_failure_exercises_report.py \
  --input=docs/evidence/public-staging/failure-exercises-evidence.json \
  --ops-summary=docs/evidence/public-staging/ops-evidence-summary.json \
  --browser-map-summary=docs/evidence/public-staging/browser-map-summary.json \
  --storage-summary=docs/evidence/public-staging/storage-summary.json \
  --email-delivery-summary=docs/evidence/public-staging/email-delivery-summary.json \
  --output=docs/evidence/public-staging/21-failure-exercises.md \
  --summary-output=docs/evidence/public-staging/failure-exercises-summary.json
```

The input JSON must record sanitized results for database interruption, worker
interruption, API replacement, failed deployment, map-provider outage,
object-storage failure, and email failure. Do not include secrets, cookies,
authorization headers, provider account IDs, raw signed URLs, token-bearing
links, or private log URLs. The generated report and summary must show
`Verdict: pass`; otherwise section 23 failure exercises remain unproven even
when rollback, storage, and email summaries pass independently. The
failure-exercise input and browser/map cross-check must use the real public
HTTPS staging hostname; reserved documentation hosts such as
`staging.example.com` are hard failures.

For private-beta registration, set `OASIS_REGISTRATION_ALLOWED_EMAILS` to the
comma-separated tester list before inviting users. Denied registrations return
the same generic response and do not create users or send verification email.

Before any final verdict, run:

```bash
python3 scripts/public_staging_gate_audit.py
```

The script writes `docs/evidence/public-staging/99-public-staging-gate-audit.*`
and returns non-zero until every required evidence item is present and clean.
The JSON and Markdown audit outputs include a 22-item final-response checklist,
remaining-risk rollup, and private-beta verdict; use that checklist as the
source for the final release report instead of summarizing from memory.
Generated Markdown evidence files must include both `Verdict: pass` and the
generated-report marker emitted by the report scripts. Placeholder,
hand-written pass, `Verdict: investigate`, or verdict-less files are treated as
weak evidence. The audit also checks each generated Markdown report for its
expected title and key sections.
JSON evidence is also schema-checked: preflight, image-manifest, and Render
deploy files must prove HTTPS/DNS/TLS/header behavior, immutable GHCR digest
pinning, passing CI checks, and successful API plus worker deployments. A
hand-written `verdict: pass` is not enough. The audit also cross-checks that
public `/version` includes the tested image commit and that Render deploy
evidence records Alembic plus `server.migration_check` before the worker deploy.
Deployment automation evidence must prove the protected GitHub staging
environment, manual approval, deployment concurrency, immutable build/scan/SBOM
sequence, Render API/worker deploy, public preflight, uploaded evidence
artifact, and commit/image consistency.
Licensing evidence must prove current official-source review metadata and that
unresolved providers remain disabled and unused in the public browser/map
capture.
Rate-limit evidence must prove edge controls, trusted client-IP handling, route
family probes, and an acceptable one-replica or shared-store limiter shape.
Email-delivery evidence must prove staging/sandbox sender configuration,
sender-domain DNS alignment, delivered verification/reset messages, token
redaction, enumeration resistance, and bounded worker retry for delivery
failures.
Object-storage evidence must prove private default access, no public listing,
expiring signed authorization, ownership checks, lifecycle expiration, size and
content-type validation, and bounded export behavior when storage is
unavailable.
All public evidence is scanned for secret-like values; raw authorization
headers, token-bearing URLs, database URLs with credentials, and provider keys
make the evidence weak even when other checks pass.
The documentation criterion checks the full Phase 1.75 document and ADR set from
the objective, not only this runbook.

## Rotate Secrets

Rotate in this order:

1. Create replacement secret in provider.
2. Deploy API and worker with both old/new accepted where applicable.
3. Verify `/readyz`, login, email, storage, and worker jobs.
4. Revoke old secret.
5. Record rotation date and operator in private ops notes.

Never paste secret values into docs, commits, screenshots, or Proxyman exports.

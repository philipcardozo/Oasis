# Public Staging Full Verification Plan

Captured: 2026-07-30T07:49:07Z
Branch: `phase1.75/public-staging`
Commit: `788dc9b22bb932a6ff035d567cb67622650d4b40`
Base URL: `https://staging.example.com`
Proxyman proxy: `http://127.0.0.1:9090`
Verdict: **planned**

This file is an execution plan/run log. It is not approval proof unless the final gate audit is approved.

## Steps

### 1. Generate secret-free setup checklist

- Key: `setup_checklist`
- Manual input required: `False`
- Requires: `-`
- Produces: `docs/evidence/public-staging/public-staging-setup-checklist.md, docs/evidence/public-staging/public-staging-setup-checklist.json`

```bash
python3 scripts/public_staging_setup_checklist.py
```

### 2. Generate manual browser matrix template

- Key: `browser_matrix_template`
- Manual input required: `True`
- Requires: `-`
- Produces: `docs/evidence/public-staging/browser-matrix.template.json, docs/evidence/public-staging/browser-matrix-template.md`

```bash
python3 scripts/public_staging_browser_matrix_template.py --base-url=https://staging.example.com
```

### 3. Validate Render and Compose production-style staging value contract

- Key: `config_contract`
- Manual input required: `False`
- Requires: `render.yaml, compose.yaml`
- Produces: `docs/evidence/public-staging/public-staging-config-contract.json`

```bash
python3 scripts/public_staging_config_contract.py
```

### 4. Verify external staging prerequisites are present

- Key: `readiness`
- Manual input required: `False`
- Requires: `GitHub staging env vars/secrets, Render service IDs, Cloudflare/Access credentials, tester emails`
- Produces: `docs/evidence/public-staging/public-staging-readiness-status.json`

```bash
python3 scripts/public_staging_readiness.py
```

### 5. Check public DNS, TLS, headers, health, readiness, version

- Key: `preflight`
- Manual input required: `False`
- Requires: `STAGING_URL, Cloudflare Access service-token env vars`
- Produces: `docs/evidence/public-staging/00-public-staging-preflight.json`

```bash
python3 scripts/public_staging_preflight.py --base-url=https://staging.example.com --header=CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID --header=CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET
```

### 6. Probe public route families through the staging edge

- Key: `route_family_probe`
- Manual input required: `False`
- Requires: `public URL reachable, Cloudflare Access service-token env vars`
- Produces: `docs/evidence/performance/25-public-route-family-probe.json`

```bash
python3 scripts/compose_route_family_probe.py --base-url=https://staging.example.com --samples=3 --output-file=25-public-route-family-probe.json --verify-tls --header=CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID --header=CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET --proxy-server=http://127.0.0.1:9090
```

### 7. Exercise registration, verification, login, cookies, slots, CSRF, stale 409, cross-user denial, reset

- Key: `auth_map_slots_probe`
- Manual input required: `False`
- Requires: `tester emails/passwords and verification/reset tokens in local env`
- Produces: `docs/evidence/performance/27-public-auth-map-slots.json`

```bash
python3 scripts/public_staging_auth_map_slots_probe.py --base-url=https://staging.example.com --samples=3 --enforce-app-targets '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/27-public-auth-map-slots.json' --header=CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID --header=CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET --proxy-server=http://127.0.0.1:9090
```

### 8. Generate authentication/email evidence report

- Key: `auth_email_report`
- Manual input required: `False`
- Requires: `docs/evidence/performance/27-public-auth-map-slots.json`
- Produces: `docs/evidence/public-staging/06-auth-email.md, docs/evidence/public-staging/auth-email-summary.json`

```bash
python3 scripts/public_staging_auth_email_report.py '--auth-map-slots=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/27-public-auth-map-slots.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/06-auth-email.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/auth-email-summary.json'
```

### 9. Generate route security and security-header report

- Key: `route_security_report`
- Manual input required: `False`
- Requires: `docs/evidence/performance/25-public-route-family-probe.json, docs/evidence/public-staging/00-public-staging-preflight.json, docs/evidence/performance/27-public-auth-map-slots.json`
- Produces: `docs/evidence/public-staging/09-route-security.md, docs/evidence/public-staging/route-security-summary.json`

```bash
python3 scripts/public_staging_route_security_report.py '--route-probe=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/25-public-route-family-probe.json' '--preflight=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/00-public-staging-preflight.json' '--auth-security=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/27-public-auth-map-slots.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/09-route-security.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/route-security-summary.json'
```

### 10. Run Playwright tests against the public staging URL with Chromium, Firefox, and WebKit

- Key: `public_playwright`
- Manual input required: `False`
- Requires: `public URL reachable, Cloudflare Access service-token env vars`
- Produces: `docs/evidence/public-staging/public-playwright-summary.json, docs/evidence/public-staging/22-public-playwright.md`

```bash
python3 scripts/public_staging_playwright_report.py --base-url=https://staging.example.com '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/public-playwright-summary.json' '--markdown-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/22-public-playwright.md'
```

### 11. Capture Chrome public flows through Proxyman

- Key: `proxyman_browser_capture`
- Manual input required: `False`
- Requires: `Proxyman running, SSL proxying enabled for staging and map hosts, browser can pass Access`
- Produces: `docs/evidence/performance/26-public-staging-browser-har-summary.json`

```bash
node scripts/browser_performance_capture.js --base-url=https://staging.example.com --no-start-server=true --proxy-server=http://127.0.0.1:9090 --flow-prefix=26-public-staging --summary-file=26-public-staging-browser-har-summary.json
```

### 12. Capture direct Chrome comparison without Proxyman

- Key: `direct_browser_capture`
- Manual input required: `False`
- Requires: `public URL reachable without local proxy`
- Produces: `docs/evidence/performance/26-public-staging-direct-browser-har-summary.json`

```bash
node scripts/browser_performance_capture.js --base-url=https://staging.example.com --no-start-server=true --flow-prefix=26-public-staging-direct --summary-file=26-public-staging-direct-browser-har-summary.json
```

### 13. Generate browser matrix and map-provider reports

- Key: `browser_reports`
- Manual input required: `True`
- Requires: `filled docs/evidence/public-staging/browser-matrix.json, docs/evidence/performance/26-public-staging-browser-har-summary.json`
- Produces: `docs/evidence/public-staging/07-browser-matrix.md, docs/evidence/public-staging/08-map-provider-capture.md, docs/evidence/public-staging/browser-map-summary.json`

```bash
python3 scripts/public_staging_browser_reports.py '--browser-matrix=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/browser-matrix.json' '--browser-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/26-public-staging-browser-har-summary.json' '--browser-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/07-browser-matrix.md' '--map-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/08-map-provider-capture.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/browser-map-summary.json'
```

### 14. Generate public performance evidence report

- Key: `performance_report`
- Manual input required: `True`
- Requires: `filled performance-supplemental.json, Proxyman and direct HAR summaries`
- Produces: `docs/evidence/public-staging/15-performance.md, docs/evidence/public-staging/performance-evidence-summary.json`

```bash
python3 scripts/public_staging_performance_report.py '--browser-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/26-public-staging-browser-har-summary.json' '--direct-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/26-public-staging-direct-browser-har-summary.json' '--auth-map-slot=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/27-public-auth-map-slots.json' '--route-probe=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/performance/25-public-route-family-probe.json' '--supplemental=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/performance-supplemental.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/15-performance.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/performance-evidence-summary.json'
```

### 15. Generate DNS/TLS/Access/Render/migration reports

- Key: `infra_reports`
- Manual input required: `True`
- Requires: `filled infra-evidence.json, Render deploy and image manifest evidence`
- Produces: `docs/evidence/public-staging/02-dns-tls-edge.md, docs/evidence/public-staging/03-cloudflare-access.md, docs/evidence/public-staging/04-render-services.md, docs/evidence/public-staging/05-migration-version.md, docs/evidence/public-staging/infra-evidence-summary.json`

```bash
python3 scripts/public_staging_infra_reports.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/infra-evidence.json' '--preflight=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/00-public-staging-preflight.json' '--render-deploy=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/02-render-deploy.json' '--image-manifest=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/01-image-manifest.json' '--output-dir=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/infra-evidence-summary.json'
```

### 16. Generate backup/restore, rollback, worker, and observability reports

- Key: `ops_reports`
- Manual input required: `True`
- Requires: `filled ops-evidence.json from provider drills`
- Produces: `docs/evidence/public-staging/10-worker-jobs.md, docs/evidence/public-staging/12-backup-restore.md, docs/evidence/public-staging/13-failure-rollback.md, docs/evidence/public-staging/14-observability-alerts.md, docs/evidence/public-staging/ops-evidence-summary.json`

```bash
python3 scripts/public_staging_ops_reports.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/ops-evidence.json' '--output-dir=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/ops-evidence-summary.json'
```

### 17. Generate transactional email delivery report

- Key: `email_delivery_report`
- Manual input required: `True`
- Requires: `filled email-delivery-evidence.json`
- Produces: `docs/evidence/public-staging/20-email-delivery.md, docs/evidence/public-staging/email-delivery-summary.json`

```bash
python3 scripts/public_staging_email_delivery_report.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/email-delivery-evidence.json' '--auth-email-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/auth-email-summary.json' '--infra-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/infra-evidence-summary.json' '--ops-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/ops-evidence-summary.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/20-email-delivery.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/email-delivery-summary.json'
```

### 18. Generate public proxy/rate-limit report

- Key: `rate_limit_report`
- Manual input required: `True`
- Requires: `filled rate-limit-evidence.json`
- Produces: `docs/evidence/public-staging/18-rate-limiting.md, docs/evidence/public-staging/rate-limit-summary.json`

```bash
python3 scripts/public_staging_rate_limit_report.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/rate-limit-evidence.json' '--route-security=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/route-security-summary.json' '--preflight=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/00-public-staging-preflight.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/18-rate-limiting.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/rate-limit-summary.json'
```

### 19. Generate object-storage report

- Key: `storage_report`
- Manual input required: `True`
- Requires: `filled storage-evidence.json`
- Produces: `docs/evidence/public-staging/19-object-storage.md, docs/evidence/public-staging/storage-summary.json`

```bash
python3 scripts/public_staging_storage_report.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/storage-evidence.json' '--infra-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/infra-evidence-summary.json' '--ops-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/ops-evidence-summary.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/19-object-storage.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/storage-summary.json'
```

### 20. Generate licensing report

- Key: `licensing_report`
- Manual input required: `True`
- Requires: `filled licensing-evidence.json, browser-map-summary.json`
- Produces: `docs/evidence/public-staging/17-licensing-gates.md, docs/evidence/public-staging/licensing-summary.json`

```bash
python3 scripts/public_staging_licensing_report.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/licensing-evidence.json' '--browser-map-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/browser-map-summary.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/17-licensing-gates.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/licensing-summary.json'
```

### 21. Generate failure-exercise report

- Key: `failure_exercises_report`
- Manual input required: `True`
- Requires: `filled failure-exercises-evidence.json`
- Produces: `docs/evidence/public-staging/21-failure-exercises.md, docs/evidence/public-staging/failure-exercises-summary.json`

```bash
python3 scripts/public_staging_failure_exercises_report.py '--input=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/failure-exercises-evidence.json' '--ops-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/ops-evidence-summary.json' '--browser-map-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/browser-map-summary.json' '--storage-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/storage-summary.json' '--email-delivery-summary=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/email-delivery-summary.json' '--output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/21-failure-exercises.md' '--summary-output=/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis/docs/evidence/public-staging/failure-exercises-summary.json'
```

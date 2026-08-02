# Public Staging Browser Matrix Template

Captured: 2026-07-30T07:49:07Z
Branch: `phase1.75/public-staging`
Commit: `788dc9b22bb932a6ff035d567cb67622650d4b40`
Base URL: `https://staging.example.com`
Verdict: **operator_input_required**

This generated file is operator guidance only. It is not public-staging proof.

## Instructions

- Copy this template to docs/evidence/public-staging/browser-matrix.json after the public URL is live.
- Replace every placeholder and set each passed check to true only after manual verification in that browser.
- Leave optional mobile browsers unavailable only with a concrete reason.
- Do not record cookies, tokens, Authorization headers, Cloudflare Access secrets, SMTP credentials, or provider credentials.
- Run scripts/public_staging_browser_reports.py after the filled matrix and public HAR summary are present.

## Manual Flow Order

- Open the public staging URL in Chrome, Firefox, and Safari.
- Verify registration, email verification, login, secure cookies, logout, and password reset.
- Verify Standard, Dark, and Satellite-disabled-or-failure map behavior.
- Verify exactly three map slots, persistence across reloads, stale-update 409, and cross-user denial.
- Restart the API service and verify session/data persistence.
- Review browser console and network panels for unexpected errors, failed requests, token leakage, /api/universe/bulk on first paint, and unpkg.com requests.

## Required Browser Checks

| Key | Check |
|---|---|
| `application_shell` | application shell |
| `registration_login` | registration and login |
| `session_persistence` | session persistence |
| `no_reusable_local_storage_token` | no reusable token in localStorage |
| `standard_basemap` | Standard basemap |
| `dark_basemap` | Dark basemap |
| `satellite_disabled_or_failure` | Satellite disabled/failure behavior |
| `geographic_features` | geographic features |
| `search` | search |
| `entity_selection` | entity selection |
| `drawer_rail` | drawer and rail interactions |
| `three_map_slots` | three Map Studio slots |
| `export_workflow` | export workflow |
| `password_reset` | password reset |
| `logout` | logout |
| `responsive_layout` | responsive layout |
| `keyboard_navigation` | keyboard navigation |
| `basic_accessibility` | basic accessibility |
| `no_console_errors` | no unexpected console errors |

## Browser Rows

| Browser key | Label | Optional |
|---|---|---|
| `chrome` | Google Chrome | `False` |
| `firefox` | Firefox | `False` |
| `safari_macos` | Safari on macOS | `False` |
| `edge_or_brave` | Microsoft Edge or Brave | `True` |
| `mobile_safari` | Mobile Safari | `True` |
| `chrome_android` | Chrome on Android | `True` |

After filling `docs/evidence/public-staging/browser-matrix.json`, run:

```bash
python3 scripts/public_staging_browser_reports.py \
  --browser-matrix=docs/evidence/public-staging/browser-matrix.json \
  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \
  --browser-output=docs/evidence/public-staging/07-browser-matrix.md \
  --map-output=docs/evidence/public-staging/08-map-provider-capture.md \
  --summary-output=docs/evidence/public-staging/browser-map-summary.json
```

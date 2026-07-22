# Phase 0 — Launch Safety and Runtime Hardening

**Branch:** `phase0/launch-safety` · **Base:** `4b87c73` · **Date:** 2026-07-22
Removes launch-critical runtime hazards without rewriting OASIS.

---

## 1. Verified initial state

| Check | Baseline | Confirmed |
|---|---|---|
| `pytest -q` | 39 passed, 1 skipped | ✅ |
| `npx playwright test` | 7 passed | ✅ |
| Entities (`store.load_nodes()`) | 14,627 | ✅ |
| Geographic features | 11,338 | ✅ |
| `/api/universe/bulk` decoded | 6,404,010 B (6.11 MB) | ✅ |
| MapLibre source | vendored 5.6.2 | ✅ |
| Working tree | clean | ✅ |

No discrepancies from the stated baseline.

---

## 2. Files changed

| File | Change |
|---|---|
| `dcf_export.py` | `FactsUnavailable`; `allow_network=False` default on `load_facts`/`facts_path_for_node`; logo lookup local-only; `TICKER_DOMAINS` deleted |
| `comps.py` | Propagates `FactsUnavailable`; reports `peers_skipped_uncached` |
| `reverse_dcf.py` | Structured degraded response with `facts_cached: false` |
| `map_api.py` | DCF route returns actionable 503; `RAW_DATA_ROOT` via `oasis_paths` |
| `cache_companyfacts.py` | `OUT_DIR` via `oasis_paths.facts_dir()` |
| `oasis_paths.py` | **new** — cross-platform path resolution |
| `refresh_financial_facts.py` | **new** — the only place SEC facts are downloaded |
| `graph/js/main.js` | preferred/active/fallback basemap split; generation guard; retry; lazy bulk |
| `pyproject.toml` | **new** — dependency declaration with extras |
| `requirements.txt` | Rewritten to match, `certifi`/`requests`/`ujson` declared |
| `test_phase0_launch_safety.py` | **new** — 16 Python regressions |
| `tests/phase0.spec.js` | **new** — 8 browser regressions |
| `tests/smoke.spec.js` | Updated for lazy loading; removed `test.fail()` on the fixed bug |

---

## 3. Network-isolation design

**Rule: local reads and network acquisition are different operations.**

```
request path ──► load_facts(node)                 allow_network=False (default)
                   └─ facts_path_for_node()
                        ├─ cached?  → parse and return
                        └─ missing? → raise FactsUnavailable   (never downloads)

refresh path ──► refresh_financial_facts.py       allow_network=True (explicit)
                   └─ rate limit · UA · timeout · backoff+jitter · retries
                      max-entities · max-file-size · quota · dry-run · resume
```

Network access is **not** hidden behind a generic read function — the parameter
is explicit and defaults to off, so a new caller is safe by construction.

Degraded responses are explicit, never misleading zeros:

```json
{"available": false, "reason": "no peers with locally cached SEC facts",
 "peers_skipped_uncached": 18}

{"detail": "SEC facts for CIK0001045810 are not cached locally.
            Run `python3 refresh_financial_facts.py` to acquire them."}   // HTTP 503
```

Startup warming is local-only by inheriting the same default — it warms whatever
is cached and silently does nothing for what is not.

**Logos:** local approved logo → bundled placeholder → no logo. Domain guessing
(`{ticker}.com`) and the Clearbit fetch are deleted; a guessed domain could embed
the wrong company's mark in an export.

---

## 4. Basemap fallback design

Three states, deliberately not collapsed into one destructively-updated value:

| State | Storage | Meaning |
|---|---|---|
| `productPrefs.basemap` | localStorage | **preferred** — user intent, never overwritten by a provider failure |
| `activeBasemap` | memory | what is rendered right now |
| `basemapNotice` | memory | why they differ, drives the UI notice + Retry |

A failure sets `activeBasemap = "standard"` and a notice; the preference is
untouched, so the next session or an explicit Retry attempts it again. A
monotonic `basemapGeneration` token discards stale style responses, so a slow
load that resolves after a newer selection cannot win.

---

## 5. Lazy-data-loading design

`setMode()` previously called `await loadBulk()` unconditionally, so the ~6 MB
payload was on the initial-paint path.

- **Globe** renders from the geojson layers → no bulk needed.
- **Network** renders from the core payload → no bulk needed.
- **Index/canvas** genuinely lists every entity → loads bulk on entry.
- **Search** needs the full universe → loads on the first sign of search intent
  (focus or keystroke) and re-runs the query when it lands.

---

## 6. Cross-platform path design

`oasis_paths.py` precedence: explicit argument → environment variable → config
file (`OASIS_CONFIG`) → platform app-data directory → repo-local development
fallback (only when `OASIS_DEV=1` or the repo path already exists, so existing
local caches keep working and are never relocated).

| Platform | Directory |
|---|---|
| macOS | `~/Library/Application Support/OASIS` |
| Windows | `%LOCALAPPDATA%\OASIS` |
| Linux | `$XDG_DATA_HOME/oasis` → `~/.local/share/oasis` |

`/data/raw` — a POSIX absolute path that can never exist on Windows — is gone.
Resolution never creates directories; `ensure_dir()` does that on demand and
raises an actionable error when storage is unusable.

---

## 7. Dependency declaration

`pyproject.toml` (Python ≥3.11), extras: `export` (openpyxl), `performance`
(ujson), `ingest` (requests/yfinance/pyyaml), `terrain` (rasterio/mercantile/
numpy), `dev` (pytest + **httpx**, which `starlette.testclient` requires — a gap
the clean-venv test caught), `all`.

Runtime is deliberately small: **fastapi, uvicorn, duckdb, certifi**. Serving the
app needs neither openpyxl nor ujson. `ujson` remains a true accelerator with a
stdlib fallback (verified: without it, `dcf_export.fast_json` is `json`).

Verified in a clean venv: `pip install -e .` boots the app (72 routes, 14,627
entities); `pip install -e ".[dev]"` runs **55 passed, 1 skipped**.

---

## 8. Tests added

**Python — `test_phase0_launch_safety.py` (16).** Networking is blocked at the
socket layer, so any outbound attempt fails loudly. Covers: comps/reverse-DCF/
`load_facts` local-only and degrading; startup warming local-only; no logo
download; no domain guessing or Clearbit/urlretrieve left in source; per-platform
app-data dirs; no `/data/raw`; env override; resolve-does-not-create; refresh
defaults bounded; backoff jittered and capped; ETag/304 preserved; vendored
MapLibre is the runtime source; DCF route degrades.

**Browser — `tests/phase0.spec.js` (8).** Every provider outcome is forced with
route interception, so nothing depends on CARTO/Esri being reachable: no
`/api/universe/bulk` at paint; bulk only after search intent; preference survives
abort / HTTP 500 / invalid JSON; retry affordance without a retry storm; rapid
switching (stale-response guard); no CDN request for MapLibre.

---

## 9. Before-and-after measurements

### Request-path network isolation (empty temp facts cache, never user data)

| Measurement | Before | After |
|---|---|---|
| Cold `/api/entity/CAT/comps` | **14,300 ms** | **114.7 ms** |
| SEC files downloaded during that request | **18** | **0** |
| Disk growth from that request | **+44 MB** | **0 MB** |
| Cold `/api/entity/CAT/reverse-dcf` | n/a (would fetch) | 4.4 ms |
| Cold `/api/entity/NVDA/dcf.xlsx` | would fetch | **503 in 3.1 ms**, actionable |
| Warm comps (steady state) | ~1 ms | 4–6 ms |
| Files written during server startup | risk of N | **0** (102 → 102 files, 288 → 288 MB) |

### Initial page load (clean profile)

| Measurement | Before | After |
|---|---|---|
| Cold transfer | **1,562.5 KB** | **605.0 KB** (−61%) |
| …excluding MapLibre (unavoidable for the map view) | — | **363.2 KB** |
| `/api/universe/bulk` at first paint | **yes** (958 KB / 6.11 MB decoded) | **no** |
| Main-thread parse of bulk at startup | 6.11 MB | **0** |
| `graphState().bulkLoaded` at paint | `true` | `false` |
| Entities hydrated at paint | 14,627 | 958 (core) |
| DOMContentLoaded | 471 ms | 69–290 ms |

### Suites

| Suite | Before | After |
|---|---|---|
| pytest | 39 passed, 1 skipped | **55 passed, 1 skipped** |
| Playwright | 7 passed | **15 passed** |
| Entities / features | 14,627 / 11,338 | **unchanged** |

---

## 10. Operational modes

**Offline** — no external requests. `python3 map_api.py` with no network: app
loads, models return `available:false` with a reason, map falls back to whatever
style is reachable and keeps the user's preference. Nothing downloads.

**Normal web** — user requests are local/store-backed. Provider failures never
block the interface. Data freshness comes from separately-run refresh jobs.

**Refresh** — explicitly initiated, network-enabled, bounded:

```bash
python3 refresh_financial_facts.py --dry-run          # plan only, downloads nothing
python3 refresh_financial_facts.py --max-entities 50  # bounded acquisition
python3 refresh_financial_facts.py --entities NVDA,GM --force
```

Defaults: 6 req/s, 20 s timeout, 3 retries with jittered backoff, 100 entities
max, 25 MB per file, 2 GB cache quota. Ctrl-C finishes the current file, prints a
summary, exits 130; rerunning resumes.

**Development** — `OASIS_DEV=1` prefers repo-local paths. Production defaults are
never changed implicitly.

### Environment variables

| Variable | Purpose |
|---|---|
| `OASIS_RAW_DATA_ROOT` | ingestion source data |
| `OASIS_FACTS_DIR` | SEC companyfacts cache |
| `OASIS_CONFIG` | explicit config file path |
| `OASIS_DEV` | prefer repo-local paths |
| `EIA_API_KEY`, `DATA_GOV_API_KEY`, `ARCGIS_LOCATION_API_KEY`, `TNM_ACCESS_PRODUCTS_URL` | optional pipeline sources |

### Common operations

```bash
python3 oasis_paths.py                       # show resolved data locations
du -sh graph/data/companyfacts               # inspect cache size
rm -rf graph/data/companyfacts               # clear cache (regenerable)
python3 bootstrap.py                         # offline rebuild
python3 -m pytest -q && npx playwright test  # all tests
```

---

## 11. Remaining risks

| Risk | Severity | Note |
|---|---|---|
| **Real tile rendering unverified** | Medium | The preview browser cannot initialise MapLibre at all — a dependency-free inline style never fires `style.load`. Logic, failure handling and preference persistence are covered by tests; **actual Standard/Dark/Satellite rendering must be confirmed in a real browser.** |
| No authentication | High (Phase 1) | Write endpoints remain unauthenticated; must not be deployed publicly as-is |
| Esri imagery / yfinance licensing | High (Phase 1) | Not code — both prohibit the intended commercial use |
| `build_dcf_workbook(method=...)` ignores `method` | Low | Pre-existing; the workbook cache makes a wrong `?method=dividend` sticky |
| `map_api.py` ~3,000 lines / 72 routes | Low (debt) | Extract routers in Phase 1 |
| Cache quota is advisory | Low | Enforced in the refresh script, not by a background reaper |

---

## 12. Deferred to Phase 1

Authentication and sessions · security headers / CSP / CORS allowlist · rate
limiting · packaging (Dockerfile, CI) · observability · background worker process
(the refresh script is a manual operation, not yet a scheduled worker) ·
`map_api.py` router extraction · Postgres for users/preferences · dataset
licensing decisions.

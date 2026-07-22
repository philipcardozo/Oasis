# 18 — Pre-launch hardening: kill request-path network calls, bound disk, de-fragile the basemap

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify with the Playwright suite (`npx playwright test`).

Findings below are **measured**, not theorized (2026-07-09, Playwright + HTTP timing
against `map_api.py` on :8788). Fix in order — 1 is launch-blocking.

## 1. LAUNCH BLOCKER — synchronous SEC downloads inside request handlers

`comps(entity_id, cap=12, max_attempts=18)` loops up to **18 peers**; each calls
`dcf_export.load_facts` → `cache_companyfacts.cache_one(cik)` →
`urlopen(..., timeout=30)` against data.sec.gov **inside the HTTP request**.

Measured, one cold request `GET /api/entity/CAT/comps`:

| Metric | Measured |
|---|---|
| Response time | **14.3 s** |
| companyfacts downloaded mid-request | **18** (84 → 102 files) |
| Disk growth from that single request | **+44 MB** (244 → 288 MB) |
| Usable peers returned | **1** |

Only 84 of 14,627 entities have cached facts, so this is the *normal* path, not an
edge case. Worst case is 18 × 30 s = **9 minutes** of a hung request. Risks:
user-facing timeouts, SEC rate-limit/IP ban at any concurrency, unbounded disk
(full warm ≈ 40+ GB — this box already hit ENOSPC once), and total failure offline.

Same anti-pattern, second instance: `dcf_export.py:193`
`urllib.request.urlretrieve(url, ...)` downloads a **Clearbit logo** during
`/api/entity/{id}/dcf.xlsx`, guessing `{ticker}.com` when the domain is unknown.

**Fix:**
- Make request handlers **cache-only**. Add a `fetch: bool = False` (or
  `allow_network`) parameter to `load_facts`/`facts_path_for_node`; API paths pass
  `False` and skip peers whose facts aren't local. Never `urlopen` in a handler.
- `comps` returns what it can from cached facts plus
  `{"peers_skipped_uncached": N}` so the UI can say "N peers not yet cached".
- Logos: cache-only, never guess a domain, never fetch during export.
- Warm the cache **offline**, in the pipeline: extend `cache_companyfacts.py` into a
  `refresh_companyfacts.py` step in `refresh_all.py` that fetches facts for a bounded
  set (watchlisted + top-N by degree, e.g. 500), rate-limited ≤ 8 req/s per
  `config/sources.yaml`, with a hard cap on total cache size (evict LRU beyond, say,
  2 GB). Log what it fetched/evicted.

## 2. Basemap fallback destroys the user's saved preference

`initMapGlobe` (graph/js/main.js ~L1232) catches any style-load error and does:

```js
productPrefs.basemap="standard";
saveProductPrefs();          // ← persists the overwrite
```

So one CDN hiccup on boot **permanently** discards the user's chosen basemap.
`switchBasemap` has the sibling problem: it persists the new basemap *before*
confirming the style loads, then on failure silently falls back to standard with only
a `console.warn` — the panel just shows "Standard" selected and the user is never told
why. Map Studio depends on two third-party CDNs (CARTO, Esri), so this will happen.

Reproduced once under Playwright: after choosing Dark and reloading,
`mapStudioState().basemap` came back `"standard"`.

**Fix:** render the fallback **without** rewriting the stored preference (keep
`productPrefs.basemap`, use a separate in-memory `activeBasemap`), and surface a
non-blocking notice in the Map Studio panel: "Dark unavailable — showing Standard.
Retry." The regression test already exists:
`tests/smoke.spec.js` → "saved basemap choice survives reload even if the CDN style fails".

## 3. Eager 6.25 MB bulk payload on first paint

`/api/universe/bulk` is fetched and parsed **at startup** (`graphState().bulkLoaded === true`
on first paint, 14,627 companies): 958 KB gzipped / **6.25 MB decoded**, parsed on the
main thread. Cold DCL is 471 ms locally — it will be materially worse on a real network
and mid-range hardware, and it is the single biggest cost on the critical path.

**Fix:** restore lazy loading — hydrate the ~900-node core payload first, load bulk on
the first interaction that needs it (bulk search, globe zoom-in, index mode). Keep the
existing `loadBulk()` promise guard. Success = first paint transfers < 400 KB, with
`tests/smoke.spec.js` "cold load stays within the payload budget" tightened from 3000 KB
to ~1200 KB once lazy loading lands.

## 4. Simplification / architecture (measured smells, do after 1–3)

- **`map_api.py` is 3,043 lines and 55 routes.** Split by domain into
  `routers/` (`map`, `assets`, `entity`, `political`, `events`, `reliefs`, `reports`)
  with FastAPI `APIRouter`. Mechanical, no behavior change — do it in one pass with the
  Playwright suite green before and after.
- **`graph/js/main.js` is back to 2,896 lines** (the prompt-06 split moved config/state
  out but views stayed). Extract the three view modules now that `state.js` exists:
  `globe.js`, `network.js`, `panel.js`. `handleRailAction` (177 lines) is the worst
  offender — it is a dispatch table pretending to be a function; convert it to a
  `{action: handler}` object map.
- **One JSON-load helper, not three.** `map_api._load_json_cached`,
  `dcf_export._load_facts_cached`, and `store.py`'s loaders are the same mtime-keyed
  `lru_cache` pattern three times. Collapse into `store.py` and import it.
- **`universe.json` is still written and 17 MB** while the Parquet store is canonical.
  Once the geojson builders read the store, stop writing it (finishes prompt 10).

## Acceptance checks

- `npx playwright test` → 7 passed, and add: a cold `/api/entity/<uncached>/comps`
  returns in **< 500 ms** and downloads **0** files (assert `ls graph/data/companyfacts | wc -l`
  is unchanged across the call).
- `python3 -m pytest -q` still green.
- Offline (network disabled): app loads, comps/reverse-dcf/dcf endpoints degrade with a
  clear `available:false` + reason — no hangs, no tracebacks.
- Choosing Dark, then booting with the CDN blocked, leaves the *stored* basemap `dark`
  and shows the fallback notice.
- First-paint transfer < 400 KB; `graphState().bulkLoaded === false` on first paint.
- `graph/data/companyfacts/` stays under its cap after a full `refresh_all.py`.

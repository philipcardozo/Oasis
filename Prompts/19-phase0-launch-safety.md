# 19 — Phase 0: launch safety (blockers only, no deployment work yet)

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new dependency, no framework, no rewrite.
Full context: `docs/DEPLOYMENT-BLUEPRINT.md`.

## ⚠️ GIT SAFETY — READ BEFORE TOUCHING ANYTHING

As of 2026-07-22 the tree has **uncommitted work from another session**:

```
 M data_sources.py  dcf_export.py  graph/index.html  graph/js/config.js
 M graph/js/main.js  map_api.py  political.py  store.py  test_map_intelligence_api.py
 ?? graph/Logo_Dark_BG_96.png  graph/vendor/
```

`map_api.py` alone is +1,457 lines. Rules:

1. **Do not `git checkout`, `git restore`, `git stash`, or `git reset` anything.**
2. `git status` first. If those files are still dirty, **stop and ask the owner to
   commit them**. Two of your four tasks edit `dcf_export.py` and `graph/js/main.js` —
   editing them while dirty risks destroying that work.
3. Only after they are committed, branch: `git checkout -b phase0-launch-safety`.
4. Commit **only** files you deliberately changed. Never `git add -A`.
5. Do not commit until `pytest -q` **and** `npx playwright test` both pass.

## Task 1 — Remove network calls from request paths (LAUNCH BLOCKER)

**Measured today:** `GET /api/entity/CAT/comps` → **14.3 s**, **18 SEC files
downloaded mid-request**, **+44 MB disk**, **1 usable peer**. `comps()` loops up to 18
peers; each `load_facts` → `cache_companyfacts.cache_one(cik)` →
`urlopen(timeout=30)` **inside the handler**. Worst case 18×30 s = 9 minutes.

Files: `dcf_export.py:99-117` (`load_facts`, `facts_path_for_node`),
`cache_companyfacts.py:33-47` (`cache_one`), `comps.py`, `reverse_dcf.py`, `map_api.py`.

Do:
- Add `allow_network: bool = False` to `load_facts` / `facts_path_for_node`. Default
  **False**. When facts are absent and network is disallowed, return `None` — never fetch.
- All API/model callers (`comps`, `reverse_dcf`, the dcf endpoint) pass the default.
  `comps()` skips uncached peers and returns
  `{"peers_skipped_uncached": N}` so the UI can say "N peers not yet cached".
- Only the offline pipeline passes `allow_network=True`.
- New `refresh_companyfacts.py` (wired into `refresh_all.py`): warms a **bounded** set
  (watchlisted + top-N by degree, default 500), rate-limited **≤ 8 req/s** per
  `config/sources.yaml`, retries with exponential backoff **+ jitter**, and a **hard
  cache cap (default 2 GB) with LRU eviction**. Log fetched/skipped/evicted counts.
- Endpoints degrade to `{"available": false, "reason": "..."}` — never hang, never 500.

## Task 2 — Exports must not depend on third-party network

`dcf_export.py:188-193` downloads a **Clearbit** logo during `.xlsx` export and
**guesses `{ticker}.com`** when the domain is unknown — so an export can hang on a
third party or embed the wrong company's logo.

Do: make logo lookup **cache-only** (local `Assets & Media/Logos/` only). Never guess a
domain, never fetch during export. Missing logo = no logo.

## Task 3 — Basemap failure must not destroy the user's preference

`graph/js/main.js:1232` — inside `initMapGlobe`'s catch:
```js
productPrefs.basemap="standard"; saveProductPrefs();   // ← persists the overwrite
```
One CDN hiccup permanently discards the user's choice. Reproduced **4/4**.
`switchBasemap` has the sibling bug: it persists before confirming the style loads,
then falls back with only a `console.warn`.

Do:
- Separate **preferred** (`productPrefs.basemap`, persisted) from **active** (in-memory
  `activeBasemap`). A load failure changes only `activeBasemap`.
- Show a non-blocking notice in the Map Studio panel: "Dark unavailable — showing
  Standard. Retry." with a retry action.
- The regression test already exists and is currently marked expected-failure:
  `tests/smoke.spec.js` → "saved basemap choice survives a CDN style failure".
  **Delete its `test.fail()` line** as part of this fix so it guards the behavior.

## Task 4 — Restore lazy universe loading

Runtime-verified: `/api/universe/bulk` = **6.11 MB decoded** parsed at first paint,
`graphState().bulkLoaded === true`, 14,627 nodes. `loadBulk()` is lazy by design but
called unconditionally at startup (`graph/js/main.js:2142`, `:2846`).

Do: hydrate the ~900-node core payload first; call `loadBulk()` only on the first
interaction that needs it (bulk search, globe zoom past cluster threshold, index mode).
Keep the existing promise guard. Then tighten the Playwright budget assertion from
3000 KB to **1200 KB**.

## Task 5 — Cross-platform data path

`map_api.py:54`: `RAW_DATA_ROOT = Path(os.environ.get("OASIS_RAW_DATA_ROOT", "/data/raw"))`
— a POSIX absolute default that cannot exist on Windows.

Do: default to an OS-appropriate app-data dir (`~/Library/Application Support/OASIS`,
`%LOCALAPPDATA%\OASIS`, `~/.local/share/oasis`) via a small helper in `store.py`.
`OASIS_RAW_DATA_ROOT` still overrides. Do not hardcode `/Users/...` anywhere.

## Measurements to record (before → after, in the commit message)

```bash
# cold comps: expect 14.3s / +18 files  →  <0.5s / +0 files
ls graph/data/companyfacts | wc -l
curl -s -o /dev/null -w "%{time_total}s\n" localhost:8788/api/entity/CAT/comps
ls graph/data/companyfacts | wc -l

# first-paint transfer + eager bulk (browser console)
performance.getEntriesByType('resource').reduce((s,r)=>s+r.transferSize,0)/1024
window.graphState().bulkLoaded          // expect false at first paint
```

## Acceptance criteria

- Cold `/api/entity/<uncached>/comps` **< 500 ms** and **0** files downloaded
  (`ls graph/data/companyfacts | wc -l` unchanged across the call).
- `.xlsx` export completes with **no outbound network request**.
- With the CDN blocked, stored basemap stays `dark`, UI shows the fallback notice, and
  the un-`test.fail()`ed Playwright test passes.
- `graphState().bulkLoaded === false` at first paint; first-paint transfer < 1200 KB.
- Offline (network disabled): app loads; comps/reverse-dcf/dcf return
  `available:false` with a reason; no hangs, no tracebacks.
- `python3 -m pytest -q` → 39+ passed, and `npx playwright test` → all pass.
- `companyfacts/` stays under its cap after a full `refresh_all.py`.
- `git status` shows only files you intended to change.

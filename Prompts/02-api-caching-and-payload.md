# 02 — API caching & payload fixes

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Context

- `map_api.py` (~line 50) wraps `load_static_json` in `@lru_cache(maxsize=16)`
  keyed only by path string. After `refresh_all.py` rewrites the JSON, the API
  serves stale data until restarted.
- `graph/index.html` fetches every data file with `?v=` + `Date.now()` and
  some with `cache:"no-store"` — including `universe_bulk.json` (15 MB) at
  index.html ~line 1012. Every session re-downloads ~20 MB.
- Responses are uncompressed; the universe JSONs compress ~85% with gzip.
- `universe_bulk.json` nodes carry a `research` object of SEC URLs that are
  derivable client-side from the CIK, and an `entity_model` full of empty
  strings — dead payload weight.

## Task

1. Fix cache invalidation: key the JSON cache on `(path, mtime)`. Smallest
   version: `@lru_cache` on a helper taking `(path_str, mtime)` and a thin
   wrapper that stats the file. Apply to `load_static_json` in `map_api.py`
   and to `load_node`'s universe parse in `dcf_export.py` (~line 80, which
   re-parses 17 MB per DCF export).
2. Add `GZipMiddleware` to the FastAPI app (`minimum_size=1024`). Stdlib of
   FastAPI/Starlette — no new dependency.
3. In `graph/index.html`, remove `?v=`+`Date.now()` query strings and
   `cache:"no-store"` from data fetches. FastAPI `StaticFiles` sends
   ETag/Last-Modified; the terrain-status fetch may keep `no-store` (small).
4. In `expand_us.py`, stop emitting per-node `research` URLs into the bulk
   payload (derive in JS from `cik`/ticker — there is already a
   `sec_research`-style builder; port the URL templates to one small JS
   function). Drop empty-string fields from `entity_model` in the payloads.
5. Regenerate payloads and measure before/after sizes.

## Acceptance checks

- Edit `graph/data/prices.json` by hand → hitting the API reflects the change
  without restarting `map_api.py`.
- `curl -sH 'Accept-Encoding: gzip' localhost:8788/data/universe_core.json -o /dev/null -w '%{size_download}'`
  shows compressed transfer.
- Second page load in DevTools transfers < 1 MB (304s/cache hits on data files).
- `universe_bulk.json` shrinks ≥ 20% on disk.
- UI still works: globe loads, search works, detail panel opens, DCF export
  downloads (`window.graphState()` in the console reports sane numbers).

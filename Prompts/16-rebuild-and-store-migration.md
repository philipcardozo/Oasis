# 16 — Rebuild data + finish the store migration (make the tree runnable & green)

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps (duckdb already present), verify before finishing.
**Run this before Map Studio or anything else.**

## Why this exists

The disk-full cleanup wiped every regenerable data file, and prompt 10 stopped
short of migrating readers off `universe.json`. Current reality on a clean tree:

- **Missing from disk**: `graph/data/universe.json`, `universe_core.json`,
  `universe_bulk.json`, `companies.geojson`, `securities.geojson`,
  `relationships.geojson`, `graph-index.json`. → the app loads an empty globe.
- `python3 -m pytest -q` → **12 failed** (all `FileNotFoundError: universe.json`):
  test_store, test_comps, test_reverse_dcf, test_dcf_export, test_entity_model,
  test_ids, test_map_api, test_map_geojson, test_political, test_product_shell.
- `data/store/*.parquet` **does persist** (nodes, edges, filings, prices, events,
  pol_members, pol_trades) — the store is the durable artifact; the JSON is not.

## Task

**Part A — Make a clean checkout runnable (offline-capable bootstrap).**

1. Add `bootstrap.py` (or a `--offline` path in `refresh_all.py`) that rebuilds
   the UI payloads **without** network: `expand_us.py` (writes universe.json +
   core/bulk from `graph/data/sources/*.jsonl`, which ARE committed) →
   `build_map_geojson.py` (writes the geojsons) → `build_store.py`. The
   networked refreshers (`refresh_gleif`, `refresh_sec_addresses`,
   `refresh_prices`, `refresh_filings`, `refresh_news`, `refresh_gov_contracts`,
   `refresh_politicians`, `refresh_pol_trades`) must be **skippable** — reuse
   their existing caches under `data/raw/**` if present, and no-op cleanly if a
   source is unreachable (they should already tolerate this; fix any that hard-fail).
2. Verify: after a clean bootstrap, `map_api` serves a globe **with company
   nodes** (not empty). Confirm `companies.geojson` feature count > 10,000.
3. Add a "Regenerate data" section to `README.md`: fresh clone →
   `python3 bootstrap.py` (offline core) or `python3 refresh_all.py` (full,
   networked). State that `graph/data/*.json` and `data/store/*.parquet` are
   gitignored build artifacts.

**Part B — Finish prompt 10: migrate readers off `universe.json` to the store.**

The store persists and the JSON doesn't, so this is what makes tests green on a
clean tree. Grep the readers: `grep -rln "universe.json" --include="*.py" .`

4. Add one shared loader (e.g. `store.py`: `load_nodes()`, `load_edges()`,
   `by_id()`, `aliases()`) that reads `data/store/nodes.parquet` /
   `edges.parquet` via duckdb and returns the same shapes the current code
   expects from `universe.json["nodes"]` / `["links"]`. Cache with an
   mtime-keyed `lru_cache` (same pattern already in `map_api.py`/`dcf_export.py`).
5. Point the **library/API/model** readers at it: `map_api.py`, `dcf_export.py`,
   `comps.py`, `reverse_dcf.py`, `build_events.py`, `refresh_*` where they only
   need the entity list. Keep `expand_us.py` as the WRITER of the store and the
   JSON payloads — do not make it read the store.
6. Point the **tests** at the store or a tiny committed fixture: test_ids,
   test_entity_model, test_store, test_comps, test_reverse_dcf, test_dcf_export,
   test_map_api, test_map_geojson, test_political, test_product_shell,
   test_universe_quality. Where a test needs the full universe, read the store;
   where the store may be absent in CI, `pytest.skip` with a clear message
   rather than erroring.
7. Do NOT delete `universe.json` from `expand_us.py`'s outputs yet — the UI
   still fetches the geojsons built from it, and core/bulk are the browser
   payloads. This prompt migrates *readers*, not the writer.

## Acceptance checks

- Clean state (delete `graph/data/*.json` + geojsons, keep parquet): after
  `python3 bootstrap.py`, `map_api` shows a populated globe; geojson feature
  count > 10,000.
- `python3 -m pytest -q` → **0 failed** (skips allowed only where a fixture is
  genuinely unavailable, each with a message).
- `grep -rln "universe.json" --include="*.py" .` no longer includes the API,
  model, or test readers (only the writer `expand_us.py` and the bootstrap).
- `/api/entity/NVDA/reverse-dcf`, `/comps`, `/events`, `/political` all still
  return correct data (spot-check NVDA + LMT).
- README documents the regenerate path; a teammate could clone and run.

# 10 — DuckDB + Parquet data foundation

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 05. Allowed new dependency: `duckdb` (this prompt's whole point).

## Context

- There is no database. `map_api.py` loads JSON files and does O(n) Python
  scans per request (`/api/assets/search`, listings filters, neighborhood
  walks). `db/postgis_schema.sql` exists but nothing uses it.
- `expand_us.py` builds `universe.json` (17 MB) + `universe_core.json` +
  `universe_bulk.json` — the core+bulk pair duplicates universe.json.
- Goal: Parquet as the canonical store, DuckDB as the query engine, the JSON
  payloads demoted to build artifacts. NOT a rewrite — the UI keeps eating
  the same JSON.

## Task

1. New build step (end of `expand_us.py` or a small `build_store.py` invoked
   by `refresh_all.py`): write `data/store/nodes.parquet`,
   `data/store/edges.parquet`, `data/store/prices.parquet`,
   `data/store/filings.parquet` from the built universe + caches. Flatten
   `entity_model` into columns; keep raw JSON blobs only where truly ragged.
2. Kill the duplication: `universe.json` is no longer written; core/bulk
   payloads are produced from the store (DuckDB `COPY (SELECT ...) TO ... (FORMAT JSON)`
   or keep the existing Python writer reading from the store — smallest diff
   wins). Anything else that read `universe.json` (`dcf_export.load_node`,
   `test_*` files, `map_api.universe_nodes`) reads the store or the bulk
   payload instead — grep for `universe.json` and fix every reader.
3. Rewrite the hot API paths as DuckDB queries against Parquet:
   `/api/assets/search`, `/api/listings/search`, entity lookup, and the
   1-hop neighborhood (self-join on edges). One shared read-only
   `duckdb.connect()` per process.
4. `requirements.txt` (create it — the repo has none): fastapi, uvicorn,
   openpyxl, duckdb, plus whatever `refresh_prices.py` needs (yfinance) —
   pin loosely (`>=`).
5. Do NOT add Postgres, ORM layers, or migrations. `db/postgis_schema.sql`
   moves to `docs/design/postgis_schema.sql` with a one-line note.

## Acceptance checks

- `python3 refresh_all.py` produces `data/store/*.parquet` and the UI
  payloads; the UI works unchanged.
- `grep -rn "universe.json" --include="*.py" .` returns only the store
  builder (or nothing).
- `/api/assets/search?...` returns identical results to before (capture a
  before/after diff on 3 queries) and is faster on repeat calls.
- All pytest tests pass, updated where they read universe.json.
- `python3 -c "import duckdb; print(duckdb.sql('select count(*) from \'data/store/nodes.parquet\''))"`
  matches the node count in the UI freshness banner.

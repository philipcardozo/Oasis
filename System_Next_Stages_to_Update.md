# System Next Stages to Update

Generated: 2026-06-28

## Ponytail Review: Cut Before Adding

`build_dataset.py:L1-211: delete: obsolete S&P 500 builder now superseded by expand_us.py and universe.json. Move only REL_DEFS, SECTOR_COLORS, and LINKS into one small seed-data file.`

`graph/data/sp500.json:L1: delete: stale generated graph not loaded by graph/index.html. Nothing replaces it.`

`load_neo4j.py:L1-78: yagni: Neo4j loader reads old JSONL, not the current universe.json. Rebuild when Neo4j is actually used.`

`ingest.py:L1-207: yagni: separate SEC/GLEIF pipeline writes data/nodes.jsonl and data/edges.jsonl but refresh_all never consumes them. Wire it into the active graph or archive it.`

`config/sources.yaml:L44-51: yagni: disabled Wikidata/OpenCorporates config that no script reads. Add back when code reads it.`

`expand_us.py:L34-51: shrink: rel verb arrays are unused by the UI. Keep name and color only.`

`expand_us.py:L117-168: shrink: fallback government-contract edges duplicate refresh_gov_contracts.py query knowledge. Use the query list once, generated into links.`

`graph/index.html:L196-197: shrink: node radius is computed twice. One pass after maxNodeVal is enough.`

`graph/index.html:L202-223: shrink: creates 10,450 SVG nodes even when network mode shows about 50. Render visible nodes first, render all only in index mode.`

net: -600 lines possible.

## Next Updates Missing Now

1. Make evidence real: every curated edge needs `source_url`, `as_of`, and `confidence`. No new database yet.

2. Move curated nodes and links out of Python into `data/curated_nodes.json` and `data/curated_links.json`. Keep `expand_us.py` as the builder only.

3. Fix render latency by creating SVG elements only for visible nodes and visible links in network mode.

4. Add `data/aliases.json` for simple entity resolution: ticker aliases, old names, private-company aliases, and common spellings. Use this before Splink.

5. Add SEC latest-filings cache for connected public companies only: latest 10-K, 10-Q, 8-K, accession number, filing date, and filing URL.

6. Add hover-freeze and a hard collision pass in network mode so dense clusters stay readable.

7. Move USAspending contractor queries into `data/gov_contract_queries.json`, then add more contractors by editing data, not code.

8. Add a small data freshness banner in the UI: universe date, contracts date, news date.

9. Add a one-page README with exactly three commands: refresh, serve, open.

## Updates After That

1. Add ownership/subsidiary edges from the existing SEC/GLEIF ingestion, but only for searched or connected companies.

2. Add timeline presets: Today, 2026 AI infrastructure, 2023 banking crisis, and M&A history.

3. Add graph export: current view to JSON and CSV.

4. Add saved research packs: company profile, latest filings, government contracts, recent news, and visible graph neighbors.

5. Add basic duplicate detection report: same CIK, same LEI, same normalized name. Use this before adding Splink.

6. Add Neo4j only after users need multi-hop queries that the static JSON cannot answer fast enough.

7. Add cron only after `python3 refresh_all.py` runs cleanly for several days.

8. Consider C++ never, unless profiling proves JavaScript rendering or Python refresh is the bottleneck after visible-node rendering is fixed.

## Do Not Build Yet

- No React rewrite.
- No FastAPI backend.
- No Airflow or Dagster.
- No Splink until duplicate counts are measured.
- No C++ rewrite.
- No paid data-source integration until the public-source pipeline is clean.

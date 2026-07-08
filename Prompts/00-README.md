# OASIS Maker Prompts

Ordered prompts for fresh maker sessions, derived from the 2026-07-07 full audit.
Send one file's contents per session, in numeric order unless noted.

## Order and dependencies

| # | Prompt | Depends on | Phase |
|---|--------|-----------|-------|
| 01 | Repo hygiene & git de-bloat | — | Stop the bleeding |
| 02 | API caching & payload fixes | — | Stop the bleeding |
| 03 | GLEIF identifiers (LEI join) | — | Data quality |
| 04 | SEC business-address HQ fix | 03 helps, not required | Data quality |
| 05 | Pipeline single-build & pytest | 03, 04 | Data quality |
| 06 | Frontend module split | 02 | Product shell |
| 07 | Product shell (nav, Cmd-K, drawer) | 06 | Product shell |
| 08 | Object drawers, provenance, collision | 07 | Product shell |
| 09 | Terrain: AWS Terrain Tiles switch | 01 | Product shell |
| 10 | DuckDB/Parquet data foundation | 05 | Foundation |
| 11 | Reverse DCF + graph-aware comps | 10 | Models |
| 12 | Engine, Lenses, saved workspaces | 07, 08 | Product shell |
| 13 | Political exposure — data ingest | 10 | Wedge 1 |
| 14 | Political exposure — UI | 08, 13 | Wedge 1 |
| 15 | Event pipeline v1 + daily briefing | 10, 13 | Wedge 1 |

01–05 can run in parallel sessions. 06–08 are strictly sequential.

## Rules for every session (paste applies automatically via prompt headers)

- Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`
- Ponytail: smallest working diff, stdlib/platform first, no new dependency
  unless the prompt names it, no React, no Neo4j, no new services.
- Product spec = Obsidian vault `OASIS - Industry nodes` (never read its
  `Restricted information` folder).
- Every prompt ends with acceptance checks. Do not stop until they pass.
- Commit with a descriptive message when acceptance checks pass.

## Open decisions

- **Terrain default (prompt 09):** recommendation is AWS Terrain Tiles as the
  default globe terrain with the local 3DEP pipeline retired to an
  on-demand AOI tool. Option B (self-hosted PMTiles) is documented inside
  prompt 09 if the owner rejects the AWS dependency.

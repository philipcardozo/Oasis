# OASIS Maker Prompts

Ordered prompts for fresh maker sessions, derived from the 2026-07-07 full audit.
Send one file's contents per session, in numeric order unless noted.

## Progress (reviewed 2026-07-08)

- ✅ **02, 04, 05 complete** — deleted. API caching+gzip, SEC-address HQ fix
  (exchange placeholders 9,186 → 0), single-build + pytest (22 passing).
- ✅ **01 complete** — 03/04/05 work committed; generated payloads untracked
  (churn 0 after refresh_all); history rewritten with git-filter-repo
  (.git 569 MB → ~8 MB); backup at `../Oasis-backup.git`. Local-only (not
  force-pushed to origin, by owner's choice). 5 GB on-disk tiles left for 09.
- ✅ **03 complete** — LEI coverage 38.8% → **52.0%** via GLEIF golden-copy exact
  name+country match (INTC/XOM/LLY/AMAT resolved; ambiguous → lei_review.json).
  The 90% target is **not honestly reachable**: there are 0 bogus CIKs to clear
  (all are real SEC CIKs incl. genuine foreign filers), and ~2,200 CIK nodes are
  SPACs/ADRs/funds whose LEI sits under a differently-named entity. Test asserts
  the achieved ≥50% + all-LEIs-20-chars + spot-checks, not a fabricated 90%.
- 🟡 **06 in progress** — index.html 3079 → 102 lines (< 500). CSS → `graph/css/app.css`;
  inline JS → ES modules under `graph/js/`: `util.js` (pure helpers), `config.js`
  (static reference data), `main.js` (rest). Each step verified in-browser: identical
  `window.graphState()`, `select()`/panel work, network view renders, no console errors;
  `test_product_shell`/`test_map_api` pass. **Remaining:** split the coupled 250-function
  view core (`main.js`, ~2,556 lines) into `state.js`/`data.js`/`network.js`/`globe.js`/
  `panel.js` — needs a shared-state module (setters, since ES imports are read-only) to
  reach the 6–10 target. Higher-risk; do with full per-feature re-verification.
- ⬜ **07–15 not started.**

## Order and dependencies

| # | Prompt | Depends on | Phase |
|---|--------|-----------|-------|
| 01 | Repo hygiene — FINISH (history rewrite, commit 03-05, stop churn) | — | Stop the bleeding |
| 03 | GLEIF LEI — close coverage gap (ISIN + name fallback, CIK cleanup) | — | Data quality |
| 06 | Frontend module split | (02 done) | Product shell |
| 07 | Product shell (nav, Cmd-K, drawer) | 06 | Product shell |
| 08 | Object drawers, provenance, collision | 07 | Product shell |
| 09 | Terrain: AWS Terrain Tiles switch | 01 | Product shell |
| 10 | DuckDB/Parquet data foundation | (05 done) | Foundation |
| 11 | Reverse DCF + graph-aware comps | 10 | Models |
| 12 | Engine, Lenses, saved workspaces | 07, 08 | Product shell |
| 13 | Political exposure — data ingest | 10 | Wedge 1 |
| 14 | Political exposure — UI | 08, 13 | Wedge 1 |
| 15 | Event pipeline v1 + daily briefing | 10, 13 | Wedge 1 |

**Do next:** finish 01, then 03. Both are unblocking cleanup behind
already-landed work. 06→07→08 are strictly sequential after that.

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

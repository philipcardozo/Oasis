# 13 — Political exposure wedge: data ingestion

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 10 (store) — adapt to JSON caches if run earlier. Ponytail rules apply.

## Context

Vault notes "02 - Roadmap" Stage 8 and "09 - Deterministic Models" Vertical 1
are the spec. Goal of this prompt: get the DATA in, resolved to graph
entities, with provenance. UI is prompt 14. Guardrail from the vault: show
overlap, timing, and relevance — never manufacture corruption claims.

## Sources (all free/public)

1. **Politician stock-trade disclosures**: House Clerk financial-disclosure
   PTRs and Senate eFD. Raw PDFs are painful; prefer structured mirrors and
   check licensing/attribution. Evaluate in this order and pick the ONE that
   works best: (a) the Stock Watcher datasets
   (housestockwatcher.com / senatestockwatcher.com JSON dumps) — verify they
   are still maintained; (b) Capitol Trades unofficial endpoints (scrape/ToS
   risk — avoid if messy); (c) direct Clerk/eFD XML+PDF parsing (most work,
   most durable). Document the choice and its caveats in the source config.
2. **Members + committees**: `github.com/unitedstates/congress-legislators`
   YAML (`legislators-current.yaml`, `committee-membership-current.yaml`,
   `committees-current.yaml`). Stable, well-maintained, public domain.
3. **Contracts**: already ingested via `refresh_gov_contracts.py`
   (USAspending) — reuse, don't re-fetch.
4. **Lobbying (optional if time remains)**: Senate LDA REST API
   (`lda.senate.gov/api/`) filings by client name.

## Task

1. `refresh_politicians.py`: download legislators + committee YAML → build
   Person nodes (`node_type: "person"`, `roles: ["politician"]`, chamber,
   party, state, committee ids with names). ID scheme: `POL_<bioguide_id>`
   (fits the `PVT_`/`GOV_` convention in `docs/IDS.md`).
2. `refresh_pol_trades.py`: download trade disclosures → normalize rows
   `{politician_bioguide, ticker, asset_name, tx_type, amount_range, tx_date,
   disclosure_date, source_url}`. Resolve `ticker` → node via the existing
   alias map (`graph/data/aliases.json` / canonical ids); unresolved rows go
   to a review file, never guessed.
3. Store as `data/store/pol_trades.parquet` + `pol_members.parquet` (or JSON
   caches if pre-prompt-10), plus TRADED edge candidates:
   `{from: POL_x, to: <company id>, type: "traded", as_of, source, confidence}`
   — follow the existing `edge_candidates.json` gate pattern: they render as
   a distinct overlay/candidate class, NOT auto-merged into structural edges.
4. Committee→policy-domain relevance: a small static map (committee id →
   sector groups it plausibly governs, e.g. Armed Services → defense group;
   Energy & Commerce → energy/healthcare/telecom). Hand-write it as JSON with
   a comment header saying it's editorial; ~20 rows is enough.
5. Add both scripts to `refresh_all.py`; both must be idempotent and cache
   downloads under `data/raw/political/`.

## Acceptance checks

- After a refresh: ≥ 500 politicians with committee memberships; trades table
  non-empty with ≥ 80% ticker-resolution rate (print the rate; unresolved in
  review file with reasons).
- Spot-check one known frequent filer resolves end-to-end: person node,
  ≥ 1 trade row, TRADED candidate edge pointing at a real company node, every
  row carrying `source_url` and dates.
- Idempotent: running twice produces no duplicate rows/edges.
- pytest: new `test_political.py` asserting schema of both tables, ID format,
  and no TRADED edge without source_url + dates.

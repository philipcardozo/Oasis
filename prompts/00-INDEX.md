# Prompt Queue — Index

Supervisor-authored execution queue for the relationship-graph project. Run prompts
in number order. Each prompt is self-contained: hand `0N-*.md` to an executor as-is.

Source of truth for priorities: `System_Next_Stages_to_Update.md`.

## How to use
1. Open the lowest-numbered prompt whose Status is TODO.
2. Paste its body to the executor.
3. Check it against the prompt's Acceptance criteria before marking it DONE here.
4. Move to the next number.

## Order (and roadmap mapping)
| # | Prompt | Roadmap item |
|---|--------|--------------|
| 01 | Move curated data out of Python into JSON | Next #2 + cuts (build_dataset, seed-data) |
| 02 | Backfill edge evidence (source_url, as_of, confidence) | Next #1 |
| 03 | Render only visible nodes/links (latency) | Next #3 + cut (index.html L202-223) |
| 04 | aliases.json entity resolution | Next #4 |
| 05 | gov_contract_queries.json (data-driven contractors) | Next #6 + cut (expand_us L117-168) |
| 06 | SEC latest-filings cache for connected companies | Next #5 |
| 07 | Data freshness banner | Next #7 |
| 08 | README with three commands | Next #8 |
| 09 | Housekeeping: archive unused pipeline + dead config | Cuts (ingest.py, load_neo4j.py, config) |
| 10 | Stock price cache (current + day move + 6-month change) | Feature request |
| — | **Scaling preconditions below — must pass before adding more companies** | |
| 11 | Duplicate-detection report (measure dupes) | Phase-2 gate |
| 12 | Canonical entity id strategy | Precondition: multi-exchange/global |
| 13 | Scale the renderer (index mode → Canvas) | Precondition: rendering ceiling |
| 14 | Split data payload (core vs bulk, lazy load) | Precondition: load size |
| 15 | Source intake contract (add companies by dropping data) | Precondition: lazy scaling |
| 16 | Fortune 500 roster + sourced relationship coverage | Next data expansion |
| 17 | Edge candidate review gate | Accuracy precondition for automatic relationships |

## Global guardrails (apply to EVERY prompt)
- **Ponytail.** Laziest correct solution. Reuse what exists, stdlib/native before deps,
  shortest diff. Don't add abstractions, files, or config not asked for.
- **Accuracy is the product.** Never invent a source URL, value, or date. Mark estimates
  as estimates. `validate()` already drops edges whose endpoints aren't nodes — keep that.
- **Leave one runnable check** for any non-trivial logic (an `assert` self-check or one
  `test_*.py`). No frameworks.
- **Verify before done:** `python3 expand_us.py` rebuilds `graph/data/universe.json`
  without error, then serve `graph/` and confirm no browser console errors.

## Do NOT build yet (hard stop — from the roadmap)
- No React rewrite. No FastAPI backend. No Airflow/Dagster.
- No Splink until duplicate counts are measured.
- No C++ rewrite. No paid data sources until the public pipeline is clean.

## Gate: adding more companies
Do NOT write or run "add companies" prompts until **11–15 all pass**. That sequence makes
scaling safe: 11 measures duplicates, 12 fixes identity, 13 fixes rendering, 14 fixes load
size, 15 makes new companies a drop-in data file. After 15, adding a source = a new
`graph/data/sources/*.jsonl`, not new code.

## Phase 2 backlog (NOT promptable yet — gated on a trigger)
Write prompts for these only after the trigger is met:
- Ownership/subsidiary edges (SEC/GLEIF) for searched/connected companies — after 04+06 land.
- Timeline presets (Today / 2026 AI infra / 2023 banking crisis / M&A) — after 02 evidence has dates.
- Graph export (view → JSON/CSV) — anytime after 03.
- Saved research packs — after 06.
- Splink fuzzy dedup — only after 11's measured duplicate counts justify it.
- Neo4j — only when a multi-hop query is too slow on static JSON.
- cron — only after `refresh_all` runs clean for several days.

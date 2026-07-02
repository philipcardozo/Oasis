# 08 — README with three commands

Status: DONE
Depends on: 01, 05 (so the refresh story is accurate)
Roadmap: Next Updates #8

## Goal
A one-page top-level `README.md` whose core is exactly three commands: refresh, serve, open.

## Context
- `config/sources.yaml` already lists `suggested_commands` (refresh_gov_contracts.py,
  expand_us.py, refresh_news.py). `refresh_all.py` may or may not exist — verify before
  documenting it.

## Steps
1. Verify what actually rebuilds the graph end to end. If a single `refresh_all.py` exists
   and runs clean, document that as "refresh". If not, document the real ordered commands.
2. Write `README.md`:
   - One paragraph: what this is (graph of US public companies + major private + curated
     relationships; accuracy-first; static JSON + single-file UI).
   - **Refresh:** the exact command(s) that regenerate `graph/data/*.json`.
   - **Serve:** `python3 -m http.server 8778 --directory graph`.
   - **Open:** `http://localhost:8778/index.html`.
   - One line each on data sources and the accuracy rule (cited edges only).

## Acceptance criteria
- A new person can clone, run the three commands verbatim, and see the graph.
- Every documented command actually works (run them once to confirm).

## Guardrails
- Ponytail: one file, no docs site, no badges, no contributing guide. Three commands + a
  short paragraph. Do not document features that don't exist.

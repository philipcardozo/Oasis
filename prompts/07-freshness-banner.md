# 07 — Data freshness banner

Status: DONE
Depends on: none
Roadmap: Next Updates #7

## Goal
A small UI banner showing how fresh the data is: universe date, contracts date, news date.

## Context
- `universe.json` `meta` is the natural carrier. `expand_us.py` already writes `meta`.
- News freshness can come from `news.json` (already optionally fetched by the UI) and gov
  contracts from `gov_contracts.json` if present.

## Steps
1. In `expand_us.py`, add to `meta`: `built_at` (today ISO), and pass through
   `contracts_as_of` (from gov_contracts.json meta if present).
2. UI: read `data.meta` and render a one-line, unobtrusive banner (e.g. bottom-left or in
   the existing stats card): "universe <date> · contracts <date> · news <date>".
3. News date = max item date in `news.json` if loaded, else "—".

## Acceptance criteria
- Banner shows three dates and updates when the underlying files are rebuilt.
- No layout break; banner is quiet, not a headline.

## Guardrails
- Ponytail: derive dates from existing `meta`/file contents. No new endpoint, no polling.
  A static read at load is enough.

# 06 — SEC latest-filings cache for connected companies

Status: DONE
Depends on: 03 (so the panel work targets visible companies)
Roadmap: Next Updates #5

## Goal
For connected PUBLIC companies only, cache the latest 10-K / 10-Q / 8-K with accession
number, filing date, and filing URL. Show them in the detail panel.

## Context
- `crawl_sic.py` already hits `data.sec.gov/submissions/CIK{cik}.json`, which contains the
  recent-filings table. Reuse that endpoint shape — do not invent a new client.
- Scope: only companies with `deg>0` and `kind=="public"` (tens, not 10k). Keep it small.

## Steps
1. New `refresh_filings.py`: for each connected public company, fetch submissions, extract
   the most recent 10-K, 10-Q, 8-K (form, accessionNumber, filingDate, primary-doc URL),
   write `graph/data/filings.json` keyed by ticker.
2. `expand_us.py` merges `filings.json` into each node (if present) under `node.filings`.
3. UI detail panel: render a "Latest filings" block with clickable links when present.

## Acceptance criteria
- `filings.json` exists with an entry per connected public company.
- Selecting e.g. NVDA shows latest 10-K/10-Q/8-K links that open on sec.gov.
- Companies without filings (private/gov/legacy) show no filings block, no error.

## Guardrails
- Ponytail: reuse the `crawl_sic.py` request pattern (User-Agent, ~8/sec). Connected set
  only — do NOT pull filings for all 10k.
- Accuracy: links/dates come from the API response only.

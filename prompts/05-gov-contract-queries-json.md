# 05 — gov_contract_queries.json (data-driven contractors)

Status: DONE
Depends on: 01
Roadmap: Next Updates #6; Cut item (expand_us L117-168 duplicates query knowledge)

## Goal
Adding a government contractor relationship = editing data, not Python. One query list
drives both the fallback edges and `refresh_gov_contracts.py`.

## Context
- `expand_us.py` hardcodes `GOV_CONTRACT_LINKS` (DoD/NASA/DHS → tickers). `refresh_gov_contracts.py`
  separately knows the same recipient list. That duplication is the cut target.

## Steps
1. Create `graph/data/gov_contract_queries.json`: list of
   `{ "agency_id": "GOV_US_DOD", "recipient_id": "LMT", "recipient_name": "Lockheed Martin",
      "start": "1947-09-18", "confidence": 0.95 }` (one per contractor).
2. `refresh_gov_contracts.py` reads this list to know what to query on USAspending.
3. `expand_us.py` generates the fallback `contracts` edges FROM this same file (val 0 until
   a refresh fills it), removing the hardcoded `GOV_CONTRACT_LINKS` literal.

## Acceptance criteria
- Adding a contractor = one new object in the JSON; rebuild shows the new edge. No code edit.
- `grep -n GOV_CONTRACT_LINKS expand_us.py` returns nothing.
- `python3 expand_us.py` link count unchanged for the existing contractors.

## Guardrails
- Ponytail: reuse the existing `normalize_link()` path for the generated edges. No new
  edge-builder abstraction.
- Accuracy: refreshed dollar values come only from the USAspending API response, never typed in.

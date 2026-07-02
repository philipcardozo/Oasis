# 11 — Duplicate-detection report

Status: DONE
Depends on: none
Roadmap: Phase-2 gate ("duplicate counts measured before any Splink")

## Why this is a precondition
Adding more sources multiplies duplicates (same company via ADRs, multiple exchanges,
name variants). Measure the problem before scaling, so dedup decisions are data-driven.
This is report-only — no merging, no Splink.

## Steps
1. `dedupe_report.py`: load `graph/data/universe.json` nodes and group by:
   - exact `cik` (non-empty),
   - exact `lei` (if present),
   - normalized name (lowercase, strip punctuation and suffixes: inc, corp, co, ltd,
     plc, sa, ag, nv, group, holdings, the).
2. Write `graph/data/dupes_report.json`: each collision group (key, members[]) plus
   totals: `{groups_by_name, groups_by_cik, total_dup_candidates}`.
3. Print the headline numbers.

## Acceptance criteria
- Report exists and prints total duplicate-candidate count.
- A `test_dedupe.py` asserts the normalizer collapses "Apple Inc." and "APPLE INC" but
  not "Apple Inc." and "Applied Materials".
- No node is modified or removed.

## Guardrails
- Ponytail: a normalize function + `defaultdict(list)`. No fuzzy lib, no Splink, no ML —
  that decision waits on these measured numbers.

# 16 — Fortune 500 roster + sourced relationship coverage

Status: TODO
Depends on: 15 (source intake), 11 (dedupe report), 12 (canonical ids)
Roadmap: next major company/data expansion

## Goal
Add the current Fortune 500 roster as a sourced data snapshot, then attach only
evidence-backed relationships: government contracts, material investments, suppliers,
customers, acquisitions, and public partnerships.

## Steps
1. Add a dated Fortune 500 roster snapshot with source URL and snapshot date.
   Use `graph/data/sources/fortune_500.jsonl` for missing company nodes.
2. Preserve useful Fortune fields on each node when available:
   `fortune_rank`, `revenue`, `profit`, `employees`, `website`, `source_url`,
   `source_as_of`.
3. Map every roster company to one canonical id. Use `aliases.json` for ticker/name
   variants; do not create a second node for an existing company.
4. Public companies must have CIK + SEC research links when available. Private companies
   must be marked `kind:"private"` and still get news/USAspending research links.
5. Add relationship edges only when the source supports the edge:
   - government contracts: USAspending or agency award page
   - investments/holders: 13F/Fintel/SEC source
   - partnerships/supplier/customer: filing, press release, contract, or credible report
   - acquisitions: SEC filing, company release, or cited deal source
6. Every added edge needs `source_url`, `as_of` or `start`, `confidence`, `src`, and
   a plain-English `detail`.

## Acceptance criteria
- `python3 expand_us.py` completes with all Fortune 500 canonical ids present.
- Fewer than 500 roster matches is a failure unless the missing list is written to a
  review file with reason and source.
- No canonical id collisions increase versus the pre-run `dedupe_report.py`.
- A spot check of 20 roster companies shows: rank/details, group classification, research
  links, and only sourced relationship edges.
- Browser check: searching a Fortune 500 company opens the detail window; `Self view`
  shows only that company and its sourced direct relationships.

## Guardrails
- Ponytail: one roster file, existing source intake, existing edge shape. No new database.
- Do not invent edges from vague "strategic relationship" language. If evidence is weak,
  skip the edge and leave the source in a review list.

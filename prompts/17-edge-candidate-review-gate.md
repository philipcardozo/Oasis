# 17 — Edge candidate review gate

Status: DONE
Depends on: 02 (edge evidence), 07 (freshness), 15 (source intake)
Roadmap: keep automatic relationship updates accurate without hand-maintaining every edge

## Goal
Separate possible relationship discoveries from confirmed graph edges. Refreshers can
write candidates, but `expand_us.py` only includes candidate edges after review confirms
them and evidence fields are present.

## Steps
1. Add `graph/data/edge_candidates.json` and `graph/data/rejected_edges.json`.
2. Add `refresh_edge_candidates.py` to mine cached news for possible edges between known
   companies.
3. Teach `expand_us.py` to include only candidates with `status:"confirmed"` and:
   `source_url`, `src`, `detail`, `confidence`, plus `as_of` or `start`.
4. Add the candidate refresh to `refresh_all.py`.

## Acceptance criteria
- Candidate edges are not visible in the graph until confirmed.
- Rejected edge keys are never included.
- `python3 refresh_edge_candidates.py` writes a stable JSON list.
- `python3 expand_us.py` keeps current graph counts unless a candidate is explicitly
  confirmed.

## Guardrails
- Ponytail: JSON files, one small refresher, no database, no approval workflow UI yet.

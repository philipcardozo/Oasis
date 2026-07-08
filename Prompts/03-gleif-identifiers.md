# 03 — GLEIF identifiers: close the LEI coverage gap

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Already done (do not redo)

- `refresh_gleif.py` downloads the GLEIF **CIK→LEI** relationship file and
  builds `graph/data/sources_meta/lei_map.json`.
- `expand_us.py` joins it: LEI went from **0 → 4,037** nodes. NVDA/AAPL
  resolve correctly.

## Still broken

- Coverage is **27.6% of CIK'd nodes (4,037), not the 90% target.** Major
  issuers with genuine CIKs have no LEI: INTC, XOM, LLY, ASML, AMAT, etc.
  Root cause: GLEIF's CIK→LEI relationship file only contains entities that
  self-reported the link — it tops out around a third of SEC registrants.
  The CIK join alone cannot reach 90%.
- **Bogus CIKs inflate the denominator.** All ~14,627 nodes carry a non-empty
  `cik`, including non-US batch records that should have none — so real
  coverage looks worse than it is and the quality gate can't measure honestly.

## Task

1. **Clean bogus CIKs first** (in `expand_us.py` `source_node()`): only set
   `cik` when the source record genuinely carries one (SEC-derived). Clear
   inherited/placeholder CIKs on non-US batch nodes. Print how many were
   cleared. This alone raises the measured coverage ratio.
2. **Add fallback resolution paths in `refresh_gleif.py`**, tried in order,
   for nodes still missing an LEI after the CIK join:
   - **ISIN → LEI**: download GLEIF's ISIN→LEI mapping file; join for any node
     that has an ISIN (securities especially). Cache like the CIK file.
   - **Name + jurisdiction match against the GLEIF golden copy (Level 1)**:
     download the LEI-CDF golden copy (or query the GLEIF API by exact legal
     name filtered to the node's country). Match on
     `normalized_issuer_key(name)` (already exists in `expand_us.py`) AND
     country. **Auto-accept only exact normalized-name + country matches**;
     everything ambiguous goes to `graph/data/sources_meta/lei_review.json`
     with candidates — never guessed into the graph.
3. **Report honestly** at build end (one line): nodes with genuine CIK, LEI
   via CIK / via ISIN / via name-match, unresolved, and the review-queue size.
4. Update `test_universe_quality.py`: assert LEI coverage ≥ 90% of nodes with
   a genuine CIK, and no LEI of wrong length (LEIs are 20 chars).

## Notes

- Keep it deterministic. Do NOT reach for Splink/fuzzy libraries — exact
  normalized-name + country is enough for listed issuers; the residue goes to
  review, not to a probabilistic matcher.
- The golden copy is large; download once, cache under `data/raw/gleif/`,
  refresh only when > 30 days old or `--force`. It stays gitignored (prompt 01).
- GLEIF Level 2 ownership (parent/child OWNS edges) is still out of scope —
  note as a follow-up, don't build it.

## Acceptance checks

- After `python3 refresh_gleif.py && python3 expand_us.py`: LEI coverage ≥ 90%
  of nodes with a genuine CIK; spot-check INTC, XOM, LLY, AMAT now have LEIs.
- Bogus-CIK count reported and materially reduced (non-US nodes lose fake CIKs).
- `lei_review.json` exists for genuine ambiguities; nothing ambiguous was
  auto-merged.
- `python3 -m pytest -q` passes including the tightened coverage assertion.

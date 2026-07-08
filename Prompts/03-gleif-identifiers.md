# 03 — GLEIF identifiers: LEI on every resolvable node

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Context

- The live universe (`graph/data/universe.json`, ~14,600 nodes) has **zero**
  nodes with an LEI. The GLEIF code that once existed lives dead in
  `archive/ingest.py`; `config/sources.yaml` still claims `gleif: enabled: true`.
- Do NOT resolve LEIs by name-search against the GLEIF API. GLEIF publishes
  deterministic **mapping files** (free bulk CSVs, updated regularly):
  - CIK→LEI relationship file: https://www.gleif.org/en/lei-data/lei-mapping/download-the-cik-to-lei-relationship-files
  - ISIN→LEI mapping: https://www.gleif.org/en/lei-data/lei-mapping/download-isin-to-lei-relationship-files
- Nodes carry `cik` (all SEC registrants do) and `canonical_id` per `docs/IDS.md`.
- The universe is built by `expand_us.py` (`build_nodes()` / `source_node()` /
  `apply_canonical_entity_model()`).

## Task

1. New `refresh_gleif.py` (match the style of the other `refresh_*.py`
   scripts): download the CIK→LEI and ISIN→LEI files to `data/raw/gleif/`,
   normalize to a small local lookup, e.g. `graph/data/sources_meta/lei_map.json`
   (or CSV — smallest thing), with `{cik10: lei}` and `{isin: lei}` maps.
   Skip download if the local file is < 30 days old unless `--force`.
2. In `expand_us.py`, join during node build: if a node has a CIK and the map
   has an LEI, set `node["lei"]` and record it in `entity_model`.
3. Add `refresh_gleif.py` to `refresh_all.py` (before the universe build).
4. Update `config/sources.yaml` so the gleif block describes what actually
   runs (mapping-file join, not per-name API).
5. Report coverage: N nodes with CIK, N with LEI, N unresolved — print at the
   end of the build (one line, like existing build output).

## Notes

- ~14,600 nodes have a non-empty `cik` including non-US batches — that itself
  is suspicious. While in `source_node()`, check whether country-batch records
  inherit bogus CIKs; if so, only set `cik` when the source record really has
  one, and report how many were cleared.
- GLEIF Level 2 ownership (parent/child) is out of scope here — note it as a
  follow-up in the commit message, don't build it.

## Acceptance checks

- `python3 refresh_gleif.py && python3 expand_us.py` completes.
- ≥ 90% of nodes with a *genuine* CIK have `lei` set (spot-check: NVDA →
  `549300S4KLFTLO7GSQ80`, AAPL → `HWUPKR0MPOU8FGXBT394`).
- A quality assertion exists (in `test_ids.py` or a new `test_universe_quality.py`):
  LEI coverage ratio above threshold, and no node with `lei` of wrong length.
- UI detail panel shows LEI for NVDA (add the row if trivial; otherwise leave
  UI for prompt 08 and say so in the commit).

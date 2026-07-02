# 01 — Move curated data out of Python into JSON

Status: DONE
Depends on: none
Roadmap: Next Updates #2; Cut items (build_dataset.py L1-211, seed-data file)

## Goal
`expand_us.py` becomes a pure builder. All curated *data* (nodes and links) lives in
JSON files it reads. `build_dataset.py` is deleted.

## Context
- `expand_us.py` currently hardcodes: `PRIVATE_NODES`, `GOVERNMENT_NODES`, `LEGACY_NODES`,
  `PRIVATE_LINKS`, `GOV_CONTRACT_LINKS`, `LEGACY_LINKS`, and imports `LINKS, REL_DEFS,
  SECTOR_COLORS, short_key` from `build_dataset.py`.
- `build_dataset.py` is imported ONLY by `expand_us.py`. Nothing else uses it.

## Steps
1. Create `graph/data/curated_nodes.json` = array of the private/government/legacy node
   dicts (keep every existing field: id, n, sector, sub, hq, f, status, end_date…).
2. Create `graph/data/curated_links.json` = array of ALL curated links currently in
   `LINKS` + `PRIVATE_LINKS` + `GOV_CONTRACT_LINKS` + `LEGACY_LINKS`, normalized to the
   dict form `{from,to,rel,src,val,detail,...}`. Preserve existing source_url/confidence/
   start/end where already present.
3. In `expand_us.py`: delete the `build_dataset` import. Inline the tiny `short_key`
   (one line), `SECTOR_COLORS`, and `REL_DEFS` constants directly (they're small).
   Load curated nodes/links from the two JSON files instead of the Python literals.
4. Delete `build_dataset.py`.

## Acceptance criteria
- `python3 expand_us.py` prints the SAME company and link counts as before this change.
- `grep -rn build_dataset *.py` returns nothing.
- `graph/data/universe.json` diff vs the pre-change build is empty except key ordering.
- Adding a new curated link = editing `curated_links.json` only, no Python edit.

## Guardrails
- Ponytail: do not invent a schema/loader class; `json.load` + the existing
  `normalize_link()` is enough. Keep `validate()` as-is.
- Verify per global guardrails.

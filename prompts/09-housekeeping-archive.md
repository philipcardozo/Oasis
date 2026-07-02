# 09 — Housekeeping: archive unused pipeline + dead config

Status: DONE
Depends on: 01, 05 (so nothing here is still needed by the active build)
Roadmap: Cut items (ingest.py, load_neo4j.py, config/sources.yaml L44-51)

## Goal
Remove dead weight that no active path uses, without losing anything that might be wired
back in later.

## Context
- `ingest.py` writes `data/nodes.jsonl` / `data/edges.jsonl` that nothing currently consumes.
- `load_neo4j.py` reads that old JSONL, not `universe.json`. Neo4j isn't in use.
- `config/sources.yaml` has disabled `wikidata`/`opencorporates` blocks no script reads.

## Steps
1. Confirm (grep) that `ingest.py` and `load_neo4j.py` outputs are referenced by NOTHING
   in the active path (`expand_us.py`, `refresh_*`, `graph/`).
2. Move both to `archive/` (don't hard-delete — they're the GLEIF/Neo4j starting point for
   the Phase-2 ownership-edges work). Add a one-line `archive/README.md` saying why.
3. In `config/sources.yaml`, delete the disabled `wikidata`/`opencorporates` blocks (they
   document nothing the code reads). Keep `usaspending`/`news`.

## Acceptance criteria
- `python3 expand_us.py` still builds identically.
- Active directory no longer contains unused `ingest.py`/`load_neo4j.py`.
- `git status` (or a file listing) shows them in `archive/`, not gone.

## Guardrails
- Ponytail: archive over delete here, because Phase-2 ownership edges will reuse the GLEIF
  code. Deleting it would mean rewriting it later — that's not lazy, it's wasteful.
- Do not touch the active `usaspending`/`news` config.

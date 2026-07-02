# 14 — Split data payload (core vs bulk, lazy load)

Status: DONE
Depends on: 13 (pairs with the canvas renderer)
Roadmap: keep initial load small as node count grows

## Why this is a precondition
`universe.json` carries all nodes. At 50k+ it becomes a multi-MB download parsed before
first paint, even though network mode only needs ~50 connected nodes. Split it before the
file gets big.

## Steps
1. `expand_us.py` writes two files:
   - `graph/data/universe_core.json` — `meta`, `sectors`, `rels`, all `links`, and ONLY
     connected nodes (`deg>0`).
   - `graph/data/universe_bulk.json` — the remaining disconnected nodes.
2. UI fetches `universe_core.json` immediately (network mode renders from it).
3. UI fetches `universe_bulk.json` once, on the first switch to "Show all".

## Acceptance criteria
- Initial load fetches only core; network mode works with no bulk file present.
- "Show all" triggers exactly one bulk fetch, then reuses it.
- Combined node/link counts equal today's single-file counts.

## Guardrails
- Ponytail: two static files + one lazy `fetch`. No tiling server, no pagination API, no
  backend — those are later, only if measured necessary.

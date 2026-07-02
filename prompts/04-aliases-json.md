# 04 — aliases.json entity resolution

Status: DONE
Depends on: 01 (curated links in JSON)
Roadmap: Next Updates #4

## Goal
A simple alias table so curated links and search resolve to the right node id without
fuzzy matching. This is the cheap step that comes BEFORE any Splink.

## Context
- Ticker share classes differ across sources (`BRK.B` vs `BRK-B`) — `expand_us.py`
  already hacks `.replace(".","-")`. Names vary too ("Alphabet" vs `GOOGL`,
  "Meta"/"Facebook" vs `META`).

## Steps
1. Create `graph/data/aliases.json`: `{ "<alias-or-old-name>": "<canonical node id>" }`.
   Seed with: share-class variants, common short names, private-company aliases
   (e.g. "Twitter" → `LEGACY_TWTR`, "TikTok" → `PVT_BYTEDANCE`).
2. In `expand_us.py`, when resolving a link endpoint or building nodes, consult
   `aliases.json` before declaring a miss. Replace the ad-hoc `.replace(".","-")` with
   the alias lookup (keep the replace as a fallback).
3. In the UI search, map a typed alias to the canonical id.

## Acceptance criteria
- A curated link written as `BRK.B` and one as `BRK-B` both resolve (no DROPPED line).
- Searching "Twitter" or "TikTok" finds the right node.
- Self-check: a `test_aliases.py` (or `__main__` asserts) verifying 3 known aliases resolve.

## Guardrails
- Ponytail: a flat dict + `.get()`. No fuzzy lib, no Splink, no ML. That's a later,
  measured step.

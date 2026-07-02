# 12 — Canonical entity id strategy

Status: DONE
Depends on: 11 (know the duplicate shape first)
Roadmap: precondition for multi-exchange / non-US companies

## Why this is a precondition
Today `id == ticker`, which is unique only within the SEC set. Foreign listings, ADRs,
and multi-exchange companies will collide once more sources are added. Fix the identity
rule before, not after, the collisions exist.

## Steps
1. Document the rule in `docs/IDS.md` (short):
   - Canonical id priority: `LEI` if known → else `EXCH:TICKER` (e.g. `XNAS:NVDA`) for
     non-US/new sources → US SEC companies keep their bare ticker for now (already unique).
   - Private = `PVT_*`, government = `GOV_*`, legacy = `LEGACY_*` (unchanged).
2. `expand_us.py`: ensure every node has an explicit `canonical_id` field (for US set it
   equals the ticker today — no churn). New-source loaders must assign per the rule.
3. `aliases.json` maps every alias to the `canonical_id`, not to incidental tickers.

## Acceptance criteria
- Every node has a unique `canonical_id`; a check script reports 0 collisions.
- An alias for a foreign listing of an existing company resolves to the SAME canonical id.
- US tickers are unchanged (no gratuitous id rewrite).

## Guardrails
- Ponytail: this is mostly a documented convention plus one field. Do NOT rewrite all
  existing ids. The rule only bites when a second (non-SEC) source lands.

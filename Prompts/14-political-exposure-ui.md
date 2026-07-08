# 14 — Political exposure wedge: UI

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompts 08 and 13. Ponytail rules apply.

## Context

Data now exists: politician Person nodes, committee memberships, TRADED
candidate edges, committee→sector relevance map, USAspending contract links.
Vault guardrail: present overlap and timing; no causal/corruption claims,
neutral wording throughout ("disclosed purchase", "committee overlap").

## Task

1. **Company drawer: "Political" section** (only when data exists):
   - Disclosed trades table: politician, party/state chip, tx type, amount
     range, tx date vs disclosure lag, source link.
   - Committee overlap: committees deemed relevant to this company's group
     (from the relevance map) with member counts and "N members disclosed
     trades in this issuer".
   - Contract context: existing gov_contracts rows for this company on a
     small timeline (year buckets), with trade dates overlaid as dots.
2. **Politician drawer** (Person node with politician role): chamber, party,
   state, committees; disclosed trades grouped by issuer with jump-links to
   companies; total disclosed volume band per year.
3. **"Political exposure" lens** (uses prompt 12 machinery): Map/Network
   filtered to entities having TRADED candidates or gov contracts; TRADED
   overlay edges visible and styled distinctly (dashed + neutral color, not
   alarm-red); legend line in the drawer, not on the canvas.
4. Search must find politicians by name ("Pelosi" → person node).
5. Everything sourced: every rendered fact keeps its source chip. Amounts are
   ranges (disclosures are ranged) — render the range, never a fake midpoint.

## Acceptance checks

- Open a major defense contractor: Political section renders trades +
  committee overlap + contract timeline; every row has a working source link.
- Open the politician from one of those rows: their drawer lists the trade
  and links back; search finds them by last name.
- Switch to the Political exposure lens: canvas filters correctly; switching
  back to Company research restores the prior view.
- Companies with no political data show NO Political section (not an empty one).
- Wording audit: grep the new UI strings for loaded terms ("insider",
  "corrupt", "suspicious") — none present.
- Tests pass; extend `test_political.py` or product-shell test to assert the
  drawer section config exists and lens JSON validates.

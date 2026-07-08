# 11 — Reverse DCF + graph-aware comparables

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 10 (store) — or adapt to JSON if run earlier. Ponytail rules apply.

## Context

- `dcf_export.py` already extracts annual fundamentals from SEC companyfacts
  (`TAGS` map, `get_latest_filed_annual`) and builds a styled DCF workbook;
  `map_api.py` serves it at `/api/entity/{id}/dcf.xlsx`. `prices.json` has
  current prices; shares outstanding come from companyfacts.
- The graph has typed edges (supplies, partners, owns, funds, ...) — that is
  a peer-selection signal no generic tool has.

## Task

1. **Reverse DCF** (`reverse_dcf.py`, reusing dcf_export's extraction — do
   not duplicate the TAGS map, import it):
   - Inputs: latest FCF (or dividends for the dividend model), net debt,
     shares, current price, discount rate (default 9%, overridable), terminal
     growth (default 2.5%).
   - Solve (bisection, stdlib) for the constant 10-y growth rate that makes
     PV = market cap. Output: implied growth %, plus a small sensitivity
     table over discount rates 7–11%.
   - Endpoint `GET /api/entity/{id}/reverse-dcf` returning JSON; render in
     the company drawer Model section as "Priced-in growth: X%".
2. **Graph-aware comps** (`comps.py`):
   - Peer set: 1-hop graph neighbors of the same `node_type` (via edges) ∪
     same `group` members, ranked graph-neighbors first, cap ~12.
   - For peers with companyfacts cached: revenue, EBIT margin, implied
     EV/EBIT and P/E from prices + shares (skip peers missing data, say so).
   - Endpoint `GET /api/entity/{id}/comps`; drawer table with a "peer source"
     chip (graph vs sector).
3. Both must degrade cleanly: entities without CIK/facts return
   `{available: false, reason}` — the drawer hides the section.
4. One pytest each with a cached-facts company (NVDA facts are in
   `graph/data/companyfacts/`): assert reverse-DCF solver converges and comps
   returns ≥ 3 peers for NVDA.

## Acceptance checks

- `curl localhost:8788/api/entity/NVDA/reverse-dcf` → implied growth between
  -50% and +100%, sensitivity table present; number is stable across runs.
- Manual sanity: PV of the implied-growth cash-flow stream reproduces market
  cap within 1% (assert this inside the test).
- NVDA drawer shows both sections; an Indonesian no-CIK node shows neither
  (no errors in console).
- No duplicated XBRL tag tables (grep: TAGS defined once).

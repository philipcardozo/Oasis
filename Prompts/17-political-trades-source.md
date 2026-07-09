# 17 — Political trades: QuiverQuant adapter (PARKED until paid access)

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules apply.
**Do not start this without first choosing a data source (see below).** It is
blocked on external data availability, not on code.

## Decision (2026-07-09)

**QuiverQuant is the selected launch source.** The provider boundary now exists
in `political_trades_provider.py`, and `refresh_pol_trades.py` defaults to
`NullPoliticalTradesProvider`. Building the authenticated Quiver adapter is
postponed until the paid plan is purchased before launch.

No API key, network call, or speculative Quiver client belongs in the tree yet.

## Why the implementation is parked

Prompts 13/14 delivered the political wedge *structure* — POL_ Person nodes,
committee memberships, committee→policy map, House-Clerk PTR filing provenance,
and the company-drawer committee-overlap + contract sections. What's missing is
**transaction-level trades** (which politician bought/sold which ticker, when,
for how much), which unlocks:

- the disclosed-trades table in the company + politician drawers
- `POL_ → company` TRADED overlay edges on the graph/map
- politician nodes appearing in search and the graph
- the trade-filtered "political exposure" lens overlay

The free structured datasets that used to provide this (House/Senate Stock
Watcher S3 JSON) are **offline (403)**. The durable official source
(House Clerk / Senate eFD) publishes **PDFs**, which need brittle parsing.

## Decide first (owner picks one)

| Option | Access | Cost | Effort | Notes |
|---|---|---|---|---|
| Quiver Quantitative API | API key | Paid tier | Low | Clean congressional-trading endpoint |
| Capitol Trades | Unofficial/scrape | Free | Med | ToS risk; structure changes |
| Finnhub congressional-trading | API key | Free tier | Low | Rate-limited; check coverage |
| House/Senate PDF parsing | Public | Free | High | Most durable, most work; new dep (pdf parser) |
| Unusual Whales / others | API key | Paid | Low | Verify licensing for redistribution |

If none is acceptable, **leave this parked** — the wedge already ships real
committee + contract value without trades.

## Task (once a source is chosen)

1. New `refresh_pol_trades.py` path (extend, don't replace, the existing PTR
   filing ingest): fetch transaction rows, normalize to
   `{politician_bioguide, ticker, asset_name, tx_type, amount_low, amount_high,
   tx_date, disclosure_date, source_url}`.
2. Resolve `ticker` → node via `graph/data/aliases.json` / canonical ids;
   unresolved → `pol_trades_review.json`, never guessed.
3. Write `data/store/pol_trades.parquet` (real transactions now, not just
   filings) and emit `TRADED` edge candidates
   `{from: POL_x, to: <company>, type: "traded", as_of, source, confidence}`
   through the existing `edge_candidates.json` gate — distinct overlay class,
   not auto-merged into structural edges.
4. Make politician Person nodes graph/search-visible (they exist in
   `pol_members`; surface them the way company nodes are surfaced).
5. UI (finishes prompt 14): disclosed-trades table in company + politician
   drawers (render amount **ranges**, never a fake midpoint); TRADED overlay
   edges styled distinctly (dashed, neutral color — not alarm-red); trade rows
   feed the political-exposure lens. Neutral wording throughout (no "insider"/
   "corrupt"/"suspicious"); grep the new strings to confirm.

## Acceptance checks

- ≥ 80% ticker resolution; unresolved in review file with reasons.
- A known frequent filer → person node in search, ≥ 1 trade row with source_url
  + both dates, a TRADED candidate edge to a real company.
- Idempotent (two runs, no dupes); `test_political.py` extended (schema, ID
  format, no TRADED edge without source_url + dates).
- Wording audit clean; amounts render as ranges.

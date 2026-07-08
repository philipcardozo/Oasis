# 15 — Event pipeline v1 + daily briefing

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 10; prompt 13 enriches it. Ponytail rules: cron + files, no queues,
no daemons, no LLM narration.

## Context

OASIS refresh scripts already fetch filings, contracts, prices, news — but
they overwrite caches; nothing is an *event* with a timeline. Goal: one
append-only events table + deterministic gates + a generated morning
briefing. This is vault "09 - Deterministic Models" infrastructure, built
the boring way.

## Task

1. **Event extraction** from existing refresh outputs (do NOT build new
   fetchers): after each refresh, diff new data against the store and append
   events to `data/store/events.parquet`:
   - filing event: new accession number per company (`refresh_filings`).
   - contract event: new/changed USAspending obligation (`refresh_gov_contracts`).
   - price event: |1-day move| ≥ 2σ of that node's trailing prices
     (`refresh_prices` history where available).
   - news event: new item per entity (`refresh_news`).
   - trade event: new politician trade row (prompt 13).
   Event schema: `{event_id, oasis_id, event_type, ts, title, payload_json,
   source_url, retrieved_at, gates_json}`.
2. **Gates** (pure functions in one `gates.py`, each stamps
   `{gate, pass, reason}` into `gates_json` — inspectable, never silent):
   - entity gate: resolves to a known node (else quarantine file).
   - dedupe gate: content-hash + (entity, type, ±3-day window).
   - materiality gate per type: 8-K/10-K/13D over routine 424B; contract
     Δ ≥ $10M or ≥ 1% of revenue when known; price ≥ 2σ; politician trade
     always material at range ≥ $50k.
   - priority: P1 = material + (watchlisted OR graph-degree ≥ 5), P2 =
     material, P3 = rest.
3. **Watchlists**: `graph/data/watchlists.json` `{name, entity_ids[]}` with
   a minimal add/remove UI hook in the drawer (star icon) — this feeds the
   priority gate.
4. **Daily briefing**: `build_briefing.py` → `outputs/briefings/YYYY-MM-DD.md`:
   P1 events grouped by watchlist then entity, one line each: title, type,
   date, source link, priority reason (from gates_json). P2 as a compact
   digest. Plain deterministic Markdown — no prose generation.
5. **Company timeline**: drawer "Events" section reading
   `GET /api/entity/{id}/events` (DuckDB query, newest first, type icons).
6. Wire into `refresh_all.py`; document the cron line in README
   (`0 7 * * * cd ... && python3 refresh_all.py && python3 build_briefing.py`).

## Acceptance checks

- Two consecutive `refresh_all.py` runs: second run appends only genuinely
  new events (dedupe gate holds; assert count delta reasonable).
- Every event has ≥ 3 gate stamps with reasons; quarantine file collects
  unresolvable items rather than dropping them.
- Star NVDA into a watchlist → force a filing/news delta → briefing lists it
  under P1 with a working source link.
- `/api/entity/NVDA/events` returns a sorted timeline; drawer renders it.
- pytest: `test_events.py` covering dedupe, a materiality rule per type, and
  briefing generation from a fixture events table.

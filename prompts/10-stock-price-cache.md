# 10 — Stock price cache (current + day move + 6-month change)

Status: DONE
Depends on: 03 (panel targets connected companies), 06 (mirror the filings pattern)
Roadmap: new feature request (price context on click)

## Goal
When a connected PUBLIC company is selected, the detail panel shows: latest price,
today's change (abs + %), and the 6-month change (%). Static, refresh-time data — no
browser API calls, no key, no backend.

## Why this shape
- The UI is a static single file. A browser-side price API means CORS pain and an exposed
  API key. The project already solves this for filings: fetch in Python, write JSON, UI reads it.
- "Future prices" are not a thing — show current + 6-month history only. Never fabricate a forecast.

## Steps
1. New `refresh_prices.py`, modeled on `refresh_filings.py`:
   - For each connected public company (`deg>0`, `kind=="public"`), fetch ~6 months of
     daily adjusted closes via **yfinance** (free, no key). Zero-dep fallback: Stooq CSV
     `https://stooq.com/q/d/l/?s=<ticker>.us&i=d` via `urllib`.
   - Compute: `price`, `day_change_abs`, `day_change_pct` (last vs prior close),
     `chg_6m_pct` (last vs ~126 trading days ago), and a short `spark` array
     (downsampled closes, ~26 points) for a tiny inline sparkline.
   - Write `graph/data/prices.json` keyed by ticker with an `as_of` date.
   - **Keep the math in pure functions** importable WITHOUT yfinance/requests (put the
     network import inside the fetch fn), so the test runs in a minimal env. (This also
     fixes the same smell currently in `refresh_filings.py`.)
2. `expand_us.py`: merge `prices.json` into each node as `node.price` when present.
3. UI: in the detail panel add a "Market" block — price, colored day move (green up / red
   down), 6-month move, and an inline SVG `<polyline>` sparkline from `spark`. Show it only
   when `node.price` exists.
4. `refresh_all.py`: add `refresh_prices.py` to the sequence.
5. Freshness banner (#07): add `prices <date>`.
6. `test_prices.py`: assert `day_change_pct` and `chg_6m_pct` from a fixed close series.
   No network in the test.

## Acceptance criteria
- `prices.json` has an entry per connected public company.
- Selecting e.g. NVDA shows price, today's move (signed/colored), 6-month %, and a sparkline.
- Private/government/legacy nodes show NO market block, no error.
- `test_prices.py` passes with neither yfinance nor requests installed.
- A spot check: one company's day move matches a public quote within rounding.

## Guardrails
- Ponytail: reuse the `refresh_filings.py` request/rate pattern. Inline SVG sparkline, not
  a charting library. One new refresh script + one JSON + one panel block.
- Accuracy: numbers come only from the price source. No forecasts, no "target prices",
  no made-up figures. Label `as_of` so staleness is visible.
- Do-not-build still holds: no Polygon/paid feed, no client-side key, no backend.

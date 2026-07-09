# Oasis Relationship Graph

Oasis is an accuracy-first static relationship graph for U.S. public companies, major private companies, government agencies, and curated business relationships. It builds static JSON under `graph/data/` and serves a single-file UI from `graph/index.html`; structural edges should stay cited.

## Three Commands

Refresh (a fresh clone must run both — the served payloads under `graph/data/`
are generated, not tracked):
```sh
python3 refresh_all.py
python3 build_map_geojson.py
```

Serve (use `map_api.py` for the full app — it serves the UI **and** the
`/api/*` endpoints the drawer's Model / Political / Events sections need; the
plain `http.server` gives the globe only, no API):
```sh
python3 map_api.py        # UI + API on http://127.0.0.1:8788
# or, static globe only:
python3 -m http.server 8778 --directory graph
```

Open:
```sh
open http://127.0.0.1:8788/index.html
```

> Current tree note (2026-07-08): the generated data was wiped in a disk-full
> cleanup, so a checkout must run the refresh above before serving, and the
> test suite is red until `Prompts/16` migrates readers to the Parquet store.
> See `Prompts/00-README.md` for status.

Data sources: SEC company/submissions data, USAspending contracts, Google News RSS, and curated cited relationship JSON.

Accuracy rule: add edges only when they have a real source URL, date, and confidence. News-discovered relationships go to `graph/data/edge_candidates.json` first; only `status:"confirmed"` candidates with evidence enter the graph.

## Daily events + briefing (prompt 15)

`refresh_all.py` extracts append-only events (filings, contracts, ≥2σ price moves,
news, politician PTRs) into `data/store/events.parquet` via deterministic gates
(`gates.py`), then writes `outputs/briefings/YYYY-MM-DD.md`. Star entities in the
company drawer to drive P1 priority (`graph/data/watchlists.json`).

Cron (7am daily):
```
0 7 * * * cd /Users/felipecardozo/Desktop/coding/Quant\ Learn/Oasis && python3 refresh_all.py && python3 build_briefing.py
```

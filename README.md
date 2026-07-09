# Oasis Relationship Graph

Oasis is an accuracy-first static relationship graph for U.S. public companies, major private companies, government agencies, and curated business relationships. It builds static JSON under `graph/data/` and serves a single-file UI from `graph/index.html`; structural edges should stay cited.

## Three Commands

Regenerate data (the JSON/GeoJSON under `graph/data/` and Parquet under
`data/store/` are gitignored build artifacts):
```sh
python3 bootstrap.py    # offline core, using committed source snapshots/caches
python3 refresh_all.py  # full networked refresh
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

Data sources: SEC company/submissions data, USAspending contracts, Google News RSS, and curated cited relationship JSON.

Accuracy rule: add edges only when they have a real source URL, date, and confidence. News-discovered relationships go to `graph/data/edge_candidates.json` first; only `status:"confirmed"` candidates with evidence enter the graph.

Political transaction rows use the provider seam in
`political_trades_provider.py`. QuiverQuant is selected for launch, but the
current `NullPoliticalTradesProvider` intentionally makes no paid API calls
until access is purchased.

## Daily events + briefing (prompt 15)

`refresh_all.py` extracts append-only events (filings, contracts, ≥2σ price moves,
news, politician PTRs) into `data/store/events.parquet` via deterministic gates
(`gates.py`), then writes `outputs/briefings/YYYY-MM-DD.md`. Star entities in the
company drawer to drive P1 priority (`graph/data/watchlists.json`).

Cron (7am daily):
```
0 7 * * * cd /Users/felipecardozo/Desktop/coding/Quant\ Learn/Oasis && python3 refresh_all.py && python3 build_briefing.py
```

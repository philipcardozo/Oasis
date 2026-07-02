# Oasis Relationship Graph

Oasis is an accuracy-first static relationship graph for U.S. public companies, major private companies, government agencies, and curated business relationships. It builds static JSON under `graph/data/` and serves a single-file UI from `graph/index.html`; structural edges should stay cited.

## Three Commands

Refresh:
```sh
python3 refresh_all.py
```

Serve:
```sh
python3 -m http.server 8778 --directory graph
```

Open:
```sh
open http://localhost:8778/index.html
```

Data sources: SEC company/submissions data, USAspending contracts, Google News RSS, and curated cited relationship JSON.

Accuracy rule: add edges only when they have a real source URL, date, and confidence. News-discovered relationships go to `graph/data/edge_candidates.json` first; only `status:"confirmed"` candidates with evidence enter the graph.

# 01 — Repo hygiene & git de-bloat

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Context

- `.git` is 563 MB; working tree is ~7 GB. `git status --porcelain | wc -l`
  reports ~7,000+ dirty files, almost all terrain tile PNGs.
- `.gitignore` only excludes `graph/tiles/usgs_3dep/terrain-rgb/`; the unified
  `graph/tiles/terrain-rgb/` tree (~83,000 PNGs, 5 GB) is partially tracked
  (~1,900 tracked tiles) and floods every git operation.
- Generated data (`graph/data/universe*.json` ~33 MB, `companyfacts/` up to
  7.7 MB per file, `reports/` 228 files) is tracked but fully regenerable.
- Debug artifacts `graph/data/dupes_report.json` (1.8 MB) and
  `graph/data/location_unknown.json` (1.6 MB) sit in the served web root.
- One-shot ingest scripts `build_africa_batch.py`, `build_apac_batch.py`,
  `build_indonesia_batch.py` clutter the repo root; their output already
  lives in `graph/data/sources/*.jsonl`.

## Task

1. **Backup first**: `git clone --mirror . ../Oasis-backup.git` (verify it
   exists before any destructive step).
2. Commit any real (non-generated, non-tile) work currently uncommitted so
   nothing is lost.
3. Extend `.gitignore`: all of `graph/tiles/`, `graph/data/universe.json`,
   `graph/data/universe_bulk.json`, `graph/data/universe_core.json`,
   `graph/data/companyfacts/`, `graph/data/reports/`,
   `graph/data/dupes_report.json`, `graph/data/location_unknown.json`,
   `outputs/`, `archive/data/`, `Assets & Media/`.
4. `git rm -r --cached` everything newly ignored; commit.
5. Move `dupes_report.json` and `location_unknown.json` writers to
   `outputs/diagnostics/` (grep `dedupe_report.py`, `expand_us.py`,
   `build_map_geojson.py` for their writers; check `graph/index.html` — if
   the UI fetches `location_unknown.json`, keep that one served but confirm
   with a grep before moving). Smallest change that gets diagnostics out of
   the web root without breaking a UI fetch.
6. Move the three `build_*_batch.py` scripts to `scripts/ingest/`.
7. **History rewrite (destructive — ask the user for explicit confirmation
   in-session before running):** `git filter-repo` to drop
   `graph/tiles/` and `graph/data/companyfacts/` from history. If the user
   declines, stop after step 6 — the ignore rules alone stop the bleeding.

## Acceptance checks

- `git status --porcelain | wc -l` < 30.
- `git ls-files | grep -c "graph/tiles"` returns 0.
- `python3 refresh_all.py` still completes; `python3 map_api.py` serves the UI.
- If step 7 ran: `du -sh .git` < 100 MB and the mirror backup exists.

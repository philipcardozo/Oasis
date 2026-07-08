# 01 — Repo hygiene & git de-bloat (FINISH remaining work)

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Already done (do not redo)

- `.gitignore` extended; `graph/tiles/` untracked (`git ls-files | grep -c graph/tiles` == 0).
- Batch scripts moved to `scripts/ingest/`.

## Still broken

- **History was never rewritten**: `.git` = ~569 MB, working tree = ~6.1 GB,
  and ~5 GB of terrain PNGs still sit in `graph/tiles/` on disk. Old tile/
  companyfacts blobs remain in git history.
- **Prompts 03/04/05 work is uncommitted**: `refresh_gleif.py`,
  `refresh_sec_addresses.py`, `test_universe_quality.py`, modified
  `expand_us.py` / `refresh_all.py` / tests, and an 18.7 MB
  `graph/data/sources_meta/lei_map.json` are all dirty. Functional and
  passing (`pytest -q` → 22 passed) but never committed.
- **The tree never stays clean**: generated UI payloads are still tracked and
  rewritten on every refresh, so `git status` perpetually shows ~46 dirty
  (companies.geojson, securities.geojson, relationships.geojson,
  graph-index.json, hq_coords.json, filings.json, news.json,
  gov_contracts.json, edge_candidates.json, outputs/dcf/*.xlsx).

## Task

1. **Commit the 03/04/05 work first** (so history rewrite can't lose it).
   Before committing, add `graph/data/sources_meta/lei_map.json` to
   `.gitignore` — it's a regenerable 18.7 MB download from `refresh_gleif.py`,
   not source. Same for `data/raw/gleif/` and `data/raw/sec/` if tracked.
   Commit message: `feat(03-05): GLEIF LEI join, SEC business-address HQ, single-build + pytest`.
2. **Stop the payload churn.** These files are regenerable by
   `refresh_all.py` + `build_map_geojson.py`; a fresh clone rebuilds them.
   Add to `.gitignore` and `git rm --cached`:
   `graph/data/companies.geojson`, `graph/data/securities.geojson`,
   `graph/data/relationships.geojson`, `graph/data/graph-index.json`,
   `graph/data/hq_coords.json`, `graph/data/filings.json`,
   `graph/data/news.json`, `graph/data/gov_contracts.json`,
   `graph/data/edge_candidates.json`, `outputs/`.
   Add a one-line note to README: fresh clone runs `python3 refresh_all.py`
   then `python3 build_map_geojson.py` to generate served data.
   (If any of these is hand-curated rather than generated — verify with
   `git log --oneline -- <file>` and a grep for its writer — keep that one
   tracked and say which in the commit.)
3. **Backup, then rewrite history** (destructive — confirm with the user
   in-session before running):
   - `git clone --mirror . ../Oasis-backup.git` and verify it exists.
   - `git filter-repo --path graph/tiles --path graph/data/companyfacts --invert-paths`
     (add any other large regenerable path that shows up in
     `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | sort -k3 -n | tail -30`).
   - Re-add the remote if the mirror clone dropped it.
4. **Confirm the tiles on disk are expendable before deleting them.** Prompt
   09 (terrain → AWS) deletes `graph/tiles/terrain-rgb/` anyway; if 09 is
   running soon, leave the 5 GB for 09 to remove. Otherwise, once history is
   clean, delete on disk to reclaim space (they rebuild from the registry).

## Acceptance checks

- `git status --porcelain | wc -l` < 15 after a fresh `refresh_all.py`
  (generated payloads no longer appear).
- `git ls-files | grep -c "graph/tiles"` == 0; `lei_map.json` not tracked.
- After the rewrite: `du -sh .git` < 100 MB and `../Oasis-backup.git` exists.
- `python3 refresh_all.py` completes; `python3 map_api.py` serves the UI;
  `python3 -m pytest -q` still passes.

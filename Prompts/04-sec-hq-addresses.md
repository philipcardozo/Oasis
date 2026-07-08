# 04 — Real headquarters from SEC business addresses

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Context

- 9,186 nodes in `graph/data/universe.json` store an exchange name as their
  HQ (`hq` value counts: Nasdaq 4,125 / NYSE 3,072 / OTC 1,989). Only ~4,300
  of 14,600 entities resolve to city coordinates on the globe — the vault
  calls this the biggest map-quality bottleneck.
- SEC `https://data.sec.gov/submissions/CIK##########.json` contains
  `addresses.business` (`city`, `stateOrCountry`, `stateOrCountryDescription`)
  for every registrant. The pipeline already fetches submissions in
  `refresh_filings.py` but only for ~120 companies, and discards the address.
- Bulk option: SEC publishes the whole submissions dataset as one zip
  (`https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip`,
  ~1.3 GB). Alternative: per-company fetch at ≤ 8 req/s with the existing
  User-Agent (`config/sources.yaml`) — ~12k CIKs ≈ 30 min. Pick one; bulk zip
  is preferred (one download, no rate-limit dance). Extract only the fields
  needed, then delete the zip.
- Geocoding of city strings already exists: `geocode_hq_coords.py` +
  `graph/data/hq_coords.json`.

## Task

1. New `refresh_sec_addresses.py`: produce `data/raw/sec/business_addresses.json`
   mapping `cik10 → {city, state_or_country, description}`. Cache; refresh
   only when stale (> 30 days) or `--force`.
2. In `expand_us.py`, when a node's `hq` is empty or an exchange placeholder
   (`NYSE`, `Nasdaq`, `NYSE American`, `NYSE Arca`, `OTC`, `Cboe BZX`, `—`),
   replace it with `"{city}, {state_or_country_description}"` from the address
   map. Never overwrite a real city that came from a source batch.
3. Set `entity_model.location.country` properly (US states → "US"; otherwise
   the country description) and raise `location.confidence` for
   address-sourced HQs (currently NVDA sits at 0.25 for a perfect city —
   score: address/batch-sourced city ≈ 0.9, country-only ≈ 0.5, unknown 0).
4. Run `geocode_hq_coords.py` after the rebuild so new cities get coordinates.
5. Print before/after: exchange-placeholder count, located count.

## Acceptance checks

- Exchange-placeholder HQ count == 0 in the rebuilt `universe.json`.
- City-level located entities > 10,000 (was ~4,312).
- NVDA: `hq` = "Santa Clara, California"-equivalent from SEC data,
  `location.country` = "US", confidence ≥ 0.9.
- Quality assertion added (test file): no `hq` in the exchange-placeholder set.
- Globe visibly denser: `data/companies.geojson` feature count grows accordingly
  (rebuild via `build_map_geojson.py`).

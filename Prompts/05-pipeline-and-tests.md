# 05 — Pipeline single-build + pytest conversion + quality gate

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no new deps, verify before finishing.

## Context

- `refresh_all.py` runs `expand_us.py` **three times** per refresh (full
  universe rebuild each time) to fold in data produced between steps.
- 17 `test_*.py` files exist but use script-style `main()` with asserts;
  `python3 -m pytest -q` reports "no tests ran". CI or a pre-commit gate is
  impossible today.

## Task

1. Reorder `refresh_all.py` so every cache producer runs before ONE final
   `expand_us.py`. Check what each intermediate rebuild actually feeds
   (`refresh_filings.py`, `refresh_prices.py`, `refresh_edge_candidates.py`
   read `universe.json` to know which entities to refresh). If a script needs
   an entity list before the rebuild, let it read the *previous* universe.json
   — it exists on disk; freshness of the entity list lags one cycle, which is
   fine. If a first bootstrap build is genuinely required (fresh clone, no
   universe.json), guard with `if not UNIVERSE.exists()`.
2. Convert the 17 script-style tests to pytest: rename `main()` →
   `test_main()` (keep the `if __name__ == "__main__"` block calling it so
   direct `python3 test_x.py` still works). No fixtures, no conftest, no
   parametrize — pure rename.
3. Add `test_universe_quality.py` asserting on the built `universe.json`:
   - no duplicate `canonical_id`
   - zero exchange-placeholder HQs (after prompt 04)
   - LEI coverage ≥ threshold for CIK'd nodes (after prompt 03)
   - `universe_core.json` + `universe_bulk.json` node count == `universe.json`
   - every link has `source` (URL) and a date field — the accuracy rule from
     README.md.
   Skip cleanly (pytest.skip) if universe.json is absent.
4. Time the refresh before/after (rough wall-clock print in refresh_all.py or
   just report numbers in the commit message).

## Acceptance checks

- `python3 -m pytest -q` collects and passes ≥ 18 tests.
- `python3 refresh_all.py` runs `expand_us.py` exactly once (twice only on
  bootstrap) and total wall time drops materially (expect ~2/3 reduction of
  the build portion).
- `python3 test_ids.py` style direct invocation still works.

# Source Intake

Drop source records into `graph/data/sources/*.jsonl`, one JSON object per line.

Required fields:

- `canonical_id`
- `name`
- `country`
- `exchange`
- `sector_or_sic`

Optional fields:

- `ticker`
- `cik`
- `lei`
- `sub`
- `hq`
- `f`

IDs follow `docs/IDS.md`: known aliases resolve to the existing `canonical_id`; otherwise new exchange-scoped records should use `EXCH:TICKER`.

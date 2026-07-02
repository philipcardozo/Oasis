# Entity IDs

Canonical ID rule:

1. Use `LEI:<lei>` when a legal entity identifier is known.
2. Otherwise use `EXCH:TICKER` for non-US or new exchange-scoped sources, such as `XNAS:NVDA`.
3. Existing US SEC companies keep the bare ticker for now, such as `NVDA`.
4. Curated private, government, and legacy IDs keep their current prefixes: `PVT_*`, `GOV_*`, `LEGACY_*`.

Every node exposes `canonical_id`. Existing `id` values stay unchanged until a new source needs an exchange-scoped ID. Aliases in `graph/data/aliases.json` point to `canonical_id`, not incidental source tickers.

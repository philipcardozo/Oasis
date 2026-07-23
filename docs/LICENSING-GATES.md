# Licensing Feature Gates

Licensing-sensitive providers are code-level feature flags, not footnotes. In
`server/config.py` they default **OFF in production** and ON in dev/staging, and
can be overridden per environment. When a provider is disabled the UI must show a
clear unavailable state and an approved alternative — never a silent fallback to
another restricted provider.

| Provider | Flag | Intended use | Commercial status | Replacement |
|----------|------|--------------|-------------------|-------------|
| Esri World Imagery (satellite) | `OASIS_FEATURE_SATELLITE` | satellite basemap | NOT redistributable; commercial needs a license | Sentinel-2 (open) or licensed imagery |
| yfinance / Yahoo (prices) | `OASIS_FEATURE_PRICES` | equity prices | personal-use only | Polygon / Tiingo / Nasdaq |
| Company logos (Clearbit) | `OASIS_FEATURE_LOGOS` | export logos | vendor ToS; **removed from request path in Phase 0** | local approved logos only |
| CARTO dark-matter | (style only) | dark basemap | style permissive; tiles under CARTO ToS — do NOT bundle | self-host a dark style |
| OpenFreeMap / OSM | (default) | standard basemap | ODbL — attribution + share-alike | — |
| News (Google RSS) | worker-side | headlines | headline+link only; no full-text cache | — |
| Political trades (Quiver) | provider seam | trades | commercial, per-seat | parked until purchased |

## Rule
Do not enable a provider in commercial production until its intended use is
verified against current primary-source terms. Esri and yfinance are the two
that block commercial launch and need a purchase/substitution decision — they are
upstream of offline dataset packaging.

Covered by `test_phase1_security.py::test_valid_production_config_passes`
(asserts satellite + prices default OFF in production).

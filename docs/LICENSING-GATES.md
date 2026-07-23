# Licensing Feature Gates

Licensing-sensitive providers are code-level feature flags, not footnotes. In
`server/config.py` they default **OFF in secure modes** (`staging` and `production`) and ON in development, and
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

## Phase 1.75 Public Staging

For public staging and private beta, unresolved providers remain disabled in
secure modes:

```text
OASIS_FEATURE_SATELLITE=false
OASIS_FEATURE_PRICES=false
OASIS_FEATURE_LOGOS=false
```

This permits a controlled beta only for functionality that does not depend on
unapproved imagery, market-data redistribution, logo redistribution, news
full-text caching, political-trading feeds, or other commercial datasets.

Before enabling any disabled provider, record current official terms, commercial
use permission, caching rules, redistribution rules, attribution, offline-use
rights, account/API-key requirements, and the replacement provider if permission
is not sufficient.

Covered by:

- `test_phase1_security.py::test_valid_production_config_passes`
- `test_phase1_security.py::test_valid_staging_config_disables_unresolved_providers`
- `test_phase1_mapslots.py::test_default_slots_degrade_disabled_satellite`
- `test_phase1_mapslots.py::test_disabled_satellite_basemap_rejected`
- `test_phase1_mapslots.py::test_reset_uses_available_default_when_satellite_disabled`

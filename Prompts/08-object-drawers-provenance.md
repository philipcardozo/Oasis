# 08 — Type-specific object drawers, provenance chips, collision pass

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 07. Ponytail rules apply.

## Context

- Vault note "02 - Roadmap and Missing Work" Stage 3–4 is the spec: hover
  card → side drawer → (compare mode later; skip it now).
- Nodes have `node_type` (`company`, `security`, `fund`, `warrant`,
  `counterparty`) plus curated `PVT_*`/`GOV_*` kinds; every edge carries
  `source` URL, date, and confidence.
- Known rendering bug (vault note 06 item 3): dense network clusters still
  crowd/overlap after the hover-freeze work — needs a real collision pass.

## Task

1. **Drawer by object type.** One drawer component, per-type field config
   (a plain JS object, not a framework):
   - company: name, HQ, LEI/CIK/ticker, exchange, sector/group, connection
     count, top counterparties (from edges), latest filing, price sparkline
     (prices.json), recent news, source confidence, freshness.
   - security: class (ADR/pref/unit/warrant/ETF...), issuer link (jump to the
     company node), exchange/listing, price.
   - fund/government/private: the sensible subset; never render empty rows.
2. **Hover card** (lightweight, follows cursor with delay): name, type,
   HQ/location, exchange, confidence, one latest signal (newest news/filing
   date). Reuse drawer data access; no new fetches on hover.
3. **Provenance everywhere:** each relationship row in the drawer gets a
   source chip (domain of the source URL, clickable) + confidence dot
   (3-step color) + as-of date. Data already exists on the edges.
4. **Collision pass** in the network view: after layout settles, resolve
   label/node overlaps (grid-bucket sweep, push-apart or hide lower-degree
   labels — smallest effective approach; no new physics library).
5. LEI/CIK rows render when present (prompt 03/04 data).

## Acceptance checks

- Open NVDA: company drawer shows identifiers, counterparties with source
  chips, filing, price. Open an ETF/security node: security drawer with
  issuer link that navigates. No drawer shows blank field rows.
- Hover any node ≥ 300 ms → card appears; moving off hides it; no jank in the
  physics loop (check frame rate roughly via DevTools performance).
- Dense cluster (e.g. semiconductor group in network view): no overlapping
  labels at rest; screenshot before/after in the commit message.
- Every relationship row has a working source link.
- Existing tests pass; add one assertion to `test_product_shell.py` that the
  drawer config covers every `node_type` present in `universe_core.json`.

# 15 — Source intake contract (add companies by dropping data, not code)

Status: DONE
Depends on: 12 (canonical ids), 11 (dedup awareness)
Roadmap: makes "add more companies" a data operation, the whole point of the precondition work

## Why this is a precondition
Right now new companies arrive only through the bespoke SEC path. To add more sources
(other exchanges, curated lists) without writing new Python each time, define one intake
schema and a generic loader. THIS is the gate that makes scaling lazy instead of endless.

## Steps
1. Document the node intake schema (`docs/INTAKE.md`): required fields
   `canonical_id, name, country, exchange, sector_or_sic`; optional `cik, lei, sub, hq, f`.
2. `expand_us.py`: add a generic loader that reads every `graph/data/sources/*.jsonl`
   matching the schema and merges them into the node set, deduping by `canonical_id`
   (via aliases). The existing SEC build becomes one producer of such records (or stays
   as-is and is merged alongside — whichever is the smaller diff).
3. On id/name collision, alias resolution (04/12) decides; log conflicts, don't crash.

## Acceptance criteria
- Dropping `graph/data/sources/test_intl.jsonl` with 2 valid companies makes them appear
  after `python3 expand_us.py`, with NO code change.
- A record duplicating an existing company (by canonical id/alias) merges, not duplicates.
- Malformed record is skipped with a logged reason, build still completes.

## Guardrails
- Ponytail: one loader function + a folder glob, reuse existing normalization/validate.
  No plugin registry, no per-source subclasses, no schema-validation library — a few
  field checks are enough.

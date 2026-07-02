# 02 — Backfill edge evidence (source_url, as_of, confidence)

Status: DONE
Depends on: 01 (links now live in curated_links.json)
Roadmap: Next Updates #1

## Goal
Every curated link carries three evidence fields: `source_url` (real link), `as_of`
(date the fact was true, ISO), `confidence` (0-1). No new database.

## Context
- `normalize_link()` already defaults `as_of` and `confidence`. Gov/legacy links already
  have `source_url`. The gap is the tuple-origin links (the old `LINKS` + `PRIVATE_LINKS`),
  which have a `src` text citation but no `source_url`.
- These citations were gathered earlier in the project chat; the URLs exist in that history.

## Steps
1. For each link in `graph/data/curated_links.json` missing `source_url`, add the real
   URL from its citation (e.g. Berkshire 13F → holdingschannel page; OpenAI/NVIDIA →
   the OpenAI announcement; Skyworks → the Investing.com piece).
2. Set `as_of` to the date the figure refers to (e.g. Berkshire stakes → `2026-03-31`;
   NVIDIA customer-mix → `2025-08-30`), not today's date.
3. Set `confidence`: 0.9-0.95 for filings/official announcements, 0.7-0.8 for analyst
   estimates, 0.5-0.6 for "not individually disclosed" inferences.

## Acceptance criteria
- `python3 -c "import json;[print(l['from'],l['to']) for l in json.load(open('graph/data/curated_links.json')) if not l.get('source_url')]"` prints nothing.
- No fabricated URLs. If a real URL genuinely can't be found, leave `source_url:""` AND
  set `confidence <= 0.5` — do not guess a link.
- UI panel still renders (it shows `src`/`detail`; `source_url` becomes a clickable cite).

## Guardrails
- Accuracy: a wrong URL is worse than an empty one. Verify each link resolves to the claim.
- Ponytail: this is data entry, not code. Touch JSON only (and one small UI line if you
  choose to render `source_url` as a link).

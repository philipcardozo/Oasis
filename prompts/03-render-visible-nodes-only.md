# 03 — Render only visible nodes/links (fix latency)

Status: DONE
Depends on: none (independent of 01/02)
Roadmap: Next Updates #3; Cut item (index.html L202-223)

## Goal
Stop creating ~10,450 SVG groups up front. Network mode (default, ~50 visible) must
build only the elements it shows. Index mode builds the rest lazily on first switch.

## Context
- `graph/index.html` `init()` currently maps ALL `COMPANIES` to `<g>` elements eagerly.
- Network mode shows only connected nodes (`deg>0`). The other ~10,400 elements exist
  hidden — that's the cost.

## Steps
1. Build node/edge elements for the connected set only at init.
2. On first switch to "Show all" (index mode), lazily create the remaining elements once,
   then reuse them. (A simple `built` flag; do not rebuild on every toggle.)
3. Keep hit-testing, hover, select, drag, zoom/pan working in both modes.

## Acceptance criteria
- In network mode at load: `document.querySelectorAll('#nodes .node-g').length` ≈ connected
  count (tens), NOT 10,450.
- Switching to index mode renders all companies once; switching back is instant.
- No browser console errors. Select/hover/drag still work in both modes.
- Subjective: panning in index mode is at least as smooth as before.

## Guardrails
- Ponytail: smallest change that achieves lazy creation — a `built` flag + a
  `buildNode(i)` helper. Do NOT introduce a virtual-DOM lib or a renderer rewrite here.
  (WebGL is a separate, later decision — not this prompt.)
- Leave a one-line check: assert visible-node count == connected count right after init.

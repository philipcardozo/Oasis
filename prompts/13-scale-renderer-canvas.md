# 13 — Scale the renderer (index mode → Canvas)

Status: DONE
Depends on: none (rendering-only)
Roadmap: the hard rendering ceiling before any large company add

## Why this is a precondition
Lazy SVG (prompt 03) survives ~10k by not building hidden elements, but "Show all" still
materializes one DOM node per company. At 50k+ that crashes the page. The renderer must
stop scaling DOM with node count BEFORE the company count grows.

## Steps
1. Render INDEX mode to a single `<canvas>`:
   - Draw nodes (and any visible edges) to canvas; redraw on pan/zoom/filter, not per node.
   - Viewport-cull: only draw nodes inside the current view.
   - Hit-test click/hover via a spatial grid or quadtree (screen→graph→nearest node).
2. Keep NETWORK mode (the ~50 connected nodes) as SVG — interactions there already work;
   don't rewrite them.
3. Selecting a node from canvas opens the same detail panel as today.

## Acceptance criteria
- Index mode with the real ~10k: smooth pan/zoom, DOM node count stays ≈ network size.
- Synthetic stress: generate 50k dummy nodes and confirm pan/zoom stays interactive
  (a throwaway flag or test page is fine).
- Click/hover still select the correct company in index mode. No console errors.

## Guardrails
- Ponytail ladder: **Canvas 2D (native) first** — it handles 50k points with culling.
  Escalate to a WebGL graph lib ONLY if Canvas is measured insufficient at the target N.
  No React, no framework.
- Do not touch the working SVG network mode.

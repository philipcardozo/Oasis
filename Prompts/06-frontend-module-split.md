# 06 — Split index.html into ES modules (zero visual change)

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Ponytail rules:
smallest working diff, no build step, no framework, no new deps.

## Context

- `graph/index.html` is 3,064 lines / 221 KB: all CSS + one giant inline
  script containing three render paths (SVG network view with a
  requestAnimationFrame physics loop, a Canvas-2D "index" view, a MapLibre
  globe), data loading, search, filters, detail panel, DCF UI, manual-layer
  state, and product prefs.
- The vault roadmap (Engine/Maker/Lenses, richer drawers) cannot fit in this
  file. This split is the precondition — refactor only, **no behavior change**.
- The app is served statically (`python3 -m http.server 8778 --directory graph`
  or FastAPI StaticFiles). `<script type="module">` works in both.

## Task

1. Extract the inline JS into `graph/js/` ES modules along the seams that
   already exist in the code (read it first; likely: `state.js` shared
   state + META/COMPANIES/LINKS, `data.js` fetch/lazy-bulk, `network.js`
   SVG view + physics, `canvasview.js` index mode, `globe.js` MapLibre +
   terrain, `panel.js` detail panel + drawers, `search.js`, `api.js`,
   `main.js` bootstrap). Fewer, larger modules over many tiny ones — target
   6–10 files.
2. Extract CSS to `graph/css/app.css`.
3. Keep `window.graphState` exactly as-is (it is the smoke-test hook) and any
   other window-level hooks you find referenced by tests.
4. No renames of functions/vars beyond what module scoping forces. No "while
   I'm here" cleanups. Import/export wiring only.
5. `index.html` shrinks to markup + `<link>` + `<script type="module" src="js/main.js">`.

## Acceptance checks

- Serve the app; verify in browser (screenshot or DOM checks): globe renders,
  search focuses a company, cluster click opens the panel, network view
  renders and animates, index/canvas mode switches, DCF export downloads,
  terrain toggle unaffected.
- `window.graphState()` returns the same shape as before.
- `test_product_shell.py` and `test_map_api.py` still pass.
- No console errors on load in both serving modes (`:8778` static and `:8788`
  FastAPI).
- `wc -l graph/index.html` < 500.

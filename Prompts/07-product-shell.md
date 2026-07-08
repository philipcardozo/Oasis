# 07 — Product shell: nav, command bar, drawer, locked dark theme

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompt 06 (module split) done. Ponytail rules apply; no framework.

## Context

Vault note "02 - Roadmap and Missing Work", Stage 1 is the spec — read it
(vault: `~/Documents/Obsidian Vault/OASIS - Industry nodes/`; never read its
`Restricted information` folder). Summary of the spec:

- One stable workspace layout: left navigation, top command/search bar,
  central canvas, contextual right drawer, optional bottom strip.
- Top-level surfaces: `Map`, `Network`, `Research`, `Model`, `Maker`
  (Maker can be a disabled placeholder for now).
- Dark charcoal default (not pure black), laser-red accent used sparingly,
  neutral text, muted boundaries, strong selected state, restrained motion.
- No explanatory filler text on the canvas; no permanent legends.
- Definition of done: "the interface looks intentionally designed at rest";
  a first-time user knows where to search, where to look, where details open.

## Task

1. Restructure `graph/index.html` markup into the shell: left nav (icons +
   labels for the five surfaces), top command bar, canvas region hosting the
   existing three views, right drawer replacing the current side panel
   container, bottom strip collapsed by default.
2. Implement the theme as CSS custom properties in `graph/css/app.css`
   (`--bg`, `--surface`, `--text`, `--muted`, `--accent`, `--border`, ...).
   Map ALL existing hardcoded colors onto the variables — this is the hook
   the future Engine panel needs.
3. Command bar = the existing search, upgraded: focus with `Cmd/Ctrl-K` and
   `/`, arrow-key result navigation, Enter opens the object (reuse the
   existing search + focus functions from the module split — do not rewrite
   matching logic).
4. Surface switching maps to the existing mode switches (globe/network/index
   → Map/Network; Research and Model can point at the current detail-panel /
   DCF flows scoped to the selected object; placeholders are acceptable but
   must look deliberate, not broken).
5. Keep every existing feature reachable. If something has no home yet, put
   it in a `⋯` overflow menu rather than deleting it.

## Acceptance checks

- All prompt-06 acceptance behaviors still pass (globe, search, panel,
  network, DCF export, `window.graphState()`).
- `Cmd-K` focuses search from any surface; Esc closes drawer/overlays.
- No hardcoded hex colors left in inline styles or JS-injected styles for the
  shell (grep for `#0`–`#f` patterns in the shell code paths; chart/canvas
  drawing colors may stay for now).
- Screenshot each surface at 1440px and confirm: no dead whitespace bands, no
  overlapping panels, drawer opens over the canvas without reflowing the map.
- `test_product_shell.py` updated to assert the new shell landmarks exist
  (nav, command bar, drawer) and passes.

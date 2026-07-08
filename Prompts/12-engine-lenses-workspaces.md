# 12 — Engine panel, first Lenses, saved workspaces

Repo: `/Users/felipecardozo/Desktop/coding/Quant Learn/Oasis`. Requires
prompts 07–08. Ponytail rules apply; no framework.

## Context

Vault notes "02 - Roadmap" Stage 5 and "08 - Product Experience System" are
the spec. Summary: `Engine` = global appearance/behavior controls; `Lenses`
= task presets (named bundles of Engine + filter + surface state); `Maker`
(widget/export customization) is explicitly LATER — do not build it here.

## Task

1. **Engine panel** (right drawer tab or overlay from the left nav):
   - One `engineState` object persisted to localStorage; applied via the CSS
     custom properties from prompt 07 plus existing toggles.
   - Controls (bind to what already exists; add nothing speculative):
     accent color, contrast/theme intensity, node scale, line intensity,
     label depth (zoom threshold), motion/physics on-off, cluster on-off,
     terrain source toggle (from prompt 09), basemap style if >1 exists.
   - Reset-to-default button.
2. **Lenses**: a lens = named JSON `{engine, filters, surface}` snapshot.
   - Ship two built-ins: "Company research" (Map+drawer, filings/news
     visible, securities hidden) and "Security research" (securities visible,
     same-issuer edges highlighted). Hardcode as JSON presets.
   - User can "Save current as lens" → localStorage list; switching lenses
     applies atomically.
3. **Workspace export/import**: serialize `{engineState, lens, filters,
   selection, camera(map center/zoom or view mode)}` to a downloadable
   `.oasis.json`; import restores it. This file format is deliberately the
   seed of the vault Stage-6 manual-layer format — include
   `{"spec_version": 1, "kind": "workspace"}` header.
4. Keyboard: `Cmd-K` search (exists), `1..5` switch surfaces, `e` toggles
   Engine panel, `Esc` closes. Document in a `?` shortcut overlay (one small
   modal, plain HTML).

## Acceptance checks

- Change accent + node scale → reload → settings persist.
- Switch between the two lenses → filters and visibility change as specced;
  saving a custom lens and re-selecting it works after reload.
- Export workspace, hard-refresh (clear localStorage), import → view state
  (surface, filters, selection, camera) restored.
- All shortcuts work and don't fire while typing in inputs.
- Existing tests pass; add a `test_product_shell.py` assertion that built-in
  lens JSON validates (keys present, referenced filters exist).

# Map Slot Synchronization

Three server-persisted Map Studio slots per user, created transactionally on
registration (slot 1 = current default experience, active).

## Model
`{id, user_id, slot_number(1..3), name, description, basemap, config(JSON),
version, is_active, timestamps}`. `config` = `{layers, camera, conditions, prefs}`.

## Concurrency (optimistic)
Every write includes the `version` the client read. A mismatch returns **409**
`{error:"version_conflict", current_version}`. The client reloads, merges, or
intentionally replaces. No silent overwrite of newer data.

## Validation (never trust the client)
- `basemap` ∈ {standard, dark, satellite} (allowlist — no arbitrary style URLs).
- `layers` keys ∈ allowlist; `conditions` keys ∈ allowlist.
- `camera.center` within [-180,180]×[-90,90]; `zoom` 0–24, `bearing` ±360,
  `pitch` 0–85; `opacity` 0–1.
- Serialized config ≤ 64 KB (413 otherwise).
- Names/descriptions have angle brackets stripped (stored-XSS defense).
- Import requires `kind:"map_slot"` and re-validates.

## Offline → account migration
Local preferences remain usable before login. After login the client offers a
deliberate migration into a slot; cloud settings are never silently overwritten.
The Phase 0 preferred-vs-active basemap distinction is preserved.

## Operations
list · get · update · rename · reset · duplicate-to · activate · export · import.
All owner-only (session + CSRF + ownership).

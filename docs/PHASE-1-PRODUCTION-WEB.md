# Phase 1 — Secure Production Web Foundation

**Branch:** `phase1/production-web` · **Base:** Phase 0 merged at `408209b`
**Date:** 2026-07-23

Builds the secure, reproducible production-web foundation: authentication,
authorization, a transactional database, three synchronized Map Studio slots,
process isolation, containers, CI, security hardening, observability, and
backup/restore — without rewriting the Phase 0 app.

## Design in one page

A new `server/` package **composes** onto the existing app rather than replacing
it. `server.app:create_app()` builds a fresh FastAPI instance that reuses the
map_api routes (static catch-all kept last) and adds auth/map-slot/health routers
plus a security-middleware perimeter. Nothing mutates the shared `map_api.app`
singleton, so it composes cleanly per test and per worker.

```
Client ─► reverse proxy (TLS) ─► API (server.app)
                                   ├─ auth / sessions (argon2, cookie)
                                   ├─ map slots (owner-only, versioned)
                                   ├─ existing map_api reads (public)
                                   └─ existing map_api writes (auth+CSRF guard)
                                 ─► PostgreSQL (users, sessions, slots, jobs, audit)
                                 ─► Parquet/local (entity graph — unchanged)
Worker (server.worker) ─► queued jobs + scheduled refresh (ONLY external network)
```

## What Phase 1 delivers

- **Auth**: register, email verify, login, logout, logout-all, password reset/
  change, session list/revoke, account deletion. Argon2id hashing with
  rehash-on-login migration. Opaque server-side sessions in HttpOnly Secure
  cookies — **no tokens in localStorage**. Double-submit CSRF. Uniform responses
  resist user enumeration.
- **Authorization**: every route classified (`docs/AUTHORIZATION-MATRIX.md`). A
  global write-guard requires session + CSRF for all state-changing requests
  outside `/api/auth/*`, so the **existing** map_api write routes are protected
  without editing them. Map slots are owner-only with cross-user denial.
- **Database**: SQLAlchemy 2.0 models, repository layer (no SQL in handlers),
  Alembic migrations. SQLite for dev/test, PostgreSQL in secure modes. A
  `TZDateTime` decorator keeps timestamps timezone-aware on both.
- **Map slots**: exactly three per user, created transactionally on registration.
  Optimistic concurrency (version field → explicit 409). Allowlist + range
  validation; stored-XSS stripping. Export/import.
- **Process isolation**: `server.worker` is the only process that acquires
  external data; the API never does. DB-backed queue (Redis/RQ is the scale-up).
- **Config**: typed, validated, fail-fast in production; `.env.example`.
- **Containers**: multi-stage Dockerfile (non-root, healthcheck, no reload),
  `compose.yaml` (postgres + migrate + api + worker + Caddy).
- **Security**: rate limits, CSRF, explicit-origin CORS, trusted hosts, CSP
  (no wildcards), HSTS in secure modes.
- **Observability**: structured JSON logs, correlation IDs, secret redaction.
- **Backup/restore**: pg_dump/restore (SQLite copy in dev) + a drill that
  round-trips users and slots — a backup is not valid until restore succeeds.
- **Licensing gates**: Esri/yfinance/logos default OFF in production
  (`docs/LICENSING-GATES.md`).

## Real-browser map gate (REQUIRED, human-only)

The sandboxed preview browser cannot initialize MapLibre at all (a
dependency-free inline style never fires `style.load`), so automated map-tile
rendering cannot be verified here. Map **logic**, failure handling, and
preference persistence are covered by 8 deterministic Playwright tests. Before
any public deployment a human must confirm in a real browser: Standard/Dark/
Satellite render, switching works repeatedly, reload preserves the preferred
basemap, provider failure falls back without overwriting the preference, no
`unpkg.com` MapLibre request. Record browser+OS+results. **If Standard fails in a
real browser, stop and diagnose before deploying.**

## Test evidence

`pytest -q` → **107 passed, 1 skipped** (55 Phase 0 + 52 Phase 1).
Playwright → **15 passed**. Clean-venv install verified.

## Startup commands

```bash
# dev
python -m alembic upgrade head
uvicorn server.app:app --host 127.0.0.1 --port 8788

# staging (containers)
cp .env.example .env      # fill secrets
docker compose up --build

# worker
python -m server.worker
```

## Acceptance status

See `docs/PHASE-1-ACCEPTANCE.md` for the criterion-by-criterion checklist and
`docs/SECURITY-THREAT-MODEL.md`, `docs/DATABASE.md`, `docs/AUTHENTICATION.md`,
`docs/MAP-SLOT-SYNC.md`, `docs/DEPLOYMENT-STAGING.md`, `docs/BACKUP-RESTORE.md`,
`docs/OBSERVABILITY.md`, `docs/LICENSING-GATES.md`.

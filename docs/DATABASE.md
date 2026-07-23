# Database

**Transactional store:** PostgreSQL (staging/production), SQLite (dev/test).
Large analytical data stays in Parquet/local — it is NOT migrated to Postgres.

## Separation
```
PostgreSQL : users, sessions, email_tokens, organizations, org_memberships,
             map_slots, jobs, audit_events
Parquet    : entity graph, large read-mostly datasets, generated artifacts
Object store: exports, approved logos, large generated files
```

## Types
`TZDateTime` (TypeDecorator) stores UTC and always reads back timezone-aware, so
comparisons behave identically on SQLite (which drops tzinfo) and Postgres.

## Access boundaries
Route handlers never write SQL. They call the repository layer
(`server/repositories.py`) with a request-scoped session from `get_db`
(commit-on-success, rollback-on-error). `session_scope()` is the equivalent for
scripts/worker.

## Migrations (Alembic)
```bash
python -m alembic upgrade head        # apply
python -m server.migration_check      # verify deployed revision
python -m alembic downgrade base      # roll back
python -m alembic revision --autogenerate -m "msg"
```
- Versioned; env pulls the URL from validated config.
- CI validates empty-DB upgrade, exact revision, and downgrade.
- Application startup does NOT run migrations — the `migrate` service / an
  explicit step does, so production never silently runs destructive DDL.
- Migrations must stay backward-compatible for one release (rollback safety).

## Health
`readyz` checks DB connectivity + analytical store presence; never external.

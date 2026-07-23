# ADR-0010: Managed PostgreSQL

## Status: accepted

## Decision
Use Render PostgreSQL for public staging.

## Rationale
OASIS already targets PostgreSQL through SQLAlchemy and Alembic. Render
PostgreSQL keeps the staging database close to the API and worker services,
supports managed backups on paid plans, and avoids silently falling back to
SQLite in secure modes.

`render.yaml` injects the database connection as `OASIS_DATABASE_URL` and
`DATABASE_URL`; application validation rejects SQLite in staging/production.

Reference: https://render.com/docs/blueprint-spec

## Changes this if
Connection pooling, PITR retention, private networking requirements, or data
volume exceed the chosen Render plan.

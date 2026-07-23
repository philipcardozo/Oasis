# ADR-0003: Transactional database

## Status: accepted

## Decision
PostgreSQL for transactional data via SQLAlchemy 2.0 + Alembic. SQLite for
dev/test (same code). Parquet/local stores keep the entity graph.

## Rationale
Auth/slots/audit need ACID, concurrency, and constraints — Postgres. DuckDB/
Parquet remain superb for single-node analytics but have no multi-user write
story. Keeping both avoids migrating 14.6k-node analytical data pointlessly.

## Alternatives
- All-Postgres (incl. analytics): heavy, discards Parquet's read speed. Rejected.
- All-DuckDB: no concurrent multi-user writes. Rejected for transactional data.

## Changes this if
Multi-tenant analytical query load grows → consider Postgres read replicas or a
columnar warehouse; transactional store stays Postgres.

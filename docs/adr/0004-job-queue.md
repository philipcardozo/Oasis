# ADR-0004: Job queue

## Status: accepted

## Decision
DB-backed job table drained by a separate worker process (`server.worker`).

## Rationale
Lightest reliable option at current scale: no new infrastructure, transactional
with the app DB, idempotent, observable. The worker is the only process allowed
external network access (preserves the Phase 0 boundary).

## Alternatives
- Redis + RQ/Celery: warranted once job volume/concurrency grows; documented
  scale-up. Adds an operational dependency now for little benefit.
- Kafka/Redpanda: rejected — no demonstrated need.

## Changes this if
Job throughput or fan-out exceeds what `SELECT ... FOR UPDATE SKIP LOCKED` on
one Postgres handles comfortably → Redis-backed queue.

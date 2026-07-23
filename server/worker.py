"""Background worker: the ONLY process permitted to acquire external data.

Runs queued DB-backed jobs and scheduled refreshes. The API process never does
this work. A DB-backed queue is the lightest reliable option at current scale;
Redis/RQ is the documented scale-up. Idempotent, bounded, interruptible.

    python -m server.worker              # run the loop
    python -m server.worker --once       # drain the queue once and exit
"""
from __future__ import annotations

import argparse
import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import select

from server.config import get_settings
from server.db import session_scope
from server.models import Job, utcnow
from server.observability import configure_logging, log_event

log = logging.getLogger("oasis.worker")
_stop = False

# Job handlers. Each is idempotent and bounded; refresh handlers reuse the Phase 0
# controls (rate limit, quota, backoff) in refresh_financial_facts.
HANDLERS: dict[str, callable] = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


@handler("noop")
def _noop(payload: dict) -> dict:
    return {"echo": payload}


@handler("refresh_financial_facts")
def _refresh_facts(payload: dict) -> dict:
    # Bounded, opt-in acquisition. Runs the Phase 0 refresh with a small cap.
    import subprocess
    import sys

    n = int(payload.get("max_entities", 25))
    proc = subprocess.run(
        [sys.executable, "refresh_financial_facts.py", "--max-entities", str(n)],
        capture_output=True, text=True, timeout=1800,
    )
    return {"returncode": proc.returncode, "tail": proc.stdout[-500:]}


def _claim_next(db):
    job = db.scalar(
        select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
    ) if db.bind.dialect.name == "postgresql" else db.scalar(
        select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
    )
    if job:
        job.status = "running"
        job.started_at = utcnow()
        job.attempts += 1
    return job


def run_once() -> int:
    processed = 0
    while not _stop:
        with session_scope() as db:
            job = _claim_next(db)
            if not job:
                break
            jid, kind, payload, attempts, maxa = job.id, job.kind, dict(job.payload), job.attempts, job.max_attempts
        # Execute outside the claim transaction.
        try:
            fn = HANDLERS.get(kind)
            if not fn:
                raise ValueError(f"no handler for job kind {kind!r}")
            result = fn(payload)
            with session_scope() as db:
                j = db.get(Job, jid)
                j.status, j.result, j.finished_at = "done", result, utcnow()
        except Exception as exc:
            with session_scope() as db:
                j = db.get(Job, jid)
                if attempts >= maxa:
                    j.status, j.error, j.finished_at = "failed", str(exc)[:2000], utcnow()
                else:
                    j.status = "queued"  # retry with backoff on next pass
                    j.error = str(exc)[:2000]
            log_event(log, logging.WARNING, "job_failed", kind=kind, attempts=attempts)
        processed += 1
    return processed


def _install_signals():
    def _handle(_s, _f):
        global _stop
        _stop = True
        log.info("worker received shutdown signal; finishing current job")

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="drain the queue once and exit")
    p.add_argument("--poll", type=float, default=5.0, help="seconds between polls")
    args = p.parse_args()

    configure_logging()
    _install_signals()
    log.info("worker starting mode=%s", get_settings().mode)

    if args.once:
        n = run_once()
        log.info("processed %d job(s)", n)
        return 0

    while not _stop:
        run_once()
        if _stop:
            break
        time.sleep(args.poll)
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

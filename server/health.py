"""Liveness, readiness, and version endpoints. Minimal public disclosure.

Liveness never touches the DB or external services. Readiness checks the DB and
the analytical store but never contacts SEC or map providers.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Response

from server.db import db_healthy

router = APIRouter(tags=["health"])

_VERSION = os.environ.get("OASIS_BUILD_VERSION", "dev")
_COMMIT = os.environ.get("OASIS_BUILD_COMMIT") or os.environ.get("RENDER_GIT_COMMIT", "unknown")


@router.get("/healthz")
def liveness():
    return {"status": "ok"}


@router.get("/readyz")
def readiness(response: Response):
    from pathlib import Path

    checks = {
        "database": db_healthy(),
        "analytical_store": Path("data/store/nodes.parquet").exists() or Path("graph/data/universe_core.json").exists(),
    }
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "not_ready", "checks": checks}


@router.get("/version")
def version():
    return {"version": _VERSION, "commit": _COMMIT}

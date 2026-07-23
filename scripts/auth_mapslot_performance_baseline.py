#!/usr/bin/env python3
"""Measure local Phase 1 auth/session and map-slot latency.

The script uses a temporary SQLite database and the memory email backend. It
does not touch developer data or staging secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
sys.path.insert(0, str(ROOT))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def timed(fn: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    result = fn()
    return (time.perf_counter() - started) * 1000, result


def summarize(name: str, samples: list[dict[str, Any]], target_ms: float | None = None) -> dict[str, Any]:
    durations = [sample["duration_ms"] for sample in samples]
    out: dict[str, Any] = {
        "name": name,
        "samples": len(samples),
        "status_codes": sorted({sample["status_code"] for sample in samples}),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_bytes_min": min(sample["body_bytes"] for sample in samples),
        "body_bytes_max": max(sample["body_bytes"] for sample in samples),
    }
    if target_ms is not None:
        out["target_ms"] = target_ms
        out["target_met"] = out["p95_ms"] < target_ms
    return out


def configure_temp_app(tmpdir: Path):
    os.environ["OASIS_MODE"] = "development"
    os.environ["OASIS_DATABASE_URL"] = f"sqlite:///{tmpdir / 'auth-map-slot-perf.db'}"
    os.environ["OASIS_EMAIL_BACKEND"] = "memory"
    os.environ["OASIS_SESSION_SECRET"] = "test-secret-least-thirty-two-chars-long!!"

    from server import config as cfg
    from server import db as dbmod

    cfg.get_settings.cache_clear()
    dbmod.reset_engine_for_tests()

    from server.models import Base

    Base.metadata.create_all(dbmod.engine())

    from server import email as email_mod
    from server import middleware

    email_mod.SENT.clear()
    middleware._limiter._hits.clear()

    from fastapi.testclient import TestClient
    from server.app import create_app

    return TestClient(create_app())


def register_verify_login(client) -> tuple[str, str, dict[str, Any]]:
    from server import email as email_mod

    email = "perf-user@example.com"
    password = "correcthorsebattery"
    setup: dict[str, Any] = {}

    duration, response = timed(lambda: client.post("/api/auth/register", json={"email": email, "password": password}))
    setup["register_ms"] = round(duration, 3)
    setup["register_status"] = response.status_code

    token = email_mod.SENT[-1].text.split("token=")[1].split()[0]
    duration, response = timed(lambda: client.post("/api/auth/verify-email", json={"token": token}))
    setup["verify_email_ms"] = round(duration, 3)
    setup["verify_email_status"] = response.status_code

    duration, response = timed(lambda: client.post("/api/auth/login", json={"email": email, "password": password}))
    setup["login_ms"] = round(duration, 3)
    setup["login_status"] = response.status_code

    csrf = client.cookies.get("oasis_csrf") or ""
    setup["csrf_cookie_present"] = bool(csrf)
    setup["session_cookie_present"] = bool(client.cookies.get("oasis_session"))
    return email, csrf, setup


def measure_get(client, path: str, samples: int) -> list[dict[str, Any]]:
    out = []
    for _ in range(samples):
        duration, response = timed(lambda: client.get(path))
        out.append({"duration_ms": duration, "status_code": response.status_code, "body_bytes": len(response.content)})
    return out


def measure_slot_write(client, slot_id: str, csrf: str, samples: int) -> list[dict[str, Any]]:
    out = []
    basemaps = ["dark", "standard"]
    for i in range(samples):
        slot = client.get(f"/api/map-slots/{slot_id}").json()
        body = {"basemap": basemaps[i % len(basemaps)], "version": slot["version"]}
        duration, response = timed(
            lambda: client.put(f"/api/map-slots/{slot_id}", json=body, headers={"X-CSRF-Token": csrf})
        )
        out.append({"duration_ms": duration, "status_code": response.status_code, "body_bytes": len(response.content)})
    return out


def measure_slot_rename(client, slot_id: str, csrf: str, samples: int) -> list[dict[str, Any]]:
    out = []
    for i in range(samples):
        slot = client.get(f"/api/map-slots/{slot_id}").json()
        body = {"name": f"Perf View {i}", "version": slot["version"]}
        duration, response = timed(
            lambda: client.post(f"/api/map-slots/{slot_id}/rename", json=body, headers={"X-CSRF-Token": csrf})
        )
        out.append({"duration_ms": duration, "status_code": response.status_code, "body_bytes": len(response.content)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oasis-auth-map-slot-perf-") as tmp:
        client = configure_temp_app(Path(tmp))
        _, csrf, setup = register_verify_login(client)

        slots_response = client.get("/api/map-slots")
        slots = slots_response.json()["slots"]
        slot_id = slots[0]["id"]

        measurements = [
            summarize("session validation GET /api/auth/me", measure_get(client, "/api/auth/me", args.samples), 50),
            summarize("session list GET /api/auth/sessions", measure_get(client, "/api/auth/sessions", args.samples)),
            summarize("map-slot list GET /api/map-slots", measure_get(client, "/api/map-slots", args.samples), 100),
            summarize("map-slot read GET /api/map-slots/{id}", measure_get(client, f"/api/map-slots/{slot_id}", args.samples), 100),
            summarize("map-slot write PUT /api/map-slots/{id}", measure_slot_write(client, slot_id, csrf, args.samples), 200),
            summarize("map-slot rename POST /api/map-slots/{id}/rename", measure_slot_rename(client, slot_id, csrf, args.samples), 200),
            summarize("map-slot export GET /api/map-slots/{id}/export", measure_get(client, f"/api/map-slots/{slot_id}/export", args.samples)),
        ]

        csrf_duration, csrf_response = timed(lambda: client.post("/api/auth/logout"))

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "python": platform.python_version(),
        "database": "temporary sqlite",
        "samples_per_measurement": args.samples,
        "setup": setup,
        "default_map_slot_count": len(slots),
        "default_map_slot_numbers": [slot["slot_number"] for slot in slots],
        "measurements": measurements,
        "csrf_rejection": {
            "operation": "POST /api/auth/logout without X-CSRF-Token",
            "status_code": csrf_response.status_code,
            "duration_ms": round(csrf_duration, 3),
            "body_bytes": len(csrf_response.content),
        },
    }

    path = EVIDENCE / "06-local-auth-and-map-slots.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote auth/map-slot performance evidence to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate compact local performance evidence for OASIS.

This is not a load test. It records route inventory, schema-shaped API snapshots,
and repeatable local p50/p95 timings so Proxyman findings can be compared
against app-level evidence without committing huge payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"

SNAPSHOT_ENDPOINTS = [
    "/",
    "/index.html",
    "/data/universe_core.json",
    "/api/map/layers",
    "/api/bootstrap/signals",
    "/api/map/entities.geojson?bbox=-180,-90,180,90",
    "/api/map/relationships.geojson?bbox=-180,-90,180,90",
    "/api/universe/bulk",
    "/api/entity/GM",
    "/api/entity/GM/reverse-dcf",
    "/api/entity/GM/comps?cap=8",
    "/api/entity/GM/events",
    "/api/entity/GM/risk",
    "/api/data-quality/dashboard",
    "/api/reports/asset/asset%3Ademo-farm-iowa",
]

LATENCY_ENDPOINTS = SNAPSHOT_ENDPOINTS + [
    "/api/entity/BLK/dcf.xlsx?method=cash_flow",
]

INTERESTING_HEADERS = [
    "cache-control",
    "content-encoding",
    "content-length",
    "content-security-policy",
    "content-type",
    "etag",
    "referrer-policy",
    "x-content-type-options",
    "x-request-id",
]


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def route_inventory(app: Any) -> list[dict[str, Any]]:
    routes = []
    for route in app.routes:
        methods = sorted(m for m in getattr(route, "methods", []) if m not in {"HEAD", "OPTIONS"})
        routes.append(
            {
                "path": getattr(route, "path", None),
                "name": getattr(route, "name", None),
                "methods": methods,
                "kind": route.__class__.__name__,
            }
        )
    return sorted(routes, key=lambda r: (r["path"] or "", ",".join(r["methods"]), r["name"] or ""))


def describe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {
            "json_type": "object",
            "top_level_keys": sorted(str(k) for k in value.keys()),
        }
        counts = {}
        selected_scalars = {}
        for key, item in value.items():
            if isinstance(item, list):
                counts[str(key)] = len(item)
            elif isinstance(item, dict):
                counts[str(key)] = len(item)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                selected_scalars[str(key)] = item
        if counts:
            out["counts"] = counts
        if selected_scalars:
            out["selected_scalars"] = selected_scalars
        return out
    if isinstance(value, list):
        return {"json_type": "array", "count": len(value)}
    return {"json_type": type(value).__name__}


def snapshot_response(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path, headers={"accept-encoding": "gzip"})
    body = response.content
    item: dict[str, Any] = {
        "method": "GET",
        "path": path,
        "status_code": response.status_code,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "headers": {h: response.headers[h] for h in INTERESTING_HEADERS if h in response.headers},
    }
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type or path.endswith(".geojson"):
        try:
            item["json_shape"] = describe_json(response.json())
        except Exception as exc:
            item["json_shape_error"] = str(exc)
    return item


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


def measure_latency(client: TestClient, path: str, samples: int) -> dict[str, Any]:
    durations = []
    statuses = []
    body_bytes = []
    headers: dict[str, str] = {}
    for _ in range(samples):
        started = time.perf_counter()
        response = client.get(path, headers={"accept-encoding": "gzip"})
        durations.append((time.perf_counter() - started) * 1000)
        statuses.append(response.status_code)
        body_bytes.append(len(response.content))
        if not headers:
            headers = {h: response.headers[h] for h in INTERESTING_HEADERS if h in response.headers}
    return {
        "method": "GET",
        "path": path,
        "samples": samples,
        "status_codes": sorted(set(statuses)),
        "body_bytes_min": min(body_bytes),
        "body_bytes_max": max(body_bytes),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "headers": headers,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=7, help="samples per latency endpoint")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from map_api import app as map_app

    client = TestClient(map_app)
    captured_at = datetime.now(timezone.utc).isoformat()

    inventory: dict[str, Any] = {
        "captured_at": captured_at,
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "python": platform.python_version(),
        "map_api": route_inventory(map_app),
    }
    try:
        from server.app import create_app

        inventory["server_app"] = route_inventory(create_app())
    except Exception as exc:
        inventory["server_app_error"] = str(exc)

    snapshots = {
        "captured_at": captured_at,
        "commit": inventory["commit"],
        "snapshots": [snapshot_response(client, path) for path in SNAPSHOT_ENDPOINTS],
    }
    latency = {
        "captured_at": captured_at,
        "commit": inventory["commit"],
        "samples_per_endpoint": args.samples,
        "measurements": [measure_latency(client, path, args.samples) for path in LATENCY_ENDPOINTS],
    }

    write_json(EVIDENCE / "01-route-inventory.json", inventory)
    write_json(EVIDENCE / "02-golden-api-snapshots.json", snapshots)
    write_json(EVIDENCE / "07-local-api-latency.json", latency)
    print(f"Wrote performance evidence to {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


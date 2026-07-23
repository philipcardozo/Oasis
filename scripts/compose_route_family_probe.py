#!/usr/bin/env python3
"""Measure representative OASIS route families through compose HTTPS.

This complements route_family_performance_probe.py, which uses TestClient. The
compose probe intentionally stays read-mostly so it can run against staging
without creating reports, overrides, or other file-backed mutations.
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
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from urllib3.exceptions import InsecureRequestWarning


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
sys.path.insert(0, str(ROOT))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def percentile(values: list[float], pct: float) -> float:
    if len(values) <= 1:
        return values[0] if values else 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def timed(fn: Callable[[], requests.Response]) -> tuple[float, requests.Response]:
    started = time.perf_counter()
    response = fn()
    return (time.perf_counter() - started) * 1000, response


def compact_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": sorted(map(str, value.keys())),
            "counts": {
                str(k): len(v)
                for k, v in value.items()
                if isinstance(v, (list, dict))
            },
        }
    if isinstance(value, list):
        return {"type": "array", "count": len(value)}
    return {"type": type(value).__name__}


def response_shape(response: requests.Response) -> dict[str, Any] | None:
    ctype = response.headers.get("content-type", "")
    if "json" not in ctype and not response.url.endswith(".geojson"):
        return None
    try:
        return compact_shape(response.json())
    except Exception as exc:
        return {"error": type(exc).__name__}


def representative_specs() -> list[dict[str, Any]]:
    from route_family_performance_probe import probe_specs, representative_ids

    ids = representative_ids()
    specs = [spec for spec in probe_specs(ids) if spec["method"] == "GET"]
    specs.extend([
        {"name": "health", "method": "GET", "path": "/healthz", "template": "/healthz", "family": "health"},
        {"name": "readiness", "method": "GET", "path": "/readyz", "template": "/readyz", "family": "health"},
        {"name": "version", "method": "GET", "path": "/version", "template": "/version", "family": "health"},
        {"name": "map layers", "method": "GET", "path": "/api/map/layers", "template": "/api/map/layers", "family": "map API"},
        {"name": "map entities", "method": "GET", "path": "/api/map/entities.geojson", "template": "/api/map/entities.geojson", "family": "map API"},
        {"name": "map relationships", "method": "GET", "path": "/api/map/relationships.geojson", "template": "/api/map/relationships.geojson", "family": "map API"},
        {"name": "bootstrap signals", "method": "GET", "path": "/api/bootstrap/signals", "template": "/api/bootstrap/signals", "family": "bootstrap"},
        {"name": "universe core", "method": "GET", "path": "/data/universe_core.json", "template": "/data/universe_core.json", "family": "static data"},
        {"name": "companies geojson", "method": "GET", "path": "/data/companies.geojson", "template": "/data/companies.geojson", "family": "static data"},
        {"name": "entity details", "method": "GET", "path": "/api/entity/GM", "template": "/api/entity/{entity_id}", "family": "entity drawer/model"},
        {"name": "entity comps", "method": "GET", "path": "/api/entity/GM/comps", "template": "/api/entity/{entity_id}/comps", "family": "entity drawer/model"},
        {"name": "entity reverse dcf", "method": "GET", "path": "/api/entity/GM/reverse-dcf", "template": "/api/entity/{entity_id}/reverse-dcf", "family": "entity drawer/model"},
        {"name": "entity dcf workbook", "method": "GET", "path": "/api/entity/GM/dcf.xlsx?method=cash_flow", "template": "/api/entity/{entity_id}/dcf.xlsx", "family": "entity drawer/model"},
        {"name": "report preview", "method": "GET", "path": "/api/reports/entity/GM", "template": "/api/reports/{object_type}/{object_id}", "family": "reports"},
        {"name": "map slots unauthenticated", "method": "GET", "path": "/api/map-slots", "template": "/api/map-slots", "family": "auth/map slots", "expected_statuses": [401, 403]},
        {"name": "auth me unauthenticated", "method": "GET", "path": "/api/auth/me", "template": "/api/auth/me", "family": "auth/map slots", "expected_statuses": [401, 403]},
        {"name": "auth sessions unauthenticated", "method": "GET", "path": "/api/auth/sessions", "template": "/api/auth/sessions", "family": "auth/map slots", "expected_statuses": [401, 403]},
    ])
    seen = set()
    unique = []
    for spec in specs:
        key = (spec["method"], spec["template"], spec["path"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(spec)
    return unique


def measure(session: requests.Session, base_url: str, spec: dict[str, Any], samples: int) -> dict[str, Any]:
    durations = []
    statuses = []
    lengths = []
    headers = {}
    first_body = b""
    expected_statuses = set(spec.get("expected_statuses") or range(200, 300))
    for i in range(samples):
        duration, response = timed(lambda: session.request(spec["method"], base_url + spec["path"], timeout=30))
        durations.append(duration)
        statuses.append(response.status_code)
        lengths.append(len(response.content))
        if i == 0:
            first_body = response.content
            headers = {
                key: response.headers[key]
                for key in ("cache-control", "content-encoding", "content-length", "content-type", "etag")
                if key in response.headers
            }
            first_response = response
    status_set = set(statuses)
    ok = status_set.issubset(expected_statuses)
    out: dict[str, Any] = {
        "name": spec["name"],
        "method": spec["method"],
        "path": spec["path"],
        "template": spec["template"],
        "family": spec.get("family"),
        "samples": samples,
        "status_codes": sorted(status_set),
        "expected_statuses": sorted(expected_statuses),
        "ok": ok,
        "body_bytes_min": min(lengths),
        "body_bytes_max": max(lengths),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_sha256": hashlib.sha256(first_body).hexdigest(),
        "headers": headers,
    }
    shape = response_shape(first_response)
    if shape is not None:
        out["json_shape"] = shape
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost:8443")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--proxy-server", default="")
    parser.add_argument("--output-file", default="20-compose-route-family-probe.json")
    parser.add_argument("--verify-tls", action="store_true")
    args = parser.parse_args()

    if not args.verify_tls:
        warnings.simplefilter("ignore", InsecureRequestWarning)

    base_url = args.base_url.rstrip("/")
    session = requests.Session()
    session.trust_env = False
    session.verify = bool(args.verify_tls)
    session.headers.update({"User-Agent": "oasis-compose-route-family-probe"})
    if args.proxy_server:
        session.proxies.update({"http": args.proxy_server, "https": args.proxy_server})

    specs = representative_specs()
    measurements = [measure(session, base_url, spec, args.samples) for spec in specs]
    failures = [m for m in measurements if not m["ok"]]
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "python": platform.python_version(),
        "base_url": base_url,
        "transport": "HTTPS through compose reverse proxy",
        "proxy_server": args.proxy_server or None,
        "verify_tls": bool(args.verify_tls),
        "samples_per_route": args.samples,
        "measurement_count": len(measurements),
        "ok_count": len(measurements) - len(failures),
        "failure_count": len(failures),
        "families": sorted({m.get("family") for m in measurements if m.get("family")}),
        "measurements": measurements,
        "failures": failures,
        "verdict": "pass" if not failures else "investigate",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / args.output_file
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote compose route-family probe to {path}")
    print(json.dumps({"verdict": payload["verdict"], "measurement_count": len(measurements), "failure_count": len(failures)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

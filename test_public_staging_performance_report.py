"""Public-staging performance report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_public_staging_performance_report_passes_with_required_evidence(tmp_path):
    browser = tmp_path / "browser.json"
    preflight = tmp_path / "preflight.json"
    auth = tmp_path / "auth.json"
    route = tmp_path / "route.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    preflight.write_text(json.dumps({"verdict": "pass", "dns": {"duration_ms": 12.3}, "tls": {"duration_ms": 44.5}}))
    auth.write_text(json.dumps({
        "captured_at": "2026-07-25T00:00:00Z",
        "measurements": [
            {"name": "session validation GET /api/auth/me", "p50_ms": 5, "p95_ms": 10, "target_ms": 50, "target_met": True, "status_codes": [200]},
            {"name": "map-slot read GET /api/map-slots/{id}", "p50_ms": 8, "p95_ms": 20, "target_ms": 100, "target_met": True, "status_codes": [200]},
            {"name": "map-slot write PUT /api/map-slots/{id}", "p50_ms": 12, "p95_ms": 30, "target_ms": 200, "target_met": True, "status_codes": [200]},
        ],
    }))
    route.write_text(json.dumps({
        "captured_at": "2026-07-25T00:00:00Z",
        "verdict": "pass",
        "failure_count": 0,
        "measurements": [
            {"name": "entity comps", "family": "entity drawer/model", "method": "GET", "template": "/api/entity/{entity_id}/comps", "p50_ms": 100, "p95_ms": 150, "status_codes": [200], "ok": True},
        ],
    }))

    result = _run_report(browser, output, preflight=preflight, auth=auth, route=route)

    assert result.returncode == 0, result.stderr
    text = output.read_text()
    assert "Verdict: **pass**" in text
    assert "session validation GET /api/auth/me" in text
    assert "Preflight verdict: `pass`" in text


def test_public_staging_performance_report_fails_when_first_paint_loads_bulk(tmp_path):
    browser = tmp_path / "browser.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=True)))

    result = _run_report(browser, output)

    assert result.returncode == 1
    assert "first paint requested /api/universe/bulk" in output.read_text()


def _run_report(browser: Path, output: Path, *, preflight: Path | None = None, auth: Path | None = None, route: Path | None = None):
    cmd = [
        sys.executable,
        "scripts/public_staging_performance_report.py",
        "--browser-summary",
        str(browser),
        "--output",
        str(output),
    ]
    if preflight:
        cmd.extend(["--preflight", str(preflight)])
    if auth:
        cmd.extend(["--auth-map-slot", str(auth)])
    if route:
        cmd.extend(["--route-probe", str(route)])
    return subprocess.run(cmd, capture_output=True, text=True)


def _browser_summary(*, bulk: bool) -> dict:
    return {
        "capturedAt": "2026-07-25T00:00:00Z",
        "baseUrl": "https://staging.example.com",
        "proxyServer": "http://127.0.0.1:9090",
        "flows": {
            "26-public-staging-03-local-first-paint": {
                "flow": "cold first paint",
                "requestCount": 9,
                "resourceTransferKb": 350.5,
                "navigation": {"domContentLoadedMs": 300, "loadEventMs": 400},
                "requestedUniverseBulk": bulk,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": [],
                "harPath": "docs/evidence/performance/26-public-staging-03-local-first-paint.har",
            },
            "26-public-staging-05-local-search-intent": {
                "flow": "search intent and bulk load",
                "requestCount": 4,
                "resourceTransferKb": 200.0,
                "navigation": {"domContentLoadedMs": 250, "loadEventMs": 300},
                "requestedUniverseBulk": True,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": [],
                "harPath": "docs/evidence/performance/26-public-staging-05-local-search-intent.har",
            },
        },
    }

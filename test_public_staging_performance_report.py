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
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    summary = tmp_path / "performance-evidence-summary.json"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    direct = tmp_path / "direct-browser.json"
    direct.write_text(json.dumps(_browser_summary(bulk=False, proxy_server=None)))
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
    supplemental.write_text(json.dumps(_supplemental()))

    result = _run_report(browser, output, summary=summary, direct=direct, preflight=preflight, auth=auth, route=route, supplemental=supplemental)

    assert result.returncode == 0, result.stderr
    text = output.read_text()
    assert "Verdict: **pass**" in text
    assert "session validation GET /api/auth/me" in text
    assert "Preflight verdict: `pass`" in text
    data = json.loads(summary.read_text())
    assert data["verdict"] == "pass"
    assert data["browser"]["direct_comparison_present"] is True
    assert data["browser"]["direct_flows"][0]["bulk"] is False
    assert data["auth_map_slot"]["rows"][0]["p95_ms"] == 10
    assert len(data["supplemental"]["external_locations"]) == 2
    assert data["supplemental"]["runtime_resources"][0]["key"] == "api_cpu_percent"
    assert data["supplemental"]["web_vitals"][0]["key"] == "lcp_ms"


def test_public_staging_performance_report_fails_when_first_paint_loads_bulk(tmp_path):
    browser = tmp_path / "browser.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=True)))

    result = _run_report(browser, output)

    assert result.returncode == 1
    assert "browser first paint requested /api/universe/bulk" in output.read_text()


def test_public_staging_performance_report_requires_clean_direct_capture(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    direct.write_text(json.dumps(_browser_summary(bulk=True, proxy_server="http://127.0.0.1:9090")))

    result = _run_report(browser, output, direct=direct)

    assert result.returncode == 1
    text = output.read_text()
    assert "direct browser comparison unexpectedly records a proxy server" in text
    assert "direct browser first paint requested /api/universe/bulk" in text


def test_public_staging_performance_report_requires_two_external_locations(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    data = _supplemental()
    data["external_locations"] = data["external_locations"][:1]
    supplemental.write_text(json.dumps(data))

    result = _run_report(browser, output, supplemental=supplemental)

    assert result.returncode == 1
    assert "fewer than two external performance locations are recorded" in output.read_text()


def test_public_staging_performance_report_requires_runtime_resources(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    data = _supplemental()
    data["runtime_resources"]["worker_memory_mb"] = None
    supplemental.write_text(json.dumps(data))

    result = _run_report(browser, output, supplemental=supplemental)

    assert result.returncode == 1
    assert "runtime resource metric is missing: worker_memory_mb" in output.read_text()


def test_public_staging_performance_report_requires_good_web_vitals(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser.write_text(json.dumps(_browser_summary(bulk=False)))
    data = _supplemental()
    data["web_vitals"]["lcp_ms"] = 2501
    data["web_vitals"]["inp_ms"] = 0
    data["web_vitals"]["cls"] = None
    supplemental.write_text(json.dumps(data))

    result = _run_report(browser, output, supplemental=supplemental)

    assert result.returncode == 1
    text = output.read_text()
    assert "web vital metric exceeds good threshold: lcp_ms" in text
    assert "web vital metric is not positive: inp_ms" in text
    assert "web vital metric is missing: cls" in text


def _run_report(
    browser: Path,
    output: Path,
    *,
    summary: Path | None = None,
    direct: Path | None = None,
    preflight: Path | None = None,
    auth: Path | None = None,
    route: Path | None = None,
    supplemental: Path | None = None,
):
    cmd = [
        sys.executable,
        "scripts/public_staging_performance_report.py",
        "--browser-summary",
        str(browser),
        "--output",
        str(output),
    ]
    cmd.extend(["--summary-output", str(summary or output.with_name("performance-evidence-summary.json"))])
    if direct:
        cmd.extend(["--direct-summary", str(direct)])
    if preflight:
        cmd.extend(["--preflight", str(preflight)])
    if auth:
        cmd.extend(["--auth-map-slot", str(auth)])
    if route:
        cmd.extend(["--route-probe", str(route)])
    if supplemental:
        cmd.extend(["--supplemental", str(supplemental)])
    return subprocess.run(cmd, capture_output=True, text=True)


def _browser_summary(*, bulk: bool, proxy_server: str | None = "http://127.0.0.1:9090") -> dict:
    return {
        "capturedAt": "2026-07-25T00:00:00Z",
        "baseUrl": "https://staging.example.com",
        "proxyServer": proxy_server,
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


def _supplemental() -> dict:
    return {
        "input_captured_at": "2026-07-25T00:00:00Z",
        "base_url": "https://staging.example.com",
        "secret_free_evidence": True,
        "external_locations": [
            {
                "name": "us-east-probe",
                "region": "us-east",
                "dns_ms": 12.3,
                "tcp_ms": 20.1,
                "tls_ms": 44.5,
                "ttfb_ms": 90.0,
                "initial_transfer_kb": 350.5,
                "initial_request_count": 9,
                "map_initialization_ms": 650.0,
            },
            {
                "name": "us-west-probe",
                "region": "us-west",
                "dns_ms": 16.0,
                "tcp_ms": 33.0,
                "tls_ms": 55.0,
                "ttfb_ms": 120.0,
                "initial_transfer_kb": 352.0,
                "initial_request_count": 9,
                "map_initialization_ms": 700.0,
            },
        ],
        "app_layer": {
            "search": {"p50_ms": 35, "p95_ms": 80, "target_ms": None, "target_met": True},
            "comps": {"p50_ms": 100, "p95_ms": 150, "target_ms": 500, "target_met": True},
            "export_job_creation": {"p50_ms": 45, "p95_ms": 90, "target_ms": None, "target_met": True},
        },
        "runtime_resources": {
            "api_cpu_percent": 12.5,
            "api_memory_mb": 256,
            "worker_cpu_percent": 10.0,
            "worker_memory_mb": 220,
            "database_connections": 4,
            "queue_depth": 0,
            "error_rate": 0,
        },
        "web_vitals": {
            "lcp_ms": 1200,
            "inp_ms": 120,
            "cls": 0.02,
            "fcp_ms": 900,
            "ttfb_ms": 120,
            "tbt_ms": 30,
        },
    }

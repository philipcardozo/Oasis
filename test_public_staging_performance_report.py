"""Public-staging performance report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_public_staging_performance_report_passes_with_required_evidence(tmp_path):
    browser = tmp_path / "browser.json"
    preflight = tmp_path / "preflight.json"
    auth = tmp_path / "auth.json"
    route = tmp_path / "route.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    summary = tmp_path / "performance-evidence-summary.json"
    browser_data = _browser_summary(bulk=False)
    direct_data = _browser_summary(bulk=False, proxy_server=None)
    _write_hars(browser_data)
    _write_hars(direct_data)
    browser.write_text(json.dumps(browser_data))
    direct = tmp_path / "direct-browser.json"
    direct.write_text(json.dumps(direct_data))
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
    data = _browser_summary(bulk=True)
    _write_hars(data)
    browser.write_text(json.dumps(data))

    result = _run_report(browser, output)

    assert result.returncode == 1
    assert "browser first paint requested /api/universe/bulk" in output.read_text()


def test_public_staging_performance_report_requires_clean_direct_capture(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False)
    direct_data = _browser_summary(bulk=True, proxy_server="http://127.0.0.1:9090")
    _write_hars(browser_data)
    _write_hars(direct_data)
    browser.write_text(json.dumps(browser_data))
    direct.write_text(json.dumps(direct_data))

    result = _run_report(browser, output, direct=direct)

    assert result.returncode == 1
    text = output.read_text()
    assert "direct browser comparison unexpectedly records a proxy server" in text
    assert "direct browser first paint requested /api/universe/bulk" in text


def test_public_staging_performance_report_requires_local_proxyman_proxy(tmp_path):
    browser = tmp_path / "browser.json"
    output = tmp_path / "15-performance.md"
    data = _browser_summary(bulk=False, proxy_server="https://proxy.example.com:9090")
    _write_hars(data)
    browser.write_text(json.dumps(data))

    result = _run_report(browser, output)

    assert result.returncode == 1
    assert "browser Proxyman proxy is not a local explicit proxy URL" in output.read_text()


def test_public_staging_performance_report_rejects_local_or_mismatched_public_targets(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False, base_url="https://localhost:8443")
    direct_data = _browser_summary(bulk=False, proxy_server=None, base_url="https://staging.example.com")
    _write_hars(browser_data)
    _write_hars(direct_data)
    browser.write_text(json.dumps(browser_data))
    direct.write_text(json.dumps(direct_data))
    supplemental.write_text(json.dumps(_supplemental(base_url="https://127.0.0.1:8443")))

    result = _run_report(browser, output, direct=direct, supplemental=supplemental)

    assert result.returncode == 1
    text = output.read_text()
    assert "browser base URL is not public" in text
    assert "direct browser comparison base URL does not match proxied capture" in text
    assert "supplemental performance base URL is not public" in text
    assert "supplemental performance base URL does not match browser capture" in text


def test_public_staging_performance_report_rejects_reserved_documentation_targets(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False, base_url="https://staging.example.com")
    direct_data = _browser_summary(bulk=False, proxy_server=None, base_url="https://staging.example.com")
    _write_hars(browser_data)
    _write_hars(direct_data)
    browser.write_text(json.dumps(browser_data))
    direct.write_text(json.dumps(direct_data))
    supplemental.write_text(json.dumps(_supplemental(base_url="https://staging.example.com")))

    result = _run_report(browser, output, direct=direct, supplemental=supplemental)

    assert result.returncode == 1
    text = output.read_text()
    assert "browser base URL is a reserved documentation hostname" in text
    assert "direct browser base URL is a reserved documentation hostname" in text
    assert "supplemental performance base URL is a reserved documentation hostname" in text


def test_public_staging_performance_report_requires_all_public_browser_flows(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    output = tmp_path / "15-performance.md"
    proxied = _browser_summary(bulk=False)
    del proxied["flows"]["26-public-staging-14-local-report-preview"]
    direct_data = _browser_summary(bulk=False, proxy_server=None)
    del direct_data["flows"]["26-public-staging-13-local-data-quality-panel"]
    _write_hars(proxied)
    _write_hars(direct_data)
    browser.write_text(json.dumps(proxied))
    direct.write_text(json.dumps(direct_data))

    result = _run_report(browser, output, direct=direct)

    assert result.returncode == 1
    text = output.read_text()
    assert "browser capture missing required flow: report preview" in text
    assert "direct browser capture missing required flow: data quality panel" in text


def test_public_staging_performance_report_requires_har_paths(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    output = tmp_path / "15-performance.md"
    proxied = _browser_summary(bulk=False)
    proxied["flows"]["26-public-staging-03-local-first-paint"]["harPath"] = ""
    direct_data = _browser_summary(bulk=False, proxy_server=None)
    direct_data["flows"]["26-public-staging-04-local-reload"]["harPath"] = "tmp/reload.json"
    _write_hars(proxied)
    _write_hars(direct_data)
    browser.write_text(json.dumps(proxied))
    direct.write_text(json.dumps(direct_data))

    result = _run_report(browser, output, direct=direct)

    assert result.returncode == 1
    text = output.read_text()
    assert "browser capture HAR path is missing or invalid: 26-public-staging-03-local-first-paint" in text
    assert "direct browser capture HAR path is missing or invalid: 26-public-staging-04-local-reload" in text


def test_public_staging_performance_report_requires_har_files_to_exist(tmp_path):
    browser = tmp_path / "browser.json"
    output = tmp_path / "15-performance.md"
    data = _browser_summary(bulk=False)
    data["flows"]["26-public-staging-03-local-first-paint"]["harPath"] = "docs/evidence/performance/26-public-staging-missing-fixture.har"
    browser.write_text(json.dumps(data))

    result = _run_report(browser, output)

    assert result.returncode == 1
    assert "browser capture HAR path is missing or invalid: 26-public-staging-03-local-first-paint" in output.read_text()


def test_public_staging_performance_report_rejects_sensitive_urls(tmp_path):
    browser = tmp_path / "browser.json"
    direct = tmp_path / "direct-browser.json"
    output = tmp_path / "15-performance.md"
    proxied = _browser_summary(bulk=False)
    proxied["flows"]["26-public-staging-03-local-first-paint"]["sensitiveUrlCount"] = 1
    direct_data = _browser_summary(bulk=False, proxy_server=None)
    direct_data["flows"]["26-public-staging-04-local-reload"]["sensitiveUrlCount"] = 2
    _write_hars(proxied)
    _write_hars(direct_data)
    browser.write_text(json.dumps(proxied))
    direct.write_text(json.dumps(direct_data))

    result = _run_report(browser, output, direct=direct)

    assert result.returncode == 1
    text = output.read_text()
    assert "browser capture recorded sensitive URL query values" in text
    assert "direct browser capture recorded sensitive URL query values" in text


def test_public_staging_performance_report_requires_two_external_locations(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False)
    _write_hars(browser_data)
    browser.write_text(json.dumps(browser_data))
    data = _supplemental()
    data["external_locations"] = data["external_locations"][:1]
    supplemental.write_text(json.dumps(data))

    result = _run_report(browser, output, supplemental=supplemental)

    assert result.returncode == 1
    assert "fewer than two external performance locations are recorded" in output.read_text()


def test_public_staging_performance_report_rejects_placeholder_external_location_identity(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False)
    _write_hars(browser_data)
    browser.write_text(json.dumps(browser_data))
    data = _supplemental()
    data["external_locations"][0]["name"] = "replace-with-location-1"
    data["external_locations"][0]["region"] = "replace-with-region-1"
    supplemental.write_text(json.dumps(data))

    result = _run_report(browser, output, supplemental=supplemental)

    assert result.returncode == 1
    assert "external performance location identity is still a placeholder: replace-with-location-1" in output.read_text()


def test_public_staging_performance_report_requires_runtime_resources(tmp_path):
    browser = tmp_path / "browser.json"
    supplemental = tmp_path / "performance-supplemental.json"
    output = tmp_path / "15-performance.md"
    browser_data = _browser_summary(bulk=False)
    _write_hars(browser_data)
    browser.write_text(json.dumps(browser_data))
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
    browser_data = _browser_summary(bulk=False)
    _write_hars(browser_data)
    browser.write_text(json.dumps(browser_data))
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


def _write_hars(summary: dict) -> None:
    for flow in (summary.get("flows") or {}).values():
        path = str(flow.get("harPath") or "")
        if not path.startswith("docs/evidence/performance/") or not path.endswith(".har"):
            continue
        har = Path(path)
        har.parent.mkdir(parents=True, exist_ok=True)
        har.write_text(json.dumps({"log": {"version": "1.2", "entries": []}}))


def _browser_summary(
    *,
    bulk: bool,
    proxy_server: str | None = "http://127.0.0.1:9090",
    base_url: str = PUBLIC_BASE_URL,
) -> dict:
    flow_defs = [
        ("03-local-first-paint", "cold first paint", bulk),
        ("04-local-reload", "warm reload", False),
        ("05-local-search-intent", "search intent and bulk load", True),
        ("06-local-map-interactions", "Map Studio and basemap switching", False),
        ("07-local-dcf-download", "DCF workbook fetch", False),
        ("12-local-entity-drawer", "entity drawer hydration", True),
        ("13-local-data-quality-panel", "data quality panel", False),
        ("14-local-report-preview", "report preview", False),
    ]
    return {
        "capturedAt": "2026-07-25T00:00:00Z",
        "baseUrl": base_url,
        "proxyServer": proxy_server,
        "flows": {
            f"26-public-staging-{suffix}": {
                "flow": flow,
                "requestCount": 9,
                "resourceTransferKb": 350.5,
                "navigation": {"domContentLoadedMs": 300, "loadEventMs": 400},
                "requestedUniverseBulk": requested_bulk,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "sensitiveUrlCount": 0,
                "externalHosts": [],
                "harPath": f"docs/evidence/performance/26-public-staging-{suffix}.har",
            }
            for suffix, flow, requested_bulk in flow_defs
        },
    }


def _supplemental(*, base_url: str = PUBLIC_BASE_URL) -> dict:
    return {
        "input_captured_at": "2026-07-25T00:00:00Z",
        "base_url": base_url,
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

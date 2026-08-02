"""Public-staging browser/map report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.public_staging_browser_reports import build_payload, evaluate_browser_matrix, evaluate_map_provider


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_browser_reports_pass_with_complete_matrix_and_summary():
    summary = _summary()
    _write_hars(summary)
    payload = build_payload(_matrix(), summary, "matrix.json", "summary.json")

    assert payload["browser"]["verdict"] == "pass"
    assert payload["map_provider"]["verdict"] == "pass"


def test_browser_report_requires_mobile_availability_reason():
    matrix = _matrix()
    for item in matrix["browsers"]:
        if item["name"] == "mobile_safari":
            item["unavailable_reason"] = ""

    summary = _summary()
    _write_hars(summary)
    failures, _, _ = evaluate_browser_matrix(matrix, summary)

    assert "mobile_safari is unavailable without a reason" in failures


def test_browser_report_does_not_require_edge_or_brave():
    matrix = _matrix()
    matrix["browsers"] = [item for item in matrix["browsers"] if item["name"] != "edge_or_brave"]

    summary = _summary()
    _write_hars(summary)
    failures, _, _ = evaluate_browser_matrix(matrix, summary)

    assert not any("edge_or_brave" in failure for failure in failures)


def test_browser_report_rejects_first_paint_bulk():
    summary = _summary()
    summary["flows"]["26-public-staging-03-local-first-paint"]["requestedUniverseBulk"] = True
    _write_hars(summary)

    failures, _, _ = evaluate_browser_matrix(_matrix(), summary)

    assert "first paint requested /api/universe/bulk" in failures


def test_browser_report_rejects_local_or_mismatched_public_targets():
    matrix = _matrix()
    summary = _summary()
    matrix["base_url"] = "https://localhost:8443"
    summary["baseUrl"] = "https://staging.example.com"
    _write_hars(summary)

    payload = build_payload(matrix, summary, "matrix.json", "summary.json")

    assert payload["browser"]["verdict"] == "investigate"
    assert "browser matrix base URL is not public" in payload["browser"]["failures"]
    assert "browser matrix and HAR summary base URLs do not match" in payload["browser"]["failures"]


def test_browser_report_rejects_reserved_documentation_targets():
    matrix = _matrix()
    summary = _summary()
    matrix["base_url"] = "https://staging.example.com"
    summary["baseUrl"] = "https://staging.example.com"
    _write_hars(summary)

    payload = build_payload(matrix, summary, "matrix.json", "summary.json")

    assert payload["browser"]["verdict"] == "investigate"
    assert "browser matrix base URL is a reserved documentation hostname" in payload["browser"]["failures"]
    assert "browser HAR summary base URL is a reserved documentation hostname" in payload["browser"]["failures"]


def test_browser_report_rejects_template_marker_matrix():
    matrix = _matrix()
    matrix["not_public_staging_proof"] = True
    matrix["verdict"] = "operator_input_required"
    summary = _summary()
    _write_hars(summary)

    payload = build_payload(matrix, summary, "matrix.json", "summary.json")

    assert payload["browser"]["verdict"] == "investigate"
    assert "browser matrix is still marked not public-staging proof" in payload["browser"]["failures"]
    assert "browser matrix still requires operator input" in payload["browser"]["failures"]


def test_browser_report_rejects_placeholder_browser_fields_and_hosts():
    matrix = _matrix()
    matrix["browsers"][0]["browser_version"] = "<record exact browser version>"
    matrix["browsers"][0]["os"] = "<record OS>"
    matrix["browsers"][4]["unavailable_reason"] = "<required when available is false>"
    matrix["map_provider"]["approved_hosts"] = ["<record approved public map tile/style host>"]
    summary = _summary()
    _write_hars(summary)

    payload = build_payload(matrix, summary, "matrix.json", "summary.json")

    assert "chrome has placeholder browser field: browser_version" in payload["browser"]["failures"]
    assert "chrome has placeholder browser field: os" in payload["browser"]["failures"]
    assert "mobile_safari unavailable reason is still a placeholder" in payload["browser"]["failures"]
    assert any("approved map provider host is still a placeholder" in item for item in payload["map_provider"]["failures"])


def test_map_report_rejects_unexpected_external_hosts():
    summary = _summary()
    summary["flows"]["26-public-staging-06-map-interaction"]["externalHosts"].append("evil.example")
    _write_hars(summary)

    failures, _, _ = evaluate_map_provider(_matrix(), summary)

    assert "browser capture used unexpected external hosts: evil.example" in failures


def test_browser_report_rejects_missing_har_files():
    summary = _summary()
    summary["flows"]["26-public-staging-03-local-first-paint"]["harPath"] = "docs/evidence/performance/26-public-staging-browser-missing-fixture.har"

    failures, _, _ = evaluate_browser_matrix(_matrix(), summary)

    assert "browser capture HAR path is missing or invalid: 26-public-staging-03-local-first-paint" in failures


def test_browser_report_cli_writes_two_pass_markdown_files(tmp_path):
    matrix = tmp_path / "browser-matrix.json"
    summary = tmp_path / "browser-summary.json"
    browser_output = tmp_path / "07-browser-matrix.md"
    map_output = tmp_path / "08-map-provider-capture.md"
    summary_output = tmp_path / "browser-map-summary.json"
    summary_data = _summary()
    _write_hars(summary_data)
    matrix.write_text(json.dumps(_matrix()))
    summary.write_text(json.dumps(summary_data))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_browser_reports.py",
            f"--browser-matrix={matrix}",
            f"--browser-summary={summary}",
            f"--browser-output={browser_output}",
            f"--map-output={map_output}",
            f"--summary-output={summary_output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verdict: **pass**" in browser_output.read_text()
    assert "Verdict: **pass**" in map_output.read_text()
    data = json.loads(summary_output.read_text())
    assert data["browser"]["verdict"] == "pass"
    assert data["map_provider"]["verdict"] == "pass"
    assert data["map_provider"]["approved_hosts"] == ["tiles.openfreemap.org"]


def _write_hars(summary: dict) -> None:
    for flow in (summary.get("flows") or {}).values():
        path = str(flow.get("harPath") or "")
        if not path.startswith("docs/evidence/performance/") or not path.endswith(".har"):
            continue
        har = Path(path)
        har.parent.mkdir(parents=True, exist_ok=True)
        har.write_text(json.dumps({"log": {"version": "1.2", "entries": []}}))


def _checks() -> dict:
    return {
        "application_shell": True,
        "registration_login": True,
        "session_persistence": True,
        "no_reusable_local_storage_token": True,
        "standard_basemap": True,
        "dark_basemap": True,
        "satellite_disabled_or_failure": True,
        "geographic_features": True,
        "search": True,
        "entity_selection": True,
        "drawer_rail": True,
        "three_map_slots": True,
        "export_workflow": True,
        "password_reset": True,
        "logout": True,
        "responsive_layout": True,
        "keyboard_navigation": True,
        "basic_accessibility": True,
        "no_console_errors": True,
    }


def _matrix() -> dict:
    browsers = [
        ("chrome", "150.0", "macOS", "26.5.2", True, ""),
        ("edge_or_brave", "150.0", "macOS", "26.5.2", True, ""),
        ("firefox", "142.0", "macOS", "26.5.2", True, ""),
        ("safari_macos", "19.0", "macOS", "26.5.2", True, ""),
        ("mobile_safari", "", "iOS", "", False, "device unavailable for first public drill"),
        ("chrome_android", "", "Android", "", False, "device unavailable for first public drill"),
    ]
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "base_url": PUBLIC_BASE_URL,
        "not_public_staging_proof": False,
        "verdict": "pass",
        "browsers": [
            {
                "name": name,
                "browser_version": version,
                "os": os_name,
                "os_version": os_version,
                "available": available,
                "unavailable_reason": reason,
                "checks": _checks() if available else {},
            }
            for name, version, os_name, os_version, available, reason in browsers
        ],
        "map_provider": {
            "approved_hosts": ["tiles.openfreemap.org"],
            "checks": {
                "vendored_maplibre": True,
                "no_unpkg": True,
                "no_provider_credentials": True,
                "attribution_displayed": True,
                "standard_available": True,
                "disabled_providers_unused": True,
                "preferred_basemap_preserved_after_failure": True,
                "style_requests_expected": True,
                "tile_requests_expected": True,
                "terrain_requests_expected_or_disabled": True,
                "csp_ok": True,
                "cors_ok": True,
            },
        },
    }


def _summary() -> dict:
    return {
        "capturedAt": "2026-07-25T00:00:00Z",
        "baseUrl": PUBLIC_BASE_URL,
        "flows": {
            "26-public-staging-03-local-first-paint": {
                "flow": "cold first paint",
                "requestedUniverseBulk": False,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": [],
                "harPath": "docs/evidence/performance/26-public-staging-03-local-first-paint.har",
            },
            "26-public-staging-06-map-interaction": {
                "flow": "map interaction",
                "requestedUniverseBulk": False,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": ["tiles.openfreemap.org"],
                "harPath": "docs/evidence/performance/26-public-staging-06-map-interaction.har",
            },
        },
    }

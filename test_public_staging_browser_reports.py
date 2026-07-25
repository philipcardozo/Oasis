"""Public-staging browser/map report regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_browser_reports import build_payload, evaluate_browser_matrix, evaluate_map_provider


def test_browser_reports_pass_with_complete_matrix_and_summary():
    payload = build_payload(_matrix(), _summary(), "matrix.json", "summary.json")

    assert payload["browser"]["verdict"] == "pass"
    assert payload["map_provider"]["verdict"] == "pass"


def test_browser_report_requires_mobile_availability_reason():
    matrix = _matrix()
    for item in matrix["browsers"]:
        if item["name"] == "mobile_safari":
            item["unavailable_reason"] = ""

    failures, _, _ = evaluate_browser_matrix(matrix, _summary())

    assert "mobile_safari is unavailable without a reason" in failures


def test_browser_report_rejects_first_paint_bulk():
    summary = _summary()
    summary["flows"]["26-public-staging-03-local-first-paint"]["requestedUniverseBulk"] = True

    failures, _, _ = evaluate_browser_matrix(_matrix(), summary)

    assert "first paint requested /api/universe/bulk" in failures


def test_map_report_rejects_unexpected_external_hosts():
    summary = _summary()
    summary["flows"]["26-public-staging-06-map-interaction"]["externalHosts"].append("evil.example")

    failures, _, _ = evaluate_map_provider(_matrix(), summary)

    assert "browser capture used unexpected external hosts: evil.example" in failures


def test_browser_report_cli_writes_two_pass_markdown_files(tmp_path):
    matrix = tmp_path / "browser-matrix.json"
    summary = tmp_path / "browser-summary.json"
    browser_output = tmp_path / "07-browser-matrix.md"
    map_output = tmp_path / "08-map-provider-capture.md"
    summary_output = tmp_path / "browser-map-summary.json"
    matrix.write_text(json.dumps(_matrix()))
    summary.write_text(json.dumps(_summary()))

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


def _checks() -> dict:
    return {
        "application_shell": True,
        "registration_login": True,
        "session_persistence": True,
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
        "base_url": "https://staging.example.com",
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
        "baseUrl": "https://staging.example.com",
        "flows": {
            "26-public-staging-03-local-first-paint": {
                "flow": "cold first paint",
                "requestedUniverseBulk": False,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": [],
            },
            "26-public-staging-06-map-interaction": {
                "flow": "map interaction",
                "requestedUniverseBulk": False,
                "requestedUnpkg": False,
                "consoleErrors": [],
                "failedRequestCount": 0,
                "externalHosts": ["tiles.openfreemap.org"],
            },
        },
    }

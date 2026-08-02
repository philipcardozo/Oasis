"""Public-staging route-security report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_public_route_security_report_passes_with_complete_evidence(tmp_path):
    files = _write_inputs(tmp_path, include_auth=True)
    output = tmp_path / "09-route-security.md"
    summary = tmp_path / "route-security-summary.json"

    result = _run_report(files, output, summary)

    assert result.returncode == 0, result.stderr
    text = output.read_text()
    assert "Verdict: **pass**" in text
    assert "CSRF rejection status: `403`" in text
    assert "Cross-user slot denial status: `404`" in text
    data = json.loads(summary.read_text())
    assert data["verdict"] == "pass"
    assert data["auth_security"]["stale_conflict_status"] == 409
    assert data["auth_security"]["fourth_slot_create_status"] == 405
    assert data["auth_security"]["fourth_slot_import_status"] == 422
    assert data["inventory"]["class_summary"]["public-write-auth-flow-rate-limited"] == 5


def test_public_route_security_report_requires_auth_security_evidence(tmp_path):
    files = _write_inputs(tmp_path, include_auth=False)
    output = tmp_path / "09-route-security.md"
    summary = tmp_path / "route-security-summary.json"

    result = _run_report(files, output, summary)

    assert result.returncode == 1
    text = output.read_text()
    assert "Verdict: **investigate**" in text
    assert "auth/CSRF/cross-user security evidence is missing" in text
    assert json.loads(summary.read_text())["verdict"] == "investigate"


def test_public_route_security_report_rejects_local_or_mismatched_targets(tmp_path):
    files = _write_inputs(tmp_path, include_auth=True)
    route = json.loads(files["route_probe"].read_text())
    preflight = json.loads(files["preflight"].read_text())
    auth = json.loads(files["auth"].read_text())
    route["base_url"] = "https://localhost:8443"
    preflight["base_url"] = PUBLIC_BASE_URL
    auth["base_url"] = "https://other-staging.example.com"
    files["route_probe"].write_text(json.dumps(route))
    files["preflight"].write_text(json.dumps(preflight))
    files["auth"].write_text(json.dumps(auth))
    output = tmp_path / "09-route-security.md"
    summary = tmp_path / "route-security-summary.json"

    result = _run_report(files, output, summary)

    assert result.returncode == 1
    text = output.read_text()
    assert "public route probe base URL is not public" in text
    assert "public preflight base URL does not match route probe" in text
    assert "auth/security base URL does not match route probe" in text


def test_public_route_security_report_rejects_reserved_documentation_targets(tmp_path):
    files = _write_inputs(tmp_path, include_auth=True)
    for name in ("route_probe", "preflight", "auth"):
        data = json.loads(files[name].read_text())
        data["base_url"] = "https://staging.example.com"
        files[name].write_text(json.dumps(data))
    output = tmp_path / "09-route-security.md"
    summary = tmp_path / "route-security-summary.json"

    result = _run_report(files, output, summary)

    assert result.returncode == 1
    text = output.read_text()
    assert "public route probe base URL is a reserved documentation hostname" in text
    assert "public preflight base URL is a reserved documentation hostname" in text
    assert "auth/security base URL is a reserved documentation hostname" in text


def _run_report(files: dict[str, Path], output: Path, summary: Path):
    cmd = [
        sys.executable,
        "scripts/public_staging_route_security_report.py",
        "--route-probe",
        str(files["route_probe"]),
        "--preflight",
        str(files["preflight"]),
        "--inventory",
        str(files["inventory"]),
        "--output",
        str(output),
        "--summary-output",
        str(summary),
    ]
    if files.get("auth"):
        cmd.extend(["--auth-security", str(files["auth"])])
    return subprocess.run(cmd, capture_output=True, text=True)


def _write_inputs(tmp_path: Path, *, include_auth: bool) -> dict[str, Path]:
    route_probe = tmp_path / "25-public-route-family-probe.json"
    preflight = tmp_path / "00-public-staging-preflight.json"
    inventory = tmp_path / "route-authorization-inventory.json"
    auth = tmp_path / "27-public-auth-map-slots.json"
    route_probe.write_text(json.dumps({
        "captured_at": "2026-07-25T00:00:00Z",
        "base_url": PUBLIC_BASE_URL,
        "verdict": "pass",
        "failure_count": 0,
        "measurements": [
            _measurement("health", "/healthz", [200], True),
            _measurement("map slots unauthenticated", "/api/map-slots", [401], True),
            _measurement("auth me unauthenticated", "/api/auth/me", [401], True),
            _measurement("auth sessions unauthenticated", "/api/auth/sessions", [403], True),
        ],
    }))
    preflight.write_text(json.dumps({
        "captured_at": "2026-07-25T00:00:00Z",
        "base_url": PUBLIC_BASE_URL,
        "verdict": "pass",
        "endpoints": {
            "/index.html": {
                "headers": {
                    "content-security-policy": "default-src 'self'",
                    "strict-transport-security": "max-age=31536000",
                    "x-content-type-options": "nosniff",
                    "referrer-policy": "strict-origin",
                    "permissions-policy": "geolocation=()",
                }
            }
        },
    }))
    inventory.write_text(json.dumps({
        "generated_on": "2026-07-25",
        "inventories": [
            {
                "label": "staging-secure",
                "unique_method_paths": 92,
                "duplicate_method_paths": [],
                "docs_paths_present": [],
                "class_summary": {
                    "public-read": 61,
                    "owner-only-session-csrf": 6,
                    "public-write-auth-flow-rate-limited": 5,
                },
            }
        ],
    }))
    files = {"route_probe": route_probe, "preflight": preflight, "inventory": inventory}
    if include_auth:
        auth.write_text(json.dumps({
            "captured_at": "2026-07-25T00:00:00Z",
            "base_url": PUBLIC_BASE_URL,
            "verdict": "pass",
            "checks": {
                "csrf_rejection": {"status_code": 403},
                "cross_user_slot_read_denied": {"status_code": 404},
                "stale_version_conflict": {"status_code": 409},
                "default_map_slot_count": 3,
                "default_map_slot_numbers": [1, 2, 3],
                "fourth_slot_create_attempt": {"status_code": 405},
                "fourth_slot_import_attempt": {"status_code": 422},
            },
        }))
        files["auth"] = auth
    return files


def _measurement(name: str, template: str, status_codes: list[int], ok: bool) -> dict:
    return {
        "name": name,
        "family": "auth/map slots" if name != "health" else "health",
        "method": "GET",
        "template": template,
        "status_codes": status_codes,
        "ok": ok,
    }

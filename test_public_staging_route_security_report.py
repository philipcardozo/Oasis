"""Public-staging route-security report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_public_route_security_report_passes_with_complete_evidence(tmp_path):
    files = _write_inputs(tmp_path, include_auth=True)
    output = tmp_path / "09-route-security.md"

    result = _run_report(files, output)

    assert result.returncode == 0, result.stderr
    text = output.read_text()
    assert "Verdict: **pass**" in text
    assert "CSRF rejection status: `403`" in text
    assert "Cross-user slot denial status: `404`" in text


def test_public_route_security_report_requires_auth_security_evidence(tmp_path):
    files = _write_inputs(tmp_path, include_auth=False)
    output = tmp_path / "09-route-security.md"

    result = _run_report(files, output)

    assert result.returncode == 1
    text = output.read_text()
    assert "Verdict: **investigate**" in text
    assert "auth/CSRF/cross-user security evidence is missing" in text


def _run_report(files: dict[str, Path], output: Path):
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
        "base_url": "https://staging.example.com",
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
                "class_summary": {"public-read": 61, "owner-only-session-csrf": 6},
            }
        ],
    }))
    files = {"route_probe": route_probe, "preflight": preflight, "inventory": inventory}
    if include_auth:
        auth.write_text(json.dumps({
            "captured_at": "2026-07-25T00:00:00Z",
            "verdict": "pass",
            "checks": {
                "csrf_rejection": {"status_code": 403},
                "cross_user_slot_read_denied": {"status_code": 404},
                "stale_version_conflict": {"status_code": 409},
                "default_map_slot_count": 3,
                "default_map_slot_numbers": [1, 2, 3],
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

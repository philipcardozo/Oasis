"""Public-staging rate-limit evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_rate_limit_report import build_payload, template


def test_rate_limit_report_passes_for_single_replica_with_edge_controls():
    payload = build_payload(
        _evidence(),
        _route_security(),
        _preflight(),
        input_path="rate-limit.json",
        route_security_path="route-security.json",
        preflight_path="preflight.json",
    )

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_rate_limit_report_requires_shared_store_for_multiple_replicas():
    evidence = _evidence()
    evidence["deployment_shape"]["api_replicas"] = 2
    evidence["deployment_shape"]["shared_rate_limit_store"] = False

    payload = build_payload(
        evidence,
        _route_security(),
        _preflight(),
        input_path="rate-limit.json",
        route_security_path="route-security.json",
        preflight_path="preflight.json",
    )

    assert "deployment rate-limit shape check is not true: multi_replica_shared_store" in payload["failures"]
    assert "deployment rate-limit shape check is not true: no_unbounded_public_replica" in payload["failures"]


def test_rate_limit_report_accepts_multiple_replicas_with_shared_store():
    evidence = _evidence()
    evidence["deployment_shape"]["api_replicas"] = 2
    evidence["deployment_shape"]["shared_rate_limit_store"] = True
    evidence["deployment_shape"]["per_process_limiter_documented"] = False

    payload = build_payload(
        evidence,
        _route_security(),
        _preflight(),
        input_path="rate-limit.json",
        route_security_path="route-security.json",
        preflight_path="preflight.json",
    )

    assert payload["verdict"] == "pass"


def test_rate_limit_report_rejects_missing_edge_and_client_ip_checks():
    evidence = _evidence()
    evidence["edge_controls"]["waf_or_rate_rules_enabled"] = False
    evidence["client_ip"]["spoofed_forwarded_for_rejected_or_ignored"] = False

    payload = build_payload(
        evidence,
        _route_security(),
        _preflight(),
        input_path="rate-limit.json",
        route_security_path="route-security.json",
        preflight_path="preflight.json",
    )

    assert "edge rate-limit check is not true: waf_or_rate_rules_enabled" in payload["failures"]
    assert "client IP check is not true: spoofed_forwarded_for_rejected_or_ignored" in payload["failures"]


def test_rate_limit_report_rejects_missing_route_family_probe():
    evidence = _evidence()
    evidence["route_families"]["exports"]["tested"] = False
    evidence["route_families"]["exports"]["limit_exceeded_statuses"] = [200]

    payload = build_payload(
        evidence,
        _route_security(),
        _preflight(),
        input_path="rate-limit.json",
        route_security_path="route-security.json",
        preflight_path="preflight.json",
    )

    assert "route family rate-limit evidence is not proven: exports" in payload["failures"]


def test_rate_limit_report_cli_writes_pass_artifacts(tmp_path):
    evidence = tmp_path / "rate-limit-evidence.json"
    route_security = tmp_path / "route-security-summary.json"
    preflight = tmp_path / "00-public-staging-preflight.json"
    report = tmp_path / "18-rate-limiting.md"
    summary = tmp_path / "rate-limit-summary.json"
    evidence.write_text(json.dumps(_evidence()))
    route_security.write_text(json.dumps(_route_security()))
    preflight.write_text(json.dumps(_preflight()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_rate_limit_report.py",
            f"--input={evidence}",
            f"--route-security={route_security}",
            f"--preflight={preflight}",
            f"--output={report}",
            f"--summary-output={summary}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: **pass**" in report.read_text()
    assert json.loads(summary.read_text())["verdict"] == "pass"


def _evidence() -> dict:
    data = template()
    data["base_url"] = "https://staging.example.com"
    return data


def _route_security() -> dict:
    return {
        "verdict": "pass",
        "inventory": {
            "class_summary": {
                "public-write-auth-flow-rate-limited": 5,
            },
        },
    }


def _preflight() -> dict:
    return {
        "verdict": "pass",
        "url": {"scheme": "https"},
    }

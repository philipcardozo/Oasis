"""Public-staging failure-exercise evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_failure_exercises_report import build_payload, public_base_url_failures, template
from test_public_staging_browser_reports import _matrix as browser_matrix, _summary as browser_summary
from test_public_staging_email_delivery_report import (
    _auth_summary as email_auth_summary,
    _evidence as email_evidence,
    _infra_summary as email_infra_summary,
    _ops_summary as email_ops_summary,
)
from test_public_staging_ops_reports import _evidence as ops_evidence
from test_public_staging_storage_report import (
    _evidence as storage_evidence,
    _infra_summary as storage_infra_summary,
    _ops_summary as storage_ops_summary,
)

PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_failure_exercises_report_passes_with_complete_structured_evidence():
    payload = _payload()

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_failure_exercises_report_rejects_database_recovery_gaps():
    evidence = _evidence()
    evidence["database_interruption"]["readiness_fails"] = False
    evidence["database_interruption"]["no_data_corruption"] = False

    payload = _payload(evidence)

    assert "failure exercise database_interruption check is not true: readiness_fails" in payload["failures"]
    assert "failure exercise database_interruption check is not true: no_data_corruption" in payload["failures"]


def test_failure_exercises_report_rejects_local_public_target():
    evidence = _evidence()
    evidence["base_url"] = "https://localhost:8443"

    payload = _payload(evidence)

    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "failure exercise base URL is not a non-local public hostname" in payload["failures"]


def test_failure_exercises_report_rejects_reserved_documentation_target():
    evidence = _evidence()
    evidence["base_url"] = "https://staging.example.com"

    payload = _payload(evidence)

    assert "failure exercise base URL is a reserved documentation hostname" in payload["failures"]


def test_failure_exercises_report_rejects_reserved_browser_map_cross_check():
    browser_map = _browser_map_summary()
    browser_map["target"]["matrix_base_url"] = "https://staging.example.com"
    browser_map["target"]["summary_base_url"] = "https://staging.example.com"

    payload = build_payload(
        _evidence(),
        _ops_summary(),
        browser_map,
        _storage_summary(),
        _email_summary(),
        input_path="failure-exercises-evidence.json",
        ops_path="ops-evidence-summary.json",
        browser_map_path="browser-map-summary.json",
        storage_path="storage-summary.json",
        email_path="email-delivery-summary.json",
    )

    assert "failure exercise cross-check is not true: browser_map_failure_pass" in payload["failures"]


def test_failure_exercises_report_rejects_map_outage_gaps():
    evidence = _evidence()
    evidence["map_provider_outage"]["preferred_basemap_preserved"] = False
    evidence["map_provider_outage"]["retry_bounded"] = False

    payload = _payload(evidence)

    assert "failure exercise map_provider_outage check is not true: preferred_basemap_preserved" in payload["failures"]
    assert "failure exercise map_provider_outage check is not true: retry_bounded" in payload["failures"]


def test_failure_exercises_report_rejects_missing_cross_checks():
    payload = build_payload(
        _evidence(),
        None,
        None,
        None,
        None,
        input_path="failure-exercises-evidence.json",
        ops_path="ops-evidence-summary.json",
        browser_map_path="browser-map-summary.json",
        storage_path="storage-summary.json",
        email_path="email-delivery-summary.json",
    )

    assert "failure exercise cross-check is not true: ops_worker_summary_pass" in payload["failures"]
    assert "failure exercise cross-check is not true: browser_map_failure_pass" in payload["failures"]
    assert "failure exercise cross-check is not true: storage_failure_pass" in payload["failures"]
    assert "failure exercise cross-check is not true: email_failure_pass" in payload["failures"]


def test_failure_exercises_report_cli_writes_pass_artifacts(tmp_path):
    evidence = tmp_path / "failure-exercises-evidence.json"
    ops = tmp_path / "ops-evidence-summary.json"
    browser_map = tmp_path / "browser-map-summary.json"
    storage = tmp_path / "storage-summary.json"
    email = tmp_path / "email-delivery-summary.json"
    report = tmp_path / "21-failure-exercises.md"
    summary = tmp_path / "failure-exercises-summary.json"
    evidence.write_text(json.dumps(_evidence()))
    ops.write_text(json.dumps(_ops_summary()))
    browser_map.write_text(json.dumps(_browser_map_summary()))
    storage.write_text(json.dumps(_storage_summary()))
    email.write_text(json.dumps(_email_summary()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_failure_exercises_report.py",
            f"--input={evidence}",
            f"--ops-summary={ops}",
            f"--browser-map-summary={browser_map}",
            f"--storage-summary={storage}",
            f"--email-delivery-summary={email}",
            f"--output={report}",
            f"--summary-output={summary}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: **pass**" in report.read_text()
    assert json.loads(summary.read_text())["verdict"] == "pass"


def _payload(evidence: dict | None = None) -> dict:
    return build_payload(
        evidence or _evidence(),
        _ops_summary(),
        _browser_map_summary(),
        _storage_summary(),
        _email_summary(),
        input_path="failure-exercises-evidence.json",
        ops_path="ops-evidence-summary.json",
        browser_map_path="browser-map-summary.json",
        storage_path="storage-summary.json",
        email_path="email-delivery-summary.json",
    )


def _evidence() -> dict:
    data = template()
    data["base_url"] = PUBLIC_BASE_URL
    return data


def _ops_summary() -> dict:
    from scripts.public_staging_ops_reports import build_payload as build_ops_payload

    return build_ops_payload(ops_evidence())


def _browser_map_summary() -> dict:
    from scripts.public_staging_browser_reports import build_payload as build_browser_payload

    matrix = browser_matrix()
    summary = browser_summary()
    matrix["base_url"] = PUBLIC_BASE_URL
    summary["base_url"] = PUBLIC_BASE_URL
    return build_browser_payload(matrix, summary, "browser-matrix.json", "browser-summary.json")


def _storage_summary() -> dict:
    from scripts.public_staging_storage_report import build_payload as build_storage_payload

    return build_storage_payload(
        storage_evidence(),
        storage_infra_summary(),
        storage_ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )


def _email_summary() -> dict:
    from scripts.public_staging_email_delivery_report import build_payload as build_email_payload

    return build_email_payload(
        email_evidence(),
        email_auth_summary(),
        email_infra_summary(),
        email_ops_summary(),
        input_path="email-delivery-evidence.json",
        auth_path="auth-email-summary.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

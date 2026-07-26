"""Public-staging email-delivery evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_email_delivery_report import build_payload, template
from scripts.public_staging_auth_email_report import build_payload as build_auth_payload
from test_public_staging_auth_email_report import _auth
from test_public_staging_infra_reports import _image_manifest, _infra, _preflight, _render_deploy
from test_public_staging_ops_reports import _evidence as ops_evidence


def test_email_delivery_report_passes_with_complete_structured_evidence():
    payload = build_payload(
        _evidence(),
        _auth_summary(),
        _infra_summary(),
        _ops_summary(),
        input_path="email-delivery-evidence.json",
        auth_path="auth-email-summary.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_email_delivery_report_rejects_sender_domain_gap():
    evidence = _evidence()
    evidence["provider_configuration"]["dkim_configured"] = False
    evidence["provider_configuration"]["sender_domain_verified"] = False

    payload = build_payload(
        evidence,
        _auth_summary(),
        _infra_summary(),
        _ops_summary(),
        input_path="email-delivery-evidence.json",
        auth_path="auth-email-summary.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "email provider_configuration check is not true: dkim_configured" in payload["failures"]
    assert "email provider_configuration check is not true: sender_domain_verified" in payload["failures"]


def test_email_delivery_report_rejects_missing_failure_retry():
    evidence = _evidence()
    evidence["failure_handling"]["delivery_failure_retried_through_worker"] = False
    evidence["failure_handling"]["retry_bounded"] = False

    payload = build_payload(
        evidence,
        _auth_summary(),
        _infra_summary(),
        _ops_summary(),
        input_path="email-delivery-evidence.json",
        auth_path="auth-email-summary.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "email failure_handling check is not true: delivery_failure_retried_through_worker" in payload["failures"]
    assert "email failure_handling check is not true: retry_bounded" in payload["failures"]


def test_email_delivery_report_rejects_missing_cross_checks():
    payload = build_payload(
        _evidence(),
        None,
        None,
        None,
        input_path="email-delivery-evidence.json",
        auth_path="auth-email-summary.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "email cross-check is not true: auth_email_summary_pass" in payload["failures"]
    assert "email cross-check is not true: infra_email_summary_pass" in payload["failures"]
    assert "email cross-check is not true: ops_worker_retry_summary_pass" in payload["failures"]


def test_email_delivery_report_cli_writes_pass_artifacts(tmp_path):
    evidence = tmp_path / "email-delivery-evidence.json"
    auth = tmp_path / "auth-email-summary.json"
    infra = tmp_path / "infra-evidence-summary.json"
    ops = tmp_path / "ops-evidence-summary.json"
    report = tmp_path / "20-email-delivery.md"
    summary = tmp_path / "email-delivery-summary.json"
    evidence.write_text(json.dumps(_evidence()))
    auth.write_text(json.dumps(_auth_summary()))
    infra.write_text(json.dumps(_infra_summary()))
    ops.write_text(json.dumps(_ops_summary()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_email_delivery_report.py",
            f"--input={evidence}",
            f"--auth-email-summary={auth}",
            f"--infra-summary={infra}",
            f"--ops-summary={ops}",
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


def _auth_summary() -> dict:
    return build_auth_payload(_auth(), "27-public-auth-map-slots.json")


def _infra_summary() -> dict:
    from scripts.public_staging_infra_reports import build_payload as build_infra_payload

    return build_infra_payload(_infra(), _preflight(), _render_deploy(), _image_manifest())


def _ops_summary() -> dict:
    from scripts.public_staging_ops_reports import build_payload as build_ops_payload

    return build_ops_payload(ops_evidence())

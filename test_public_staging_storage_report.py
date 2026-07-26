"""Public-staging object-storage evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_storage_report import build_payload, template
from test_public_staging_infra_reports import _image_manifest, _infra, _preflight, _render_deploy
from test_public_staging_ops_reports import _evidence as ops_evidence


def test_storage_report_passes_with_complete_structured_evidence():
    payload = build_payload(
        _evidence(),
        _infra_summary(),
        _ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_storage_report_rejects_public_bucket_listing():
    evidence = _evidence()
    evidence["access_controls"]["public_bucket_listing_disabled"] = False

    payload = build_payload(
        evidence,
        _infra_summary(),
        _ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "storage access_controls check is not true: public_bucket_listing_disabled" in payload["failures"]


def test_storage_report_rejects_missing_content_type_validation():
    evidence = _evidence()
    evidence["validation_limits"]["content_type_validation"] = False
    evidence["validation_limits"]["allowed_content_types"] = []

    payload = build_payload(
        evidence,
        _infra_summary(),
        _ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "storage validation_limits check is not true: content_type_validation" in payload["failures"]
    assert "storage validation_limits check is not true: allowed_content_type_count_positive" in payload["failures"]


def test_storage_report_rejects_unavailable_storage_partial_output():
    evidence = _evidence()
    evidence["failure_behavior"]["partial_output_not_offered"] = False

    payload = build_payload(
        evidence,
        _infra_summary(),
        _ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "storage failure_behavior check is not true: partial_output_not_offered" in payload["failures"]


def test_storage_report_rejects_missing_cross_check_summaries():
    payload = build_payload(
        _evidence(),
        None,
        None,
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )

    assert "storage cross-check is not true: infra_storage_summary_pass" in payload["failures"]
    assert "storage cross-check is not true: ops_storage_summary_pass" in payload["failures"]


def test_storage_report_cli_writes_pass_artifacts(tmp_path):
    evidence = tmp_path / "storage-evidence.json"
    infra = tmp_path / "infra-evidence-summary.json"
    ops = tmp_path / "ops-evidence-summary.json"
    report = tmp_path / "19-object-storage.md"
    summary = tmp_path / "storage-summary.json"
    evidence.write_text(json.dumps(_evidence()))
    infra.write_text(json.dumps(_infra_summary()))
    ops.write_text(json.dumps(_ops_summary()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_storage_report.py",
            f"--input={evidence}",
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


def _infra_summary() -> dict:
    from scripts.public_staging_infra_reports import build_payload as build_infra_payload

    return build_infra_payload(_infra(), _preflight(), _render_deploy(), _image_manifest())


def _ops_summary() -> dict:
    from scripts.public_staging_ops_reports import build_payload as build_ops_payload

    return build_ops_payload(ops_evidence())

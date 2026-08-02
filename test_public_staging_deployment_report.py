"""Public-staging deployment automation evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.public_staging_deployment_report import build_payload, public_base_url_failures, template


DIGEST = "sha256:" + "d" * 64
IMAGE = f"ghcr.io/example/oasis@{DIGEST}"
COMMIT = "abcdef1234567890abcdef1234567890abcdef12"
PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"
RUN_ID = "9876543210"


def test_deployment_automation_report_passes_for_protected_successful_run():
    payload = build_payload(
        workflow_text=_workflow_text(),
        run=_run(),
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_deployment_automation_report_rejects_unprotected_or_failed_run():
    run = _run()
    run["protected_environment"] = False
    run["steps"]["Python tests"] = "failure"

    payload = build_payload(
        workflow_text=_workflow_text(),
        run=run,
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )

    assert payload["verdict"] == "investigate"
    assert "run check is not true: protected_environment" in payload["failures"]
    assert "run check is not true: python_tests" in payload["failures"]


def test_deployment_automation_report_rejects_artifact_mismatch():
    manifest = _image_manifest()
    manifest["ci"]["run_id"] = "different"
    render_deploy = _render_deploy()
    render_deploy["image_url"] = f"ghcr.io/example/oasis@sha256:{'e' * 64}"
    preflight = _preflight()
    preflight["endpoints"]["/version"]["body_text"] = '{"commit":"different"}'

    payload = build_payload(
        workflow_text=_workflow_text(),
        run=_run(),
        image_manifest=manifest,
        render_deploy=render_deploy,
        preflight=preflight,
        workflow_path=".github/workflows/deploy.yml",
    )

    assert "artifacts check is not true: workflow_run_matches_manifest" in payload["failures"]
    assert "artifacts check is not true: render_image_matches_manifest" in payload["failures"]
    assert "artifacts check is not true: preflight_version_matches_commit" in payload["failures"]


def test_deployment_automation_report_rejects_local_preflight_target():
    preflight = _preflight()
    preflight["base_url"] = "https://127.0.0.1:8443"
    preflight["url"]["hostname"] = "127.0.0.1"

    payload = build_payload(
        workflow_text=_workflow_text(),
        run=_run(),
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=preflight,
        workflow_path=".github/workflows/deploy.yml",
    )

    assert public_base_url_failures(_preflight()) == []
    assert "public preflight base URL is not a non-local public hostname" in public_base_url_failures(preflight)
    assert "artifacts check is not true: public_preflight_target" in payload["failures"]


def test_deployment_automation_report_rejects_reserved_preflight_target():
    preflight = _preflight()
    preflight["base_url"] = "https://staging.example.com"
    preflight["url"]["hostname"] = "staging.example.com"

    payload = build_payload(
        workflow_text=_workflow_text(),
        run=_run(),
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=preflight,
        workflow_path=".github/workflows/deploy.yml",
    )

    assert "public preflight base URL is a reserved documentation hostname" in public_base_url_failures(preflight)
    assert "artifacts check is not true: public_preflight_target" in payload["failures"]


def test_deployment_automation_report_rejects_template_run_identity():
    payload = build_payload(
        workflow_text=_workflow_text(),
        run=template(),
        image_manifest={**_image_manifest(), "commit": "abcdef123456"},
        render_deploy={**_render_deploy(), "commit": "abcdef123456"},
        preflight={**_preflight(), "commit": "abcdef123456"},
        workflow_path=".github/workflows/deploy.yml",
    )

    assert "run check is not true: run_identity_real" in payload["failures"]
    assert "run check is not true: run_commit_full_sha" in payload["failures"]
    assert "artifacts check is not true: commit_full_sha" in payload["failures"]


def test_deployment_automation_report_rejects_missing_workflow_controls():
    payload = build_payload(
        workflow_text="name: Deploy\n",
        run=_run(),
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )

    assert any(item.startswith("workflow check is not true:") for item in payload["failures"])


def test_deployment_automation_report_requires_config_contract_workflow_gate():
    workflow_text = _workflow_text().replace("scripts/public_staging_config_contract.py", "scripts/removed_config_gate.py")

    payload = build_payload(
        workflow_text=workflow_text,
        run=_run(),
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )

    assert "workflow check is not true: config_contract" in payload["failures"]


def test_deployment_automation_report_requires_config_contract_run_step():
    run = _run()
    run["steps"]["Validate public staging config contract"] = "skipped"

    payload = build_payload(
        workflow_text=_workflow_text(),
        run=run,
        image_manifest=_image_manifest(),
        render_deploy=_render_deploy(),
        preflight=_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )

    assert "run check is not true: config_contract" in payload["failures"]


def test_deployment_automation_cli_writes_report_and_summary(tmp_path):
    run_path = tmp_path / "deployment-automation-run.json"
    manifest_path = tmp_path / "01-image-manifest.json"
    deploy_path = tmp_path / "02-render-deploy.json"
    preflight_path = tmp_path / "00-public-staging-preflight.json"
    report_path = tmp_path / "16-deployment-automation.md"
    summary_path = tmp_path / "deployment-automation-summary.json"

    run_path.write_text(json.dumps(_run()))
    manifest_path.write_text(json.dumps(_image_manifest()))
    deploy_path.write_text(json.dumps(_render_deploy()))
    preflight_path.write_text(json.dumps(_preflight()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_deployment_report.py",
            f"--run-evidence={run_path}",
            f"--image-manifest={manifest_path}",
            f"--render-deploy={deploy_path}",
            f"--preflight={preflight_path}",
            f"--output={report_path}",
            f"--summary-output={summary_path}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: **pass**" in report_path.read_text()
    assert json.loads(summary_path.read_text())["verdict"] == "pass"


def test_deployment_automation_template_is_non_secret_shape():
    data = template()

    assert data["workflow"] == "Deploy"
    assert data["environment"] == "staging"
    assert data["production_deploy"] is False
    assert all(value == "success" for value in data["steps"].values())


def _workflow_text() -> str:
    return Path(".github/workflows/deploy.yml").read_text()


def _run() -> dict:
    run = template()
    run["commit"] = COMMIT
    run["captured_at"] = "2026-07-30T12:34:56Z"
    run["run_id"] = RUN_ID
    run["run_attempt"] = "1"
    return run


def _image_manifest() -> dict:
    return {
        "verdict": "pass",
        "commit": COMMIT,
        "image": IMAGE,
        "image_name": "ghcr.io/example/oasis",
        "digest": DIGEST,
        "registry": "ghcr.io",
        "architecture": "linux/amd64",
        "checks": {
            "migration_validation": "pass",
            "python_tests": "pass",
            "playwright_tests": "pass",
            "image_scan": "pass",
            "sbom": "present",
            "provenance": "present",
        },
        "ci": {
            "workflow": "Deploy",
            "run_id": RUN_ID,
            "run_attempt": "1",
        },
    }


def _render_deploy() -> dict:
    return {
        "verdict": "pass",
        "commit": COMMIT,
        "image_url": IMAGE,
        "deployments": [
            {"role": "api", "ok": True, "terminal": True, "deploy_id": "dep-api", "service_id_sha256_16": "a" * 16},
            {"role": "worker", "ok": True, "terminal": True, "deploy_id": "dep-worker", "service_id_sha256_16": "b" * 16},
        ],
    }


def _preflight() -> dict:
    return {
        "verdict": "pass",
        "commit": COMMIT,
        "base_url": PUBLIC_BASE_URL,
        "url": {"scheme": "https", "hostname": "staging.oasis-private-beta.com", "port": 443},
        "endpoints": {
            "/version": {
                "ok": True,
                "status": 200,
                "body_text": f'{{"commit":"{COMMIT}"}}',
            }
        },
    }

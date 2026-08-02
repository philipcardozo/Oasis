"""Public-staging setup checklist regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_readiness import GITHUB_STAGING_SECRETS, GITHUB_STAGING_VARIABLES
from scripts.public_staging_readiness import GCP_GITHUB_STAGING_SECRETS, GCP_GITHUB_STAGING_VARIABLES
from scripts.public_staging_setup_checklist import build_payload, markdown


def test_setup_checklist_contains_required_github_inputs_and_no_secret_values():
    payload = build_payload(captured_at="2026-07-30T00:00:00Z")

    assert payload["verdict"] == "operator_setup_required"
    assert payload["not_public_staging_proof"] is True
    assert payload["github_environment"]["required_variables"] == GITHUB_STAGING_VARIABLES
    assert payload["github_environment"]["required_secrets"] == GITHUB_STAGING_SECRETS
    text = json.dumps(payload)
    assert "RENDER_API_KEY" in text
    assert "<render_api_key>" in text
    assert "ghp_" not in text
    assert "Bearer " not in text


def test_setup_checklist_markdown_is_generated_and_secret_free():
    text = markdown(build_payload(captured_at="2026-07-30T00:00:00Z"))

    assert "# Public Staging Setup Checklist" in text
    assert "Verdict: **operator_setup_required**" in text
    assert "This generated checklist is not public-staging proof" in text
    assert "gh variable set STAGING_URL --env staging" in text
    assert "gh secret set RENDER_API_KEY --env staging" in text
    assert "OASIS_STORAGE_BACKEND=s3" in text
    assert "AWS_SECRET_ACCESS_KEY=<least-privilege-r2-secret-key>" in text
    assert "public_staging_config_contract.py" in text
    assert "public_staging_browser_matrix_template.py" in text
    assert "public_staging_playwright_report.py" in text
    assert "public_staging_full_verification.py" in text
    assert "OASIS_PUBLIC_TESTER_A_PASSWORD" in text
    assert "OASIS_PUBLIC_TESTER_A_RESET_PASSWORD" in text
    assert "OASIS_PUBLIC_TESTER_B_PASSWORD" in text
    assert "OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD" in text
    assert "Chrome, Firefox, and Safari" in text
    assert "password123" not in text


def test_setup_checklist_gcp_mode_uses_gcp_variables_without_render_secrets():
    payload = build_payload(provider="gcp", captured_at="2026-08-02T00:00:00Z")
    text = markdown(payload)

    assert payload["deploy_provider"] == "gcp"
    assert payload["github_environment"]["required_variables"] == GCP_GITHUB_STAGING_VARIABLES
    assert payload["github_environment"]["required_secrets"] == GCP_GITHUB_STAGING_SECRETS
    assert "GCP_PROJECT_ID" in text
    assert "GCP_CLOUD_RUN_WORKER_POOL" in text
    assert "Workload Identity Federation" in text
    assert "Cloud Storage bucket" in text
    assert "RENDER_API_KEY" not in text
    assert "CF-Access-Client-Id" not in text


def test_setup_checklist_cli_writes_markdown_and_json(tmp_path):
    md = tmp_path / "setup.md"
    js = tmp_path / "setup.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_setup_checklist.py",
            f"--output={md}",
            f"--json-output={js}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Public Staging Setup Checklist" in md.read_text()
    assert json.loads(js.read_text())["verdict"] == "operator_setup_required"

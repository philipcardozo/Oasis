"""Public-staging full verification runner regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_full_verification import build_steps, public_base_url_failures

PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_full_verification_plan_covers_required_public_gates():
    steps = build_steps(
        base_url=PUBLIC_BASE_URL,
        proxy_server="http://127.0.0.1:9090",
        expect_commit="abc123",
        samples=3,
    )
    keys = [step.key for step in steps]

    assert "config_contract" in keys
    assert "readiness" in keys
    assert "preflight" in keys
    assert "route_family_probe" in keys
    assert "auth_map_slots_probe" in keys
    assert "public_playwright" in keys
    assert "proxyman_browser_capture" in keys
    assert "direct_browser_capture" in keys
    assert "route_security_report" in keys
    assert "ops_reports" in keys
    assert "storage_report" in keys
    assert "failure_exercises_report" in keys
    assert "final_gate_audit" not in keys

    command_text = "\n".join(" ".join(step.command) for step in steps)
    assert "/healthz" not in command_text  # covered by the preflight helper, not hand-rolled curl
    assert "public_staging_preflight.py" in command_text
    assert "public_staging_config_contract.py" in command_text
    assert "compose_route_family_probe.py" in command_text
    assert "public_staging_auth_map_slots_probe.py" in command_text
    assert "public_staging_playwright_report.py" in command_text
    assert "browser_performance_capture.js" in command_text
    assert "--proxy-server=http://127.0.0.1:9090" in command_text
    assert "public_staging_ops_reports.py" in command_text


def test_full_verification_gcp_plan_omits_cloudflare_access_headers():
    steps = build_steps(
        base_url="https://oasis-staging-abc-ue.a.run.app",
        proxy_server="http://127.0.0.1:9090",
        expect_commit="abc123",
        samples=3,
        provider="gcp",
    )
    command_text = "\n".join(" ".join(step.command) for step in steps)

    assert "public_staging_config_contract.py --provider=gcp" in command_text
    assert "public_staging_setup_checklist.py --provider=gcp" in command_text
    assert "CF-Access-Client-Id" not in command_text
    assert "OASIS_CF_ACCESS_CLIENT_SECRET" not in command_text


def test_full_verification_dry_run_writes_secret_free_plan(tmp_path):
    output = tmp_path / "run.json"
    markdown = tmp_path / "run.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_full_verification.py",
            f"--base-url={PUBLIC_BASE_URL}",
            "--proxy-server=http://127.0.0.1:9090",
            "--expect-commit=abc123",
            "--dry-run",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text())
    text = output.read_text() + markdown.read_text()
    assert payload["verdict"] == "planned"
    assert payload["dry_run"] is True
    assert payload["not_public_staging_proof"] is True
    assert payload["results"] == []
    assert "Public Staging Full Verification Plan" in text
    assert "failure_exercises_report" in text
    assert "final_gate_audit" not in text
    assert "APPROVED FOR CONTROLLED PRIVATE BETA" not in text
    assert "Bearer " not in text
    assert "ghp_" not in text
    assert "password123" not in text


def test_full_verification_rejects_local_base_url_and_allows_dry_run_placeholder():
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "base URL must use https" in public_base_url_failures("http://staging.example.com")
    assert "base URL must be a non-local public hostname" in public_base_url_failures("https://localhost:8443")
    assert "base URL must not be a reserved documentation hostname" in public_base_url_failures("https://staging.example.com")
    assert public_base_url_failures("https://staging.<approved-domain>", allow_placeholder=True) == []


def test_full_verification_cli_rejects_explicit_local_base_url(tmp_path):
    output = tmp_path / "run.json"
    markdown = tmp_path / "run.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_full_verification.py",
            "--base-url=https://127.0.0.1:8443",
            "--dry-run",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "base URL must be a non-local public hostname" in result.stderr
    assert not output.exists()
    assert not markdown.exists()


def test_full_verification_requires_base_url_for_real_run(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_full_verification.py",
            f"--output={tmp_path / 'run.json'}",
            f"--markdown-output={tmp_path / 'run.md'}",
        ],
        capture_output=True,
        text=True,
        env={},
    )

    assert result.returncode != 0
    assert "provide --base-url or STAGING_URL" in result.stderr

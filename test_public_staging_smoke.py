"""Public-staging smoke orchestrator regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.compose_route_family_probe import env_headers
from scripts.public_staging_smoke import build_commands, payload, public_base_url_failures


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_route_probe_env_headers_do_not_record_values(monkeypatch):
    monkeypatch.setenv("HEADER_SECRET", "super-secret-value")

    headers, names = env_headers(["X-Test=HEADER_SECRET"])

    assert headers == {"X-Test": "super-secret-value"}
    assert names == ["X-Test"]


def test_smoke_dry_run_commands_include_access_headers_without_values():
    commands = build_commands(
        base_url=PUBLIC_BASE_URL,
        proxy_server="http://localhost:9090",
        expect_commit="abc123",
        samples=2,
    )
    text = json.dumps(commands)

    assert "scripts/public_staging_preflight.py" in text
    assert "scripts/compose_route_family_probe.py" in text
    assert "--header=CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID" in text
    assert "--header=CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET" in text
    assert "super-secret-value" not in text
    assert "--proxy-server=http://localhost:9090" in text


def test_smoke_gcp_commands_omit_access_headers():
    commands = build_commands(
        base_url="https://oasis-staging-abc-ue.a.run.app",
        proxy_server="http://localhost:9090",
        expect_commit="abc123",
        samples=2,
        provider="gcp",
    )
    text = json.dumps(commands)

    assert "scripts/public_staging_preflight.py" in text
    assert "CF-Access-Client-Id" not in text
    assert "OASIS_CF_ACCESS_CLIENT_SECRET" not in text


def test_smoke_payload_dry_run_is_planned_not_public_proof():
    commands = build_commands(base_url=PUBLIC_BASE_URL, proxy_server="", expect_commit="", samples=1)
    data = payload(commands=commands, results=[], dry_run=True)

    assert data["verdict"] == "planned"
    assert data["deploy_provider"] == "render"
    assert data["not_public_staging_proof"] is True
    assert data["failures"] == []


def test_smoke_rejects_non_public_base_url():
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "base URL must use https" in public_base_url_failures("http://staging.example.com")
    assert "base URL must be a non-local public hostname" in public_base_url_failures("https://localhost:8443")
    assert "base URL must not be a reserved documentation hostname" in public_base_url_failures("https://staging.example.com")


def test_smoke_cli_rejects_local_base_url_before_plan_write(tmp_path):
    output = tmp_path / "smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_smoke.py",
            "--base-url=https://127.0.0.1:8443",
            "--dry-run",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "base URL must be a non-local public hostname" in result.stderr
    assert not output.exists()


def test_smoke_cli_rejects_reserved_documentation_host_before_plan_write(tmp_path):
    output = tmp_path / "smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_smoke.py",
            "--base-url=https://staging.example.com",
            "--dry-run",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "base URL must not be a reserved documentation hostname" in result.stderr
    assert not output.exists()


def test_smoke_cli_dry_run_writes_plan(tmp_path):
    output = tmp_path / "smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_smoke.py",
            f"--base-url={PUBLIC_BASE_URL}",
            "--dry-run",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text())
    assert data["verdict"] == "planned"
    assert data["dry_run"] is True

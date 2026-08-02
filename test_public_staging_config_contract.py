"""Public-staging config contract regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.public_staging_config_contract import build_payload


def test_config_contract_passes_current_render_and_compose_contract():
    payload = build_payload(captured_at="2026-07-30T00:00:00Z")

    assert payload["verdict"] == "pass"
    assert payload["deploy_provider"] == "render"
    assert payload["render"]["verdict"] == "pass"
    assert payload["gcp"]["verdict"] == "not_applicable"
    assert payload["compose"]["verdict"] == "pass"
    assert payload["not_public_staging_proof"] is True


def test_config_contract_passes_gcp_contract_when_required_env_is_present():
    env = {
        "OASIS_DEPLOY_PROVIDER": "gcp",
        "GCP_PROJECT_ID": "oasis-staging-123",
        "GCP_REGION": "us-east1",
        "GCP_ARTIFACT_REPOSITORY": "oasis",
        "GCP_CLOUD_RUN_SERVICE": "oasis-staging",
        "GCP_CLOUD_RUN_WORKER_POOL": "oasis-staging-worker",
        "GCP_CLOUD_SQL_INSTANCE": "oasis-staging-postgres",
        "GCP_STORAGE_BUCKET": "oasis-staging-123-oasis-staging",
        "STAGING_URL": "https://oasis-staging-abc-ue.a.run.app",
    }

    payload = build_payload(env=env, provider="gcp", captured_at="2026-08-02T00:00:00Z")

    assert payload["verdict"] == "pass"
    assert payload["deploy_provider"] == "gcp"
    assert payload["render"]["verdict"] == "not_applicable"
    assert payload["gcp"]["verdict"] == "pass"
    assert payload["gcp"]["failures"] == []


def test_config_contract_rejects_gcp_missing_env_and_wrong_region():
    payload = build_payload(
        env={
            "OASIS_DEPLOY_PROVIDER": "gcp",
            "GCP_REGION": "us-west1",
            "STAGING_URL": "https://staging.example.com",
        },
        provider="gcp",
        captured_at="2026-08-02T00:00:00Z",
    )

    assert payload["verdict"] == "investigate"
    assert "gcp_env_GCP_PROJECT_ID" in payload["failures"]
    assert "gcp_region_us_east1" in payload["failures"]
    assert "gcp_staging_url_public_https" in payload["failures"]


def test_config_contract_rejects_committed_base_url_value(tmp_path):
    render = yaml.safe_load(Path("render.yaml").read_text())
    compose = tmp_path / "compose.yaml"
    render_path = tmp_path / "render.yaml"
    compose.write_text(Path("compose.yaml").read_text())
    env = render["envVarGroups"][0]["envVars"]
    item = next(row for row in env if row["key"] == "OASIS_PUBLIC_BASE_URL")
    item.pop("sync", None)
    item["value"] = "https://staging.example.com"
    render_path.write_text(yaml.safe_dump(render))

    payload = build_payload(
        render_path=render_path,
        compose_path=compose,
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "investigate"
    assert "render_sync_false_OASIS_PUBLIC_BASE_URL" in payload["failures"]


def test_config_contract_rejects_missing_compose_storage_env(tmp_path):
    render = tmp_path / "render.yaml"
    compose = tmp_path / "compose.yaml"
    render.write_text(Path("render.yaml").read_text())
    compose_config = yaml.safe_load(Path("compose.yaml").read_text())
    compose_config["services"]["api"]["environment"].pop("OASIS_S3_BUCKET")
    compose.write_text(yaml.safe_dump(compose_config))

    payload = build_payload(
        render_path=render,
        compose_path=compose,
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "investigate"
    assert "compose_api_env_OASIS_S3_BUCKET" in payload["failures"]


def test_config_contract_rejects_compose_public_staging_fallbacks(tmp_path):
    render = tmp_path / "render.yaml"
    compose = tmp_path / "compose.yaml"
    render.write_text(Path("render.yaml").read_text())
    compose_config = yaml.safe_load(Path("compose.yaml").read_text())
    compose_config["services"]["api"]["environment"]["OASIS_STORAGE_BACKEND"] = "${OASIS_STORAGE_BACKEND:-local}"
    compose_config["services"]["api"]["environment"]["OASIS_API_BASE_URL"] = "${OASIS_API_BASE_URL:-https://localhost:8443}"
    compose_config["services"]["api"]["environment"]["AWS_SECRET_ACCESS_KEY"] = "${AWS_SECRET_ACCESS_KEY:-}"
    compose.write_text(yaml.safe_dump(compose_config))

    payload = build_payload(
        render_path=render,
        compose_path=compose,
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "investigate"
    assert "compose_api_env_required_OASIS_STORAGE_BACKEND" in payload["failures"]
    assert "compose_api_env_required_OASIS_API_BASE_URL" in payload["failures"]
    assert "compose_api_env_required_AWS_SECRET_ACCESS_KEY" in payload["failures"]


def test_config_contract_cli_writes_secret_free_json(tmp_path):
    output = tmp_path / "contract.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_config_contract.py",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text())
    text = output.read_text()
    assert data["verdict"] == "pass"
    assert "OASIS_SESSION_SECRET uses generateValue" in text
    assert "AWS_SECRET_ACCESS_KEY" in text
    assert "super-secret" not in text
    assert "Bearer " not in text

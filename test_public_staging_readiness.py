"""Public-staging readiness checker regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.public_staging_readiness import (
    GITHUB_ACTIONS_ENV_REQUIRED,
    GITHUB_STAGING_BRANCH_POLICIES,
    GITHUB_STAGING_SECRETS,
    GITHUB_STAGING_VARIABLES,
    LOCAL_ENV_REQUIRED,
    build_payload,
)

PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_readiness_passes_when_all_prerequisites_are_present():
    payload = build_payload(
        env={**{name: "present" for name in LOCAL_ENV_REQUIRED}, "STAGING_URL": PUBLIC_BASE_URL},
        github={
            "gh_authenticated": True,
            "staging_environment_exists": True,
            "staging_environment_protection_rule_count": 1,
            "staging_environment_deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False},
            "required_staging_branch_policies_missing": [],
            "staging_branch_policies_configured": GITHUB_STAGING_BRANCH_POLICIES,
            "required_staging_secrets_missing": [],
            "required_staging_vars_missing": [],
            "staging_secret_names_configured": GITHUB_STAGING_SECRETS,
            "staging_variable_names_configured": GITHUB_STAGING_VARIABLES,
        },
        browsers={"chrome": True, "firefox": True, "safari": True},
        branch="main",
        commit="abc1234",
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "ready"
    assert payload["blocking_external_inputs"] == []
    assert payload["not_public_staging_proof"] is True
    assert payload["staging_url"]["public_https"] is True


def test_readiness_reports_missing_external_prerequisites_without_secret_values():
    payload = build_payload(
        env={},
        github={
            "gh_authenticated": True,
            "staging_environment_exists": True,
            "staging_environment_protection_rule_count": 0,
            "staging_environment_deployment_branch_policy": None,
            "required_staging_branch_policies_missing": ["main"],
            "staging_branch_policies_configured": [],
            "required_staging_secrets_missing": ["RENDER_API_KEY"],
            "required_staging_vars_missing": ["STAGING_URL"],
            "staging_secret_names_configured": [],
            "staging_variable_names_configured": [],
        },
        browsers={"chrome": True, "firefox": False, "safari": True},
        branch="phase1.75/public-staging",
        commit="abc1234",
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "not_ready"
    assert any("local environment variables missing" in item for item in payload["blocking_external_inputs"])
    assert "GitHub staging environment has no protection rules" in payload["blocking_external_inputs"]
    assert "GitHub staging environment does not require custom branch policies" in payload["blocking_external_inputs"]
    assert "GitHub staging branch policies missing: main" in payload["blocking_external_inputs"]
    assert "GitHub staging secrets missing: RENDER_API_KEY" in payload["blocking_external_inputs"]
    assert "GitHub staging variables missing: STAGING_URL" in payload["blocking_external_inputs"]
    assert "manual browser matrix apps missing: firefox" in payload["blocking_external_inputs"]
    text = json.dumps(payload)
    assert "password123" not in text.lower()
    assert "supersecret" not in text.lower()
    assert all(value == "missing" for value in payload["local_environment"].values())
    assert payload["staging_url"]["present"] is False


def test_readiness_rejects_reserved_or_local_staging_url():
    base_env = {name: "present" for name in LOCAL_ENV_REQUIRED}
    for url, expected in (
        ("https://staging.example.com", "local environment variables STAGING_URL is a reserved documentation hostname"),
        ("https://localhost:8443", "local environment variables STAGING_URL is not a non-local public hostname"),
        ("http://staging.oasis-private-beta.com", "local environment variables STAGING_URL is not HTTPS"),
    ):
        payload = build_payload(
            env={**base_env, "STAGING_URL": url},
            github={
                "gh_authenticated": True,
                "staging_environment_exists": True,
                "staging_environment_protection_rule_count": 1,
                "staging_environment_deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False},
                "required_staging_branch_policies_missing": [],
                "staging_branch_policies_configured": GITHUB_STAGING_BRANCH_POLICIES,
                "required_staging_secrets_missing": [],
                "required_staging_vars_missing": [],
                "staging_secret_names_configured": GITHUB_STAGING_SECRETS,
                "staging_variable_names_configured": GITHUB_STAGING_VARIABLES,
            },
            browsers={"chrome": True, "firefox": True, "safari": True},
            branch="main",
            commit="abc1234",
            captured_at="2026-07-30T00:00:00Z",
        )

        assert payload["verdict"] == "not_ready"
        assert expected in payload["blocking_external_inputs"]
        assert payload["staging_url"]["public_https"] is False
        assert url not in json.dumps(payload)


def test_readiness_cli_writes_not_ready_evidence_with_allow_not_ready(tmp_path):
    output = tmp_path / "readiness.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_readiness.py",
            f"--output={output}",
            "--allow-not-ready",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text())
    assert data["not_public_staging_proof"] is True
    assert data["verdict"] in {"ready", "not_ready"}
    assert Path(output).exists()


def test_github_actions_mode_checks_injected_env_without_provider_metadata():
    payload = build_payload(
        env={**{name: "set" for name in GITHUB_ACTIONS_ENV_REQUIRED if name != "RENDER_API_KEY"}, "STAGING_URL": PUBLIC_BASE_URL},
        github={"context": "github-actions-env-only"},
        browsers={},
        branch="main",
        commit="abc1234",
        captured_at="2026-07-30T00:00:00Z",
        required_env_names=GITHUB_ACTIONS_ENV_REQUIRED,
        require_github_provider_metadata=False,
        require_browsers=False,
        env_label="GitHub Actions deployment environment variables",
    )

    assert payload["verdict"] == "not_ready"
    assert payload["local_environment"]["RENDER_API_KEY"] == "missing"
    assert payload["github"] == {"context": "github-actions-env-only"}
    assert payload["local_browser_availability"] == {}
    assert payload["blocking_external_inputs"] == [
        "GitHub Actions deployment environment variables missing: RENDER_API_KEY"
    ]

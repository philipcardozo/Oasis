"""GitHub staging environment hardening helper regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_github_environment import environment_payload


def test_environment_payload_requires_reviewer_and_custom_branch_policy():
    payload = environment_payload(reviewer_id=123, prevent_self_review=True)

    assert payload["wait_timer"] == 0
    assert payload["prevent_self_review"] is True
    assert payload["reviewers"] == [{"type": "User", "id": 123}]
    assert payload["deployment_branch_policy"] == {
        "protected_branches": False,
        "custom_branch_policies": True,
    }


def test_github_environment_helper_dry_run_is_secret_free():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_github_environment.py",
            "--dry-run",
            "--reviewer-id=123",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["environment"] == "staging"
    assert payload["branch"] == "main"
    assert payload["payload"]["reviewers"][0]["id"] == 123
    assert "secret" not in result.stdout.lower()

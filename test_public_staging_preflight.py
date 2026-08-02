"""Public-staging preflight regressions."""
from __future__ import annotations

import subprocess
import sys

from scripts.public_staging_preflight import public_base_url_failures

PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_public_preflight_rejects_non_https_or_local_base_url():
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "base URL must use https" in public_base_url_failures("http://staging.example.com")
    assert "base URL must be a non-local public hostname" in public_base_url_failures("https://localhost:8443")
    assert "base URL must be a non-local public hostname" in public_base_url_failures("https://oasis.local")
    assert "base URL must not be a reserved documentation hostname" in public_base_url_failures("https://staging.example.com")


def test_public_preflight_cli_aborts_before_network_for_reserved_url(tmp_path):
    output = tmp_path / "preflight.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_preflight.py",
            "--base-url=https://staging.example.com",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "base URL must not be a reserved documentation hostname" in result.stderr
    assert not output.exists()


def test_public_preflight_cli_aborts_before_network_for_local_url(tmp_path):
    output = tmp_path / "preflight.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_preflight.py",
            "--base-url=https://127.0.0.1:8443",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "base URL must be a non-local public hostname" in result.stderr
    assert not output.exists()

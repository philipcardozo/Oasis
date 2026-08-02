"""Public-staging browser matrix template regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_browser_matrix_template import build_payload, markdown, public_base_url_failures
from scripts.public_staging_browser_reports import BROWSER_CHECKS, MAP_CHECKS


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_browser_matrix_template_requires_operator_input_and_covers_checks():
    payload = build_payload(
        base_url=PUBLIC_BASE_URL,
        captured_at="2026-07-30T00:00:00Z",
    )

    assert payload["verdict"] == "operator_input_required"
    assert payload["not_public_staging_proof"] is True
    assert payload["base_url"] == PUBLIC_BASE_URL

    by_name = {row["name"]: row for row in payload["browsers"]}
    assert {"chrome", "firefox", "safari_macos"} <= by_name.keys()
    assert by_name["edge_or_brave"]["optional"] is True
    assert {"mobile_safari", "chrome_android"} <= by_name.keys()

    for name in ("chrome", "firefox", "safari_macos"):
        assert by_name[name]["available"] is None
        assert by_name[name]["checks"] == {key: None for key in BROWSER_CHECKS}

    assert payload["map_provider"]["checks"] == {key: None for key in MAP_CHECKS}


def test_browser_matrix_template_text_is_secret_free_and_actionable():
    payload = build_payload(
        base_url=PUBLIC_BASE_URL,
        captured_at="2026-07-30T00:00:00Z",
    )
    text = json.dumps(payload) + markdown(payload)

    assert "Chrome, Firefox, and Safari" in text
    assert "stale-update 409" in text
    assert "cross-user denial" in text
    assert "no reusable token in localStorage" in text
    assert "public_staging_browser_reports.py" in text
    assert "Bearer " not in text
    assert "CF-Access-Client-Secret" not in text
    assert "ghp_" not in text
    assert "password123" not in text


def test_browser_matrix_template_cli_writes_json_and_markdown(tmp_path):
    template_json = tmp_path / "browser-matrix.template.json"
    template_md = tmp_path / "browser-matrix-template.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_browser_matrix_template.py",
            f"--base-url={PUBLIC_BASE_URL}",
            f"--json-output={template_json}",
            f"--markdown-output={template_md}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(template_json.read_text())
    assert data["verdict"] == "operator_input_required"
    assert data["base_url"] == PUBLIC_BASE_URL
    assert "# Public Staging Browser Matrix Template" in template_md.read_text()


def test_browser_matrix_template_rejects_explicit_local_public_target(tmp_path):
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert public_base_url_failures("https://staging.<approved-domain>", allow_placeholder=True) == []
    assert "browser matrix base URL must use https" in public_base_url_failures("http://staging.example.com")
    assert "browser matrix base URL must be a non-local public hostname" in public_base_url_failures("https://localhost:8443")
    assert "browser matrix base URL must not be a reserved documentation hostname" in public_base_url_failures(
        "https://staging.example.com"
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_browser_matrix_template.py",
            "--base-url=https://127.0.0.1:8443",
            f"--json-output={tmp_path / 'browser-matrix.template.json'}",
            f"--markdown-output={tmp_path / 'browser-matrix-template.md'}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "non-local public hostname" in result.stderr


def test_browser_matrix_template_rejects_reserved_documentation_target(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_browser_matrix_template.py",
            "--base-url=https://staging.example.com",
            f"--json-output={tmp_path / 'browser-matrix.template.json'}",
            f"--markdown-output={tmp_path / 'browser-matrix-template.md'}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "reserved documentation hostname" in result.stderr

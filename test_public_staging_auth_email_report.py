"""Public-staging auth/email report regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_auth_email_report import evaluate


def test_auth_email_report_passes_with_complete_sanitized_evidence():
    failures, rows = evaluate(_auth())

    assert failures == []
    assert rows["user_a_verification_status"] == 200
    assert rows["password_reset_complete_status"] == 200
    assert rows["password_change_status"] == 200
    assert rows["account_delete_status"] == 200


def test_auth_email_report_requires_reset_completion():
    auth = _auth()
    auth["checks"]["password_reset"]["complete"]["status_code"] = 400

    failures, _ = evaluate(auth)

    assert "password reset completion did not return 200" in failures


def test_auth_email_report_requires_account_lifecycle_completion():
    auth = _auth()
    auth["checks"]["account_lifecycle"]["logout_all"]["status_code"] = 500
    auth["checks"]["account_lifecycle"]["post_delete_login"]["status_code"] = 200

    failures, _ = evaluate(auth)

    assert "account lifecycle logout_all_status is not 200" in failures
    assert "account lifecycle post_delete_login_status is not 401" in failures


def test_auth_email_report_rejects_complete_emails_and_secret_values():
    auth = _auth()
    auth["users"]["user_a"]["email"] = "tester@example.com"
    auth["checks"]["password_reset"]["token"] = "raw-reset-token"

    failures, _ = evaluate(auth)

    assert "auth evidence contains a complete email address" in failures
    assert any("secret-like string values" in item for item in failures)


def test_auth_email_report_cli_writes_pass_markdown(tmp_path):
    source = tmp_path / "27-public-auth-map-slots.json"
    output = tmp_path / "06-auth-email.md"
    summary = tmp_path / "auth-email-summary.json"
    source.write_text(json.dumps(_auth()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_auth_email_report.py",
            f"--auth-map-slots={source}",
            f"--output={output}",
            f"--summary-output={summary}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verdict: **pass**" in output.read_text()
    data = json.loads(summary.read_text())
    assert data["verdict"] == "pass"
    assert data["rows"]["password_reset_complete_status"] == 200
    assert data["rows"]["session_cookie_httponly"] is True


def _auth() -> dict:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "base_url": "https://staging.example.com",
        "verdict": "pass",
        "users": {
            "user_a": {
                "email_env": "OASIS_PUBLIC_TESTER_A_EMAIL",
                "email_domain": "example.com",
                "verification_token_env": "OASIS_PUBLIC_TESTER_A_VERIFY_TOKEN",
                "verification_token_supplied": True,
                "register": {"status_code": 201},
                "verify_email": {"status_code": 200},
                "login": {"status_code": 200},
            },
            "user_b": {
                "email_env": "OASIS_PUBLIC_TESTER_B_EMAIL",
                "email_domain": "example.com",
                "verification_token_env": "OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN",
                "verification_token_supplied": True,
                "register": {"status_code": 201},
                "verify_email": {"status_code": 200},
                "login": {"status_code": 200},
            },
            "lifecycle_user": {
                "email_env": "OASIS_PUBLIC_LIFECYCLE_EMAIL",
                "email_domain": "example.com",
                "verification_token_env": "OASIS_PUBLIC_LIFECYCLE_VERIFY_TOKEN",
                "verification_token_supplied": True,
                "register": {"status_code": 201},
                "verify_email": {"status_code": 200},
                "login": {"status_code": 200},
            },
        },
        "checks": {
            "session_cookie_secure": True,
            "session_cookie_httponly": True,
            "csrf_cookie_secure": True,
            "csrf_rejection": {"status_code": 403},
            "password_reset": {
                "reset_token_env": "OASIS_PUBLIC_TESTER_A_RESET_TOKEN",
                "reset_token_supplied": True,
                "reset_password_env": "OASIS_PUBLIC_TESTER_A_RESET_PASSWORD",
                "reset_password_supplied": True,
                "request": {"status_code": 200},
                "complete": {"status_code": 200},
                "post_reset_login": {"status_code": 200},
            },
            "account_lifecycle": {
                "changed_password_env": "OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD",
                "changed_password_supplied": True,
                "csrf_cookie_present": True,
                "session_list": {"status_code": 200},
                "revoke_target_login": {"status_code": 200},
                "revoke_target_session_found": True,
                "session_revoke": {"status_code": 200},
                "revoked_session_me": {"status_code": 401},
                "password_change": {"status_code": 200},
                "old_password_login_after_change": {"status_code": 401},
                "new_password_login_after_change": {"status_code": 200},
                "logout_all": {"status_code": 200},
                "post_logout_all_me": {"status_code": 401},
                "original_session_after_logout_all_me": {"status_code": 401},
                "delete_login": {"status_code": 200},
                "account_delete": {"status_code": 200},
                "post_delete_me": {"status_code": 401},
                "post_delete_login": {"status_code": 401},
            },
        },
    }

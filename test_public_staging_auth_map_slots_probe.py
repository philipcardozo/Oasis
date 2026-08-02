"""Public-staging auth/map-slot probe regressions."""
from __future__ import annotations

from argparse import Namespace

import pytest

from scripts.public_staging_auth_map_slots_probe import build_payload, email_domain, evaluate, public_base_url_failures


PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def test_public_auth_map_slot_probe_passes_with_complete_evidence():
    payload = _payload()

    failures, warnings = evaluate(payload)

    assert failures == []
    assert warnings == ["latency targets were not enforced because this is external HTTP timing"]


def test_public_auth_map_slot_probe_requires_email_tokens_and_csrf():
    payload = _payload()
    payload["users"]["user_a"]["verification_token_supplied"] = False
    payload["checks"]["csrf_rejection"]["status_code"] = 200
    payload["checks"]["session_cookie_samesite"] = "none"
    payload["checks"]["account_lifecycle"]["password_change"]["status_code"] = 403
    payload["checks"]["password_reset"]["token_reuse"]["status_code"] = 200

    failures, _ = evaluate(payload)

    assert "user_a verification token env is missing" in failures
    assert "CSRF rejection status is not 403" in failures
    assert "session cookie SameSite is not lax" in failures
    assert "password change did not return 200" in failures
    assert "password reset token reuse was not rejected" in failures


def test_public_auth_map_slot_probe_requires_single_use_and_generic_reset_shape():
    payload = _payload()
    payload["users"]["user_b"]["verify_email_reuse"]["status_code"] = 200
    payload["checks"]["password_reset"]["unknown_account_request"]["status_code"] = 202
    payload["checks"]["password_reset"]["unknown_account_request"]["json_keys"] = ["different"]

    failures, _ = evaluate(payload)

    assert "user_b email verification token reuse was not rejected" in failures
    assert "unknown-account password reset request did not return generic 200" in failures
    assert "known and unknown password reset responses have different JSON shape" in failures


def test_public_auth_map_slot_probe_requires_exactly_three_slots_and_cross_user_denial():
    payload = _payload()
    payload["checks"]["default_map_slot_numbers"] = [1, 2, 3, 4]
    payload["checks"]["cross_user_slot_read_denied"]["status_code"] = 200

    failures, _ = evaluate(payload)

    assert "exactly-three map-slot evidence is missing" in failures
    assert "cross-user map-slot read denial is missing or not 403/404" in failures


def test_public_auth_map_slot_probe_requires_fourth_slot_denial():
    payload = _payload()
    payload["checks"]["fourth_slot_create_attempt"]["status_code"] = 201
    payload["checks"]["fourth_slot_import_attempt"]["status_code"] = 200

    failures, _ = evaluate(payload)

    assert "fourth map-slot create attempt was not rejected" in failures
    assert "fourth map-slot import attempt was not rejected with 422" in failures


def test_email_domain_avoids_recording_complete_address():
    assert email_domain("beta.tester+probe@example.com") == "example.com"
    assert email_domain("not-an-email") == "<invalid>"


def test_public_auth_map_slot_probe_rejects_local_or_non_https_base_url():
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "base URL is not HTTPS" in public_base_url_failures("http://staging.example.com")
    assert "base URL is not public" in public_base_url_failures("https://localhost:8443")
    assert "base URL is a reserved documentation hostname" in public_base_url_failures("https://staging.example.com")


def test_public_auth_map_slot_probe_build_payload_aborts_before_network_for_local_url():
    args = Namespace(
        base_url="https://127.0.0.1:8443",
        header=[],
        user_a_email_env="OASIS_PUBLIC_TESTER_A_EMAIL",
        user_a_password_env="OASIS_PUBLIC_TESTER_A_PASSWORD",
        user_a_verification_token_env="OASIS_PUBLIC_TESTER_A_VERIFY_TOKEN",
        user_a_reset_token_env="OASIS_PUBLIC_TESTER_A_RESET_TOKEN",
        user_a_reset_password_env="OASIS_PUBLIC_TESTER_A_RESET_PASSWORD",
        unknown_reset_email_env="OASIS_PUBLIC_UNKNOWN_RESET_EMAIL",
        user_b_email_env="OASIS_PUBLIC_TESTER_B_EMAIL",
        user_b_password_env="OASIS_PUBLIC_TESTER_B_PASSWORD",
        user_b_verification_token_env="OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN",
        lifecycle_email_env="OASIS_PUBLIC_LIFECYCLE_EMAIL",
        lifecycle_password_env="OASIS_PUBLIC_LIFECYCLE_PASSWORD",
        lifecycle_verification_token_env="OASIS_PUBLIC_LIFECYCLE_VERIFY_TOKEN",
        lifecycle_changed_password_env="OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD",
        proxy_server="",
        insecure=False,
        timeout=1,
        samples=1,
        enforce_app_targets=False,
    )

    with pytest.raises(SystemExit, match="base URL is not public"):
        build_payload(args)


def _payload() -> dict:
    return {
        "latency_targets_enforced": False,
        "users": {
            "user_a": {
                "register": {"status_code": 201},
                "verification_token_supplied": True,
                "verify_email": {"status_code": 200},
                "verify_email_reuse": {"status_code": 400},
                "login": {"status_code": 200},
            },
            "user_b": {
                "register": {"status_code": 201},
                "verification_token_supplied": True,
                "verify_email": {"status_code": 200},
                "verify_email_reuse": {"status_code": 400},
                "login": {"status_code": 200},
            },
            "lifecycle_user": {
                "register": {"status_code": 201},
                "verification_token_supplied": True,
                "verify_email": {"status_code": 200},
                "verify_email_reuse": {"status_code": 400},
                "login": {"status_code": 200},
            },
        },
        "checks": {
            "session_cookie_secure": True,
            "session_cookie_httponly": True,
            "session_cookie_samesite": "lax",
            "session_cookie_path": "/",
            "session_cookie_domain_host_only": True,
            "csrf_cookie_secure": True,
            "csrf_cookie_samesite": "lax",
            "csrf_cookie_path": "/",
            "csrf_cookie_domain_host_only": True,
            "csrf_rejection": {"status_code": 403},
            "default_map_slot_count": 3,
            "default_map_slot_numbers": [1, 2, 3],
            "cross_user_slot_read_denied": {"status_code": 404},
            "stale_version_conflict": {"status_code": 409},
            "fourth_slot_create_attempt": {"status_code": 405},
            "fourth_slot_import_attempt": {"status_code": 422},
            "password_reset": {
                "request": {"status_code": 200, "json_keys": ["message", "ok"]},
                "unknown_account_request": {"status_code": 200, "json_keys": ["message", "ok"]},
                "reset_token_supplied": True,
                "reset_password_supplied": True,
                "complete": {"status_code": 200},
                "post_reset_login": {"status_code": 200},
                "session_cookie_rotated_after_login": True,
                "token_reuse": {"status_code": 400},
            },
            "account_lifecycle": {
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
        "measurements": [
            {
                "name": "session validation GET /api/auth/me",
                "status_codes": [200],
                "target_met": None,
            },
            {
                "name": "map-slot read GET /api/map-slots/{id}",
                "status_codes": [200],
                "target_met": None,
            },
            {
                "name": "map-slot write PUT /api/map-slots/{id}",
                "status_codes": [200],
                "target_met": None,
            },
        ],
    }

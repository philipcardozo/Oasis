"""Public-staging auth/map-slot probe regressions."""
from __future__ import annotations

from scripts.public_staging_auth_map_slots_probe import email_domain, evaluate


def test_public_auth_map_slot_probe_passes_with_complete_evidence():
    payload = _payload()

    failures, warnings = evaluate(payload)

    assert failures == []
    assert warnings == ["latency targets were not enforced because this is external HTTP timing"]


def test_public_auth_map_slot_probe_requires_email_tokens_and_csrf():
    payload = _payload()
    payload["users"]["user_a"]["verification_token_supplied"] = False
    payload["checks"]["csrf_rejection"]["status_code"] = 200
    payload["checks"]["account_lifecycle"]["password_change"]["status_code"] = 403
    payload["checks"]["password_reset"]["token_reuse"]["status_code"] = 200

    failures, _ = evaluate(payload)

    assert "user_a verification token env is missing" in failures
    assert "CSRF rejection status is not 403" in failures
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


def test_email_domain_avoids_recording_complete_address():
    assert email_domain("beta.tester+probe@example.com") == "example.com"
    assert email_domain("not-an-email") == "<invalid>"


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
            "csrf_cookie_secure": True,
            "csrf_rejection": {"status_code": 403},
            "default_map_slot_count": 3,
            "default_map_slot_numbers": [1, 2, 3],
            "cross_user_slot_read_denied": {"status_code": 404},
            "stale_version_conflict": {"status_code": 409},
            "password_reset": {
                "request": {"status_code": 200, "json_keys": ["message", "ok"]},
                "unknown_account_request": {"status_code": 200, "json_keys": ["message", "ok"]},
                "reset_token_supplied": True,
                "reset_password_supplied": True,
                "complete": {"status_code": 200},
                "post_reset_login": {"status_code": 200},
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

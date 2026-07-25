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

    failures, _ = evaluate(payload)

    assert "user_a verification token env is missing" in failures
    assert "CSRF rejection status is not 403" in failures


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
                "login": {"status_code": 200},
            },
            "user_b": {
                "register": {"status_code": 201},
                "verification_token_supplied": True,
                "verify_email": {"status_code": 200},
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
                "request": {"status_code": 200},
                "reset_token_supplied": True,
                "reset_password_supplied": True,
                "complete": {"status_code": 200},
                "post_reset_login": {"status_code": 200},
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

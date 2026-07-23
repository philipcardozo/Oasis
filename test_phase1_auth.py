"""Phase 1 authentication regressions."""
from __future__ import annotations


def _verify_token():
    from server import email as email_mod
    return email_mod.SENT[-1].text.split("token=")[1].split()[0]


def test_register_and_verify(app_client):
    r = app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    assert r.status_code == 201
    r = app_client.post("/api/auth/verify-email", json={"token": _verify_token()})
    assert r.status_code == 200 and r.json()["verified"] is True


def test_duplicate_registration_does_not_enumerate(app_client):
    app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    r = app_client.post("/api/auth/register", json={"email": "A@B.com", "password": "different1"})
    # Same generic success message regardless of whether the email exists.
    assert r.status_code == 201
    assert "verify" in r.json()["message"].lower()


def test_email_is_normalized(app_client):
    app_client.post("/api/auth/register", json={"email": "Mixed@Case.COM", "password": "correcthorse"})
    from server.db import session_scope
    from server import repositories as repo
    with session_scope() as db:
        assert repo.get_user_by_email(db, "mixed@case.com") is not None


def test_login_success_and_failure(app_client):
    app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    bad = app_client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert bad.status_code == 401
    good = app_client.post("/api/auth/login", json={"email": "a@b.com", "password": "correcthorse"})
    assert good.status_code == 200 and "oasis_session" in good.cookies


def test_expired_verification_token_rejected(app_client):
    app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    r = app_client.post("/api/auth/verify-email", json={"token": "bogus-token"})
    assert r.status_code == 400


def test_password_reset_flow(registered):
    client, email, _ = registered
    from server import email as email_mod
    client.post("/api/auth/password-reset/request", json={"email": email})
    token = email_mod.SENT[-1].text.split("token=")[1].split()[0]
    r = client.post("/api/auth/password-reset/complete", json={"token": token, "password": "brandnewpass1"})
    assert r.status_code == 200
    # Old sessions revoked; new password works.
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "brandnewpass1"}).status_code == 200


def test_expired_reset_token_rejected(app_client):
    r = app_client.post("/api/auth/password-reset/complete", json={"token": "nope", "password": "whatever12"})
    assert r.status_code == 400


def test_password_change_requires_current(registered):
    client, _, csrf = registered
    bad = client.post("/api/auth/password-change",
                      json={"current_password": "wrong", "new_password": "newpassword1"},
                      headers={"X-CSRF-Token": csrf})
    assert bad.status_code == 403
    ok = client.post("/api/auth/password-change",
                     json={"current_password": "correcthorsebattery", "new_password": "newpassword1"},
                     headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200


def test_session_listing_and_revocation(registered):
    client, _, csrf = registered
    sessions = client.get("/api/auth/sessions").json()["sessions"]
    assert len(sessions) >= 1
    sid = sessions[0]["id"]
    assert client.delete(f"/api/auth/sessions/{sid}", headers={"X-CSRF-Token": csrf}).status_code == 200
    # Revoked session no longer authenticates.
    assert client.get("/api/auth/me").status_code == 401


def test_logout_all(registered):
    client, _, csrf = registered
    r = client.post("/api/auth/logout-all", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_secure_cookie_flags(app_client):
    app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    r = app_client.post("/api/auth/login", json={"email": "a@b.com", "password": "correcthorse"})
    set_cookie = " ".join(r.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie          # session cookie is HttpOnly
    assert "Path=/" in set_cookie
    assert "oasis_session" in set_cookie


def test_no_token_in_body_or_localstorage_shape(registered):
    """The session token must live only in the cookie, never in a JSON body."""
    client, email, _ = registered
    body = client.get("/api/auth/me").json()
    assert "token" not in body and "session" not in body


def test_csrf_required_for_logout(registered):
    client, _, _ = registered
    assert client.post("/api/auth/logout").status_code == 403  # no CSRF header


def test_account_deletion_anonymizes(registered):
    client, email, csrf = registered
    assert client.delete("/api/auth/account", headers={"X-CSRF-Token": csrf}).status_code == 200
    from server.db import session_scope
    from server import repositories as repo
    with session_scope() as db:
        assert repo.get_user_by_email(db, email) is None  # normalized email rewritten

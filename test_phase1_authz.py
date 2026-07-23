"""Phase 1 authorization + map-slot ownership regressions."""
from __future__ import annotations


def _make_user(client, email):
    from server import email as email_mod
    client.post("/api/auth/register", json={"email": email, "password": "correcthorsebattery"})
    token = email_mod.SENT[-1].text.split("token=")[1].split()[0]
    client.post("/api/auth/verify-email", json={"token": token})


def _login(client, email):
    client.post("/api/auth/login", json={"email": email, "password": "correcthorsebattery"})
    return client.cookies.get("oasis_csrf")


def test_public_route_needs_no_auth(app_client):
    assert app_client.get("/healthz").status_code == 200
    assert app_client.get("/version").status_code == 200


def test_protected_route_requires_auth(app_client):
    assert app_client.get("/api/auth/me").status_code == 401
    assert app_client.get("/api/map-slots").status_code == 401


def test_existing_write_route_requires_auth(app_client):
    # Retrofit check: the pre-existing map_api write endpoint is now protected.
    r = app_client.post("/api/overrides",
                        json={"object_type": "x", "object_id": "y", "field_name": "z", "new_value": "1"})
    assert r.status_code == 401


def test_existing_write_route_requires_csrf(registered):
    client, _, _ = registered  # logged in, but no CSRF header
    r = client.post("/api/overrides",
                    json={"object_type": "x", "object_id": "y", "field_name": "z", "new_value": "1"})
    assert r.status_code == 403


def test_owner_only_map_slot_access_denied_cross_user(app_client):
    _make_user(app_client, "owner@x.com")
    _login(app_client, "owner@x.com")
    slot_id = app_client.get("/api/map-slots").json()["slots"][0]["id"]
    # Switch to a different user.
    app_client.post("/api/auth/logout", headers={"X-CSRF-Token": app_client.cookies.get("oasis_csrf")})
    _make_user(app_client, "attacker@x.com")
    _login(app_client, "attacker@x.com")
    # The attacker cannot read the owner's slot.
    assert app_client.get(f"/api/map-slots/{slot_id}").status_code == 404


def test_worker_and_admin_paths_are_not_publicly_reachable(app_client):
    # There are no unauthenticated admin/worker HTTP routes; write guard blocks writes.
    assert app_client.post("/api/reports/asset/x/generate").status_code in (401, 404, 405)


def test_safe_methods_stay_public_for_read_data(app_client):
    # A deliberately public read endpoint remains reachable without auth.
    r = app_client.get("/api/map/layers")
    assert r.status_code == 200

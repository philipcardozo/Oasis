"""Phase 1 map-slot regressions: 3 defaults, CRUD, concurrency, validation."""
from __future__ import annotations

import json


def test_exactly_three_default_slots(registered):
    client, _, _ = registered
    slots = client.get("/api/map-slots").json()["slots"]
    assert len(slots) == 3
    assert [s["slot_number"] for s in slots] == [1, 2, 3]
    assert slots[0]["is_active"] is True  # slot 1 = current default experience


def test_default_slots_degrade_disabled_satellite(app_client):
    from server import repositories as repo
    from server.db import session_scope
    from server.security import hash_password

    with session_scope() as db:
        user = repo.create_user(db, "secure-slots@example.com", hash_password("correcthorse"),
                                feature_satellite_esri=False)
        slots = repo.list_map_slots(db, user.id)
    assert len(slots) == 3
    assert [slot.basemap for slot in slots] == ["standard", "dark", "standard"]


def test_update_and_rename(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][1]
    r = client.put(f"/api/map-slots/{slot['id']}", json={"basemap": "dark", "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["basemap"] == "dark" and r.json()["version"] == slot["version"] + 1
    r2 = client.post(f"/api/map-slots/{slot['id']}/rename", json={"name": "My View", "version": r.json()["version"]},
                     headers={"X-CSRF-Token": csrf})
    assert r2.status_code == 200 and r2.json()["name"] == "My View"


def test_reset(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][2]
    client.put(f"/api/map-slots/{slot['id']}", json={"basemap": "standard", "version": slot["version"]},
               headers={"X-CSRF-Token": csrf})
    r = client.post(f"/api/map-slots/{slot['id']}/reset", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["basemap"] == "satellite"  # slot 3 default


def test_version_conflict_detected(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    client.put(f"/api/map-slots/{slot['id']}", json={"basemap": "dark", "version": slot["version"]},
               headers={"X-CSRF-Token": csrf})
    # Second device sends the stale version.
    r = client.put(f"/api/map-slots/{slot['id']}", json={"basemap": "satellite", "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "version_conflict"


def test_invalid_basemap_rejected(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    r = client.put(f"/api/map-slots/{slot['id']}", json={"basemap": "http://evil/style.json", "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422


def test_disabled_satellite_basemap_rejected(registered):
    client, _, csrf = registered
    override_key = _override_settings(client, feature_satellite_esri=False)
    try:
        slot = client.get("/api/map-slots").json()["slots"][0]
        r = client.put(f"/api/map-slots/{slot['id']}",
                       json={"basemap": "satellite", "version": slot["version"]},
                       headers={"X-CSRF-Token": csrf})
    finally:
        client.app.dependency_overrides.pop(override_key, None)
    assert r.status_code == 422
    assert "Esri imagery is disabled" in r.json()["detail"]


def test_reset_uses_available_default_when_satellite_disabled(registered):
    client, _, csrf = registered
    override_key = _override_settings(client, feature_satellite_esri=False)
    try:
        slot = client.get("/api/map-slots").json()["slots"][2]
        r = client.post(f"/api/map-slots/{slot['id']}/reset", headers={"X-CSRF-Token": csrf})
    finally:
        client.app.dependency_overrides.pop(override_key, None)
    assert r.status_code == 200
    assert r.json()["basemap"] == "standard"


def test_invalid_layer_rejected(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    r = client.put(f"/api/map-slots/{slot['id']}",
                   json={"config": {"layers": {"evil-layer": True}}, "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422


def test_camera_bounds_validated(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    r = client.put(f"/api/map-slots/{slot['id']}",
                   json={"config": {"camera": {"center": [999, 999]}}, "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422


def test_config_size_limit(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    big = {"prefs": {f"k{i}": "x" * 100 for i in range(2000)}}
    r = client.put(f"/api/map-slots/{slot['id']}", json={"config": big, "version": slot["version"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 413


def test_stored_xss_stripped_from_name(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][0]
    r = client.post(f"/api/map-slots/{slot['id']}/rename",
                    json={"name": "<script>alert(1)</script>", "version": slot["version"]},
                    headers={"X-CSRF-Token": csrf})
    assert "<" not in r.json()["name"] and ">" not in r.json()["name"]


def test_export_import_roundtrip(registered):
    client, _, csrf = registered
    slots = client.get("/api/map-slots").json()["slots"]
    src = slots[1]
    client.put(f"/api/map-slots/{src['id']}", json={"basemap": "dark", "version": src["version"]},
               headers={"X-CSRF-Token": csrf})
    exported = client.get(f"/api/map-slots/{src['id']}/export").json()
    assert exported["kind"] == "map_slot" and exported["basemap"] == "dark"
    r = client.post("/api/map-slots/import", json={"slot_number": 3, "config_json": json.dumps(exported)},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["basemap"] == "dark"


def test_set_active_slot(registered):
    client, _, csrf = registered
    slot = client.get("/api/map-slots").json()["slots"][2]
    assert client.post(f"/api/map-slots/{slot['id']}/activate", headers={"X-CSRF-Token": csrf}).status_code == 200
    slots = client.get("/api/map-slots").json()["slots"]
    assert [s["is_active"] for s in slots] == [False, False, True]


def test_duplicate_between_slots_stays_within_limit(registered):
    client, _, csrf = registered
    slots = client.get("/api/map-slots").json()["slots"]
    client.put(f"/api/map-slots/{slots[0]['id']}", json={"basemap": "satellite", "version": slots[0]["version"]},
               headers={"X-CSRF-Token": csrf})
    r = client.post(f"/api/map-slots/{slots[0]['id']}/duplicate-to/{slots[1]['id']}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["basemap"] == "satellite"
    assert len(client.get("/api/map-slots").json()["slots"]) == 3  # never exceeds 3


def _override_settings(client, **overrides):
    from server.config import get_settings, load_settings

    settings = load_settings(
        mode="development",
        session_secret="test-secret-least-thirty-two-chars-long!!",
        **overrides,
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    return get_settings

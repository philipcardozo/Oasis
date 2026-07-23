"""Phase 1.5 worker/network isolation evidence for the composed API.

The Phase 0 launch-safety tests cover the core modules. These checks exercise
the production composition root (`server.app:create_app`) so the auth/security
middleware and reused map API routes are tested together.
"""
from __future__ import annotations

import socket

import pytest


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def blocked(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network access attempted from API process")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    return calls


@pytest.fixture
def empty_facts(monkeypatch, tmp_path):
    facts = tmp_path / "companyfacts"
    facts.mkdir()

    import cache_companyfacts
    import dcf_export
    import map_api

    monkeypatch.setattr(cache_companyfacts, "OUT_DIR", facts)
    monkeypatch.setattr(dcf_export, "FACTS", facts)
    monkeypatch.setattr(map_api, "COMPANYFACTS", facts)
    dcf_export._load_facts_cached.cache_clear()
    map_api._entity_reverse_dcf_json_cached.cache_clear()
    map_api._entity_comps_json_cached.cache_clear()
    return facts


def test_composed_api_financial_paths_do_not_acquire_external_data(no_network, empty_facts, app_client):
    reverse = app_client.get("/api/entity/CAT/reverse-dcf")
    comps = app_client.get("/api/entity/CAT/comps")
    dcf = app_client.get("/api/entity/CAT/dcf.xlsx")

    assert reverse.status_code == 200
    assert reverse.json()["available"] is False
    assert reverse.json()["facts_cached"] is False

    assert comps.status_code == 200
    assert comps.json()["available"] is False
    assert "cached SEC facts" in comps.json()["reason"]

    assert dcf.status_code == 503
    assert "refresh_financial_facts.py" in dcf.json()["detail"]

    assert no_network == []
    assert list(empty_facts.glob("*.json")) == []


def test_composed_api_startup_and_health_do_not_create_financial_facts(no_network, empty_facts, app_client):
    assert app_client.get("/healthz").json() == {"status": "ok"}
    assert no_network == []
    assert list(empty_facts.glob("*.json")) == []

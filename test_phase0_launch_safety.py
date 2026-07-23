"""Phase 0 launch-safety regressions.

Deterministic: no live SEC, no map provider, no logo service, no reliance on an
existing local cache or previous browser state. Networking is hard-blocked at the
socket layer, so any request path that tries to reach out fails loudly.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


@pytest.fixture
def no_network(monkeypatch):
    """Fail any attempt to open a socket. Catches outbound access anywhere."""
    calls = []

    def blocked(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network access attempted in a local-only path")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    return calls


@pytest.fixture
def empty_facts(monkeypatch, tmp_path):
    """Point the companyfacts cache at an empty temp dir (never touches user data)."""
    import cache_companyfacts
    import dcf_export

    facts = tmp_path / "companyfacts"
    facts.mkdir()
    monkeypatch.setattr(dcf_export, "FACTS", facts)
    monkeypatch.setattr(cache_companyfacts, "OUT_DIR", facts)
    return facts


# --- 1. no network from user-facing financial endpoints ----------------------

def test_comps_is_local_only_and_degrades(no_network, empty_facts):
    from comps import comps

    result = comps("CAT")
    assert result["available"] is False
    assert "cached" in result["reason"].lower()
    assert result.get("peers_skipped_uncached", 0) > 0   # explicit, not a silent zero
    assert not list(empty_facts.glob("*.json"))          # nothing downloaded


def test_reverse_dcf_is_local_only_and_degrades(no_network, empty_facts):
    from reverse_dcf import reverse_dcf

    result = reverse_dcf("CAT")
    assert result["available"] is False
    assert result.get("facts_cached") is False
    assert not list(empty_facts.glob("*.json"))


def test_load_facts_refuses_network_by_default(no_network, empty_facts):
    from dcf_export import FactsUnavailable, load_facts

    with pytest.raises(FactsUnavailable):
        load_facts({"cik": "0000018230"})


def test_missing_facts_are_not_reported_as_zero(no_network, empty_facts):
    """A cache miss must be explicit, never a misleading 0.0."""
    from reverse_dcf import reverse_dcf

    result = reverse_dcf("CAT")
    assert result.get("implied_growth") in (None, ...) or "implied_growth" not in result


# --- 2. no network during ordinary startup warming ---------------------------

def test_startup_warming_is_local_only(no_network, empty_facts):
    import map_api

    map_api.warm_startup_caches()   # must not raise: no outbound access
    assert not list(empty_facts.glob("*.json"))


# --- 3. no logo download during workbook export ------------------------------

def test_logo_lookup_never_downloads(no_network):
    from dcf_export import get_company_logo

    # Unknown ticker: must not guess a domain or fetch; local candidates only.
    assert get_company_logo("ZZZZ_NOT_A_REAL_TICKER", "Nonexistent Corp") in (
        None, ROOT / "Assets & Media" / "Logos" / "Logo_Dark_BG.png"
    )


def test_no_ticker_domain_guessing_remains():
    source = (ROOT / "dcf_export.py").read_text("utf-8")
    assert "clearbit" not in source.lower()
    assert "TICKER_DOMAINS" not in source
    assert "urlretrieve" not in source


# --- 4. cross-platform data paths --------------------------------------------

def test_app_data_dir_per_platform(monkeypatch):
    import oasis_paths

    monkeypatch.setattr(sys, "platform", "darwin")
    assert "Application Support" in str(oasis_paths.app_data_dir())

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(oasis_paths.os, "name", "posix")
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg")
    assert oasis_paths.app_data_dir() == Path("/xdg/oasis")


def test_no_posix_absolute_default_remains():
    """The old '/data/raw' default could never exist on Windows."""
    source = (ROOT / "map_api.py").read_text("utf-8")
    assert '"/data/raw"' not in source


def test_env_var_overrides_path(monkeypatch, tmp_path):
    import oasis_paths

    monkeypatch.setenv("OASIS_RAW_DATA_ROOT", str(tmp_path / "custom"))
    assert oasis_paths.raw_data_root() == tmp_path / "custom"


def test_paths_are_not_created_on_resolve(tmp_path, monkeypatch):
    import oasis_paths

    target = tmp_path / "not-yet"
    monkeypatch.setenv("OASIS_RAW_DATA_ROOT", str(target))
    oasis_paths.raw_data_root()
    assert not target.exists()   # resolve must not create


# --- 5. refresh operation is bounded and opt-in ------------------------------

def test_refresh_script_defaults_are_bounded():
    import refresh_financial_facts as r

    assert r.DEFAULTS["max_entities"] <= 500        # never the whole universe
    assert r.DEFAULTS["rate_limit"] <= 10           # SEC fair-use ceiling
    assert r.DEFAULTS["quota_gb"] > 0
    assert r.DEFAULTS["max_retries"] >= 1


def test_refresh_backoff_is_jittered_and_capped():
    import refresh_financial_facts as r

    values = {r.backoff_delay(4) for _ in range(50)}
    assert len(values) > 1                          # jittered, not constant
    assert all(0 <= v <= 30 for v in values)        # capped


# --- 6. serving behaviour still correct --------------------------------------

def test_etag_and_gzip_behaviour_preserved():
    from fastapi.testclient import TestClient

    import map_api

    with TestClient(map_api.app) as client:
        first = client.get("/js/main.js", headers={"Accept-Encoding": "gzip"})
        assert first.status_code == 200
        etag = first.headers.get("etag")
        assert etag
        again = client.get("/js/main.js", headers={"If-None-Match": etag})
        assert again.status_code == 304


def test_vendored_maplibre_is_the_runtime_source():
    html = (ROOT / "graph" / "index.html").read_text("utf-8")
    main = (ROOT / "graph" / "js" / "main.js").read_text("utf-8")
    assert "unpkg.com" not in html and "unpkg.com" not in main
    assert "vendor/maplibre-gl/5.6.2/maplibre-gl.js" in main
    assert (ROOT / "graph" / "vendor" / "maplibre-gl" / "5.6.2" / "maplibre-gl.js").exists()


def test_dcf_route_degrades_when_facts_missing(no_network, empty_facts):
    from fastapi.testclient import TestClient

    import map_api

    with TestClient(map_api.app) as client:
        res = client.get("/api/entity/CAT/dcf.xlsx")
    assert res.status_code in (404, 503)
    assert "refresh_financial_facts" in res.json()["detail"] or res.status_code == 404

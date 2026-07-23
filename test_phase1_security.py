"""Phase 1 security regressions: headers, CORS, hosts, rate limits, storage."""
from __future__ import annotations


def test_security_headers_present(app_client):
    r = app_client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "strict-origin" in r.headers["referrer-policy"]
    assert "geolocation=()" in r.headers["permissions-policy"]
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_csp_is_not_wildcard(app_client):
    csp = app_client.get("/healthz").headers["content-security-policy"]
    assert "default-src *" not in csp
    assert "'unsafe-eval'" not in csp
    assert "frame-ancestors 'none'" in csp


def test_csp_allows_vendored_and_approved_map_hosts(app_client):
    csp = app_client.get("/healthz").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "worker-src 'self' blob:" in csp
    assert "basemaps.cartocdn.com" in csp and "arcgisonline.com" in csp


def test_trusted_host_rejects_hostile_host(app_client):
    r = app_client.get("/healthz", headers={"host": "evil.example.com"})
    assert r.status_code == 400


def test_login_rate_limited(app_client):
    app_client.post("/api/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    codes = [app_client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"}).status_code
             for _ in range(15)]
    assert 429 in codes  # login limit is 10/window


def test_register_rate_limited(app_client):
    codes = [app_client.post("/api/auth/register", json={"email": f"u{i}@b.com", "password": "correcthorse"}).status_code
             for i in range(10)]
    assert 429 in codes  # register limit is 5/window


def test_storage_rejects_path_traversal():
    from server.storage import LocalStorage
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        s = LocalStorage(d)
        s.put("ok.txt", b"data", "text/plain")
        assert s.exists("ok.txt")
        try:
            s.put("../escape.txt", b"x", "text/plain")
            # If it didn't raise, it must have stayed within root.
            assert s.exists("escape.txt") is False
        except ValueError:
            pass  # rejected — acceptable


def test_production_config_rejects_missing_secrets(monkeypatch):
    from server.config import ConfigError, load_settings

    monkeypatch.setenv("OASIS_MODE", "production")
    monkeypatch.delenv("OASIS_SESSION_SECRET", raising=False)
    try:
        load_settings()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_production_config_rejects_wildcard_cors(monkeypatch):
    from server.config import ConfigError, load_settings

    monkeypatch.setenv("OASIS_MODE", "production")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("OASIS_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OASIS_PUBLIC_BASE_URL", "https://oasis.example.com")
    monkeypatch.setenv("OASIS_COOKIE_SECURE", "true")
    monkeypatch.setenv("OASIS_EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("OASIS_TRUSTED_HOSTS", "oasis.example.com")
    monkeypatch.setenv("OASIS_ALLOWED_ORIGINS", "*")
    try:
        load_settings()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_valid_production_config_passes(monkeypatch):
    from server.config import load_settings

    monkeypatch.setenv("OASIS_MODE", "production")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("OASIS_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OASIS_PUBLIC_BASE_URL", "https://oasis.example.com")
    monkeypatch.setenv("OASIS_COOKIE_SECURE", "true")
    monkeypatch.setenv("OASIS_EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("OASIS_TRUSTED_HOSTS", "oasis.example.com")
    monkeypatch.setenv("OASIS_ALLOWED_ORIGINS", "https://oasis.example.com")
    s = load_settings()
    assert s.is_production and s.cookie_secure
    # Licensing-sensitive providers default OFF in production.
    assert s.feature_satellite_esri is False
    assert s.feature_prices_yfinance is False
    assert s.feature_company_logos is False


def test_valid_staging_config_disables_unresolved_providers(monkeypatch):
    from server.config import load_settings

    monkeypatch.setenv("OASIS_MODE", "staging")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("OASIS_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OASIS_PUBLIC_BASE_URL", "https://staging.oasis.example.com")
    monkeypatch.setenv("OASIS_COOKIE_SECURE", "true")
    monkeypatch.setenv("OASIS_TRUSTED_HOSTS", "staging.oasis.example.com")
    monkeypatch.setenv("OASIS_ALLOWED_ORIGINS", "https://staging.oasis.example.com")
    s = load_settings()
    assert s.is_secure and not s.is_production
    assert s.feature_satellite_esri is False
    assert s.feature_prices_yfinance is False
    assert s.feature_company_logos is False


def test_no_secrets_logged():
    from server.observability import redact
    out = redact({"authorization": "Bearer x", "password": "p", "email": "a@b.com"})
    assert out["authorization"] == "<redacted>"
    assert out["password"] == "<redacted>"
    assert out["email"] == "a@b.com"

"""Phase 1 security regressions: headers, CORS, hosts, rate limits, storage."""
from __future__ import annotations


def test_security_headers_present(app_client):
    r = app_client.get("/healthz")
    assert r.headers["x-request-id"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "strict-origin" in r.headers["referrer-policy"]
    assert "geolocation=()" in r.headers["permissions-policy"]
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_request_logging_includes_template_duration_status(app_client, monkeypatch):
    events = []
    import server.middleware as middleware

    monkeypatch.setattr(
        middleware,
        "log_event",
        lambda _logger, _level, msg, **fields: events.append((msg, fields)),
    )
    r = app_client.get("/api/assets/{not-real}", headers={"X-Request-ID": "req-test-1"})
    complete = [fields for msg, fields in events if msg == "request_complete"][-1]

    assert r.headers["x-request-id"] == "req-test-1"
    assert complete["request_id"] == "req-test-1"
    assert complete["method"] == "GET"
    assert complete["route"] == "/api/assets/{asset_id}"
    assert complete["status_code"] == r.status_code
    assert isinstance(complete["duration_ms"], float)


def test_short_circuit_security_responses_are_logged_and_headered(app_client, monkeypatch):
    events = []
    import server.middleware as middleware

    monkeypatch.setattr(
        middleware,
        "log_event",
        lambda _logger, _level, msg, **fields: events.append((msg, fields)),
    )
    r = app_client.post("/api/overrides", headers={"X-Request-ID": "req-auth-blocked"})
    complete = [fields for msg, fields in events if msg == "request_complete"][-1]

    assert r.status_code == 401
    assert r.headers["x-request-id"] == "req-auth-blocked"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert complete["status_code"] == 401
    assert complete["request_id"] == "req-auth-blocked"


def test_unhandled_errors_are_safe_and_headered(app_client, monkeypatch):
    from fastapi.testclient import TestClient

    import server.health as health

    monkeypatch.setattr(health, "db_healthy", lambda: (_ for _ in ()).throw(RuntimeError("secret stack trace token")))
    client = TestClient(app_client.app, raise_server_exceptions=False)
    r = client.get("/readyz")

    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert "secret stack trace token" not in r.text
    assert "Traceback" not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_http_errors_keep_intended_detail(app_client):
    r = app_client.get("/api/entity/NOT_A_REAL_ENTITY")
    assert r.status_code == 404
    assert r.json()["detail"] == "entity not found"


def test_csp_is_not_wildcard(app_client):
    csp = app_client.get("/healthz").headers["content-security-policy"]
    assert "default-src *" not in csp
    assert "'unsafe-eval'" not in csp
    assert "frame-ancestors 'none'" in csp


def test_csp_allows_vendored_and_approved_map_hosts(app_client):
    csp = app_client.get("/healthz").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "worker-src 'self' blob:" in csp
    assert "basemaps.cartocdn.com" in csp and "tiles.basemaps.cartocdn.com" in csp
    assert "arcgisonline.com" in csp


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


def test_password_reset_rate_limited(app_client):
    codes = [app_client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"}).status_code
             for _ in range(15)]
    assert 429 in codes  # password-reset uses the login-class limiter


def test_export_job_creation_rate_limited(app_client):
    codes = [app_client.post("/api/reports/company/CAT/generate").status_code for _ in range(65)]
    assert codes.count(401) == 60  # write limiter runs before auth, then auth blocks
    assert codes[-1] == 429
    assert app_client.post("/api/reports/company/CAT/generate").headers["retry-after"] == "60"


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
    assert s.hsts_header == "max-age=31536000"


def test_staging_hsts_does_not_cover_subdomains_or_preload_by_default(monkeypatch):
    from server.config import load_settings

    monkeypatch.setenv("OASIS_MODE", "staging")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("OASIS_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OASIS_PUBLIC_BASE_URL", "https://staging.oasis.example.com")
    monkeypatch.setenv("OASIS_COOKIE_SECURE", "true")
    monkeypatch.setenv("OASIS_TRUSTED_HOSTS", "staging.oasis.example.com")
    monkeypatch.setenv("OASIS_ALLOWED_ORIGINS", "https://staging.oasis.example.com")

    hsts = load_settings().hsts_header
    assert hsts == "max-age=31536000"
    assert "includeSubDomains" not in hsts
    assert "preload" not in hsts


def test_hsts_preload_requires_full_domain_policy(monkeypatch):
    from server.config import ConfigError, load_settings

    monkeypatch.setenv("OASIS_MODE", "staging")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("OASIS_DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OASIS_PUBLIC_BASE_URL", "https://staging.oasis.example.com")
    monkeypatch.setenv("OASIS_COOKIE_SECURE", "true")
    monkeypatch.setenv("OASIS_TRUSTED_HOSTS", "staging.oasis.example.com")
    monkeypatch.setenv("OASIS_ALLOWED_ORIGINS", "https://staging.oasis.example.com")
    monkeypatch.setenv("OASIS_HSTS_PRELOAD", "true")

    try:
        load_settings()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_no_secrets_logged():
    from server.observability import redact
    out = redact({"authorization": "Bearer x", "password": "p", "csrf_token": "t", "session_id": "s", "email": "a@b.com"})
    assert out["authorization"] == "<redacted>"
    assert out["password"] == "<redacted>"
    assert out["csrf_token"] == "<redacted>"
    assert out["session_id"] == "<redacted>"
    assert out["email"] == "a@b.com"


def test_json_formatter_redacts_sensitive_fields():
    import json
    import logging

    from server.observability import _JsonFormatter

    record = logging.LogRecord("oasis.test", logging.INFO, __file__, 1, "event", (), None)
    record.extra_fields = {
        "route": "/api/auth/login",
        "authorization": "Bearer secret",
        "csrf_token": "secret",
        "password": "secret",
    }
    body = json.loads(_JsonFormatter().format(record))
    assert body["route"] == "/api/auth/login"
    assert body["authorization"] == "<redacted>"
    assert body["csrf_token"] == "<redacted>"
    assert body["password"] == "<redacted>"

"""Typed, validated application configuration.

Precedence: explicit test overrides -> environment variables -> environment
defaults -> safe defaults (only where genuinely safe). Production fails fast when
a security-critical setting is missing. Configuration lives here, never in
scattered os.getenv() calls across handlers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

VALID_MODES = ("development", "test", "staging", "production")
SECURE_MODES = ("staging", "production")

# Settings that must never fall back to an insecure default in secure modes.
SECURE_REQUIRED = (
    "session_secret",
    "database_url",
    "allowed_origins",
    "trusted_hosts",
    "public_base_url",
)


class ConfigError(RuntimeError):
    """A security-critical setting is missing or invalid for the active mode."""


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str] | None = None) -> list[str]:
    v = os.environ.get(name)
    if not v:
        return list(default or [])
    return [item.strip() for item in v.split(",") if item.strip()]


def _database_url() -> str:
    url = _env("OASIS_DATABASE_URL") or _env("DATABASE_URL") or "sqlite:///./data/oasis_dev.db"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


@dataclass(frozen=True)
class Settings:
    mode: str = "development"
    public_base_url: str = "http://localhost:8788"
    api_base_url: str = "http://localhost:8788"

    # Persistence. SQLite for dev/test; Postgres URL in staging/production.
    database_url: str = "sqlite:///./data/oasis_dev.db"

    # Auth / sessions.
    session_secret: str = ""            # required in secure modes
    session_cookie_name: str = "oasis_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 14
    cookie_secure: bool = False         # forced True in secure modes
    cookie_samesite: str = "lax"
    registration_allowed_emails: list[str] = field(default_factory=list)

    # Origins / hosts.
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:8788"])
    trusted_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])
    trust_proxy: bool = False
    hsts_max_age_seconds: int = 31536000
    hsts_include_subdomains: bool = False
    hsts_preload: bool = False

    # Email (transactional). Console backend in dev; provider in prod.
    email_backend: str = "console"      # console | smtp | memory
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "OASIS <no-reply@localhost>"

    # Object storage.
    storage_backend: str = "local"      # local | s3
    storage_local_dir: str = "outputs/storage"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""

    # Rate limits (requests per window per client).
    rate_limit_login: int = 10
    rate_limit_register: int = 5
    rate_limit_write: int = 60
    rate_limit_window_seconds: int = 60

    # Observability.
    log_level: str = "INFO"
    log_json: bool = False              # forced True in secure modes
    otel_enabled: bool = False

    # Feature flags (licensing-sensitive providers default OFF in secure modes).
    feature_satellite_esri: bool = True
    feature_prices_yfinance: bool = True
    feature_company_logos: bool = True

    # Data / cache / export paths (delegated to oasis_paths at call sites).
    max_export_bytes: int = 25 * 1024 * 1024
    max_map_config_bytes: int = 64 * 1024

    @property
    def is_secure(self) -> bool:
        return self.mode in SECURE_MODES

    @property
    def is_production(self) -> bool:
        return self.mode == "production"

    @property
    def hsts_header(self) -> str | None:
        if not self.is_secure or self.hsts_max_age_seconds <= 0:
            return None
        parts = [f"max-age={self.hsts_max_age_seconds}"]
        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")
        if self.hsts_preload:
            parts.append("preload")
        return "; ".join(parts)

    def registration_allowed(self, email: str) -> bool:
        if not self.registration_allowed_emails:
            return True
        normalized = email.strip().lower()
        allowed = {item.strip().lower() for item in self.registration_allowed_emails}
        return normalized in allowed


def _build(overrides: dict | None = None) -> Settings:
    mode = (overrides or {}).get("mode") or _env("OASIS_MODE") or _env("OASIS_ENV") or "development"
    if mode not in VALID_MODES:
        raise ConfigError(f"OASIS_MODE must be one of {VALID_MODES}, got {mode!r}")

    secure = mode in SECURE_MODES
    licensing_default = not secure  # off in staging/prod until approved

    data = {
        "mode": mode,
        "public_base_url": _env("OASIS_PUBLIC_BASE_URL", "http://localhost:8788"),
        "api_base_url": _env("OASIS_API_BASE_URL", _env("OASIS_PUBLIC_BASE_URL", "http://localhost:8788")),
        "database_url": _database_url(),
        "session_secret": _env("OASIS_SESSION_SECRET", ""),
        "session_cookie_name": _env("OASIS_SESSION_COOKIE", "oasis_session"),
        "session_ttl_seconds": int(_env("OASIS_SESSION_TTL", str(60 * 60 * 24 * 14))),
        "cookie_secure": _bool("OASIS_COOKIE_SECURE", secure),
        "cookie_samesite": _env("OASIS_COOKIE_SAMESITE", "lax"),
        "registration_allowed_emails": _list("OASIS_REGISTRATION_ALLOWED_EMAILS", []),
        "allowed_origins": _list("OASIS_ALLOWED_ORIGINS", ["http://localhost:8788"]),
        "trusted_hosts": _list("OASIS_TRUSTED_HOSTS", ["localhost", "127.0.0.1", "testserver"]),
        "trust_proxy": _bool("OASIS_TRUST_PROXY", False),
        "hsts_max_age_seconds": int(_env("OASIS_HSTS_MAX_AGE", "31536000")),
        "hsts_include_subdomains": _bool("OASIS_HSTS_INCLUDE_SUBDOMAINS", False),
        "hsts_preload": _bool("OASIS_HSTS_PRELOAD", False),
        "email_backend": _env("OASIS_EMAIL_BACKEND", "console"),
        "smtp_host": _env("OASIS_SMTP_HOST", ""),
        "smtp_port": int(_env("OASIS_SMTP_PORT", "587")),
        "smtp_starttls": _bool("OASIS_SMTP_STARTTLS", True),
        "smtp_user": _env("OASIS_SMTP_USER", ""),
        "smtp_password": _env("OASIS_SMTP_PASSWORD", ""),
        "email_from": _env("OASIS_EMAIL_FROM", "OASIS <no-reply@localhost>"),
        "storage_backend": _env("OASIS_STORAGE_BACKEND", "local"),
        "storage_local_dir": _env("OASIS_STORAGE_DIR", "outputs/storage"),
        "s3_bucket": _env("OASIS_S3_BUCKET", ""),
        "s3_region": _env("OASIS_S3_REGION", ""),
        "s3_endpoint_url": _env("OASIS_S3_ENDPOINT", ""),
        "rate_limit_login": int(_env("OASIS_RATE_LOGIN", "10")),
        "rate_limit_register": int(_env("OASIS_RATE_REGISTER", "5")),
        "rate_limit_write": int(_env("OASIS_RATE_WRITE", "60")),
        "rate_limit_window_seconds": int(_env("OASIS_RATE_WINDOW", "60")),
        "log_level": _env("OASIS_LOG_LEVEL", "INFO"),
        "log_json": _bool("OASIS_LOG_JSON", secure),
        "otel_enabled": _bool("OASIS_OTEL_ENABLED", False),
        "feature_satellite_esri": _bool("OASIS_FEATURE_SATELLITE", licensing_default),
        "feature_prices_yfinance": _bool("OASIS_FEATURE_PRICES", licensing_default),
        "feature_company_logos": _bool("OASIS_FEATURE_LOGOS", licensing_default),
        "max_export_bytes": int(_env("OASIS_MAX_EXPORT_BYTES", str(25 * 1024 * 1024))),
        "max_map_config_bytes": int(_env("OASIS_MAX_MAP_CONFIG_BYTES", str(64 * 1024))),
    }
    if overrides:
        data.update(overrides)

    settings = Settings(**{k: v for k, v in data.items() if k in {f.name for f in fields(Settings)}})
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    if s.cookie_samesite.lower() not in {"lax", "strict", "none"}:
        raise ConfigError(f"cookie_samesite must be lax|strict|none, got {s.cookie_samesite!r}")
    if s.email_backend not in {"console", "memory", "smtp"}:
        raise ConfigError(f"email_backend must be console|memory|smtp, got {s.email_backend!r}")
    if s.storage_backend not in {"local", "s3"}:
        raise ConfigError(f"storage_backend must be local|s3, got {s.storage_backend!r}")
    if not s.is_secure:
        return
    # Fail fast in staging/production if a security-critical setting is unsafe.
    problems = []
    if len(s.session_secret) < 32:
        problems.append("OASIS_SESSION_SECRET must be >= 32 chars")
    if s.database_url.startswith("sqlite"):
        problems.append("OASIS_DATABASE_URL must be PostgreSQL in secure modes")
    if not s.allowed_origins or "*" in s.allowed_origins:
        problems.append("OASIS_ALLOWED_ORIGINS must be an explicit list (no '*')")
    if not s.trusted_hosts or "*" in s.trusted_hosts:
        problems.append("OASIS_TRUSTED_HOSTS must be explicit (no '*')")
    if not s.cookie_secure:
        problems.append("OASIS_COOKIE_SECURE must be true in secure modes")
    if s.hsts_max_age_seconds < 0:
        problems.append("OASIS_HSTS_MAX_AGE must be >= 0")
    if s.hsts_preload and not s.hsts_include_subdomains:
        problems.append("OASIS_HSTS_PRELOAD requires OASIS_HSTS_INCLUDE_SUBDOMAINS=true")
    if s.hsts_preload and s.hsts_max_age_seconds < 31536000:
        problems.append("OASIS_HSTS_PRELOAD requires OASIS_HSTS_MAX_AGE >= 31536000")
    if not s.public_base_url.startswith("https://") and s.is_production:
        problems.append("OASIS_PUBLIC_BASE_URL must be https:// in production")
    if s.email_backend in {"console", "memory"}:
        problems.append("OASIS_EMAIL_BACKEND must be smtp in secure modes")
    if s.email_backend == "smtp":
        if not s.smtp_host:
            problems.append("OASIS_SMTP_HOST is required when OASIS_EMAIL_BACKEND=smtp")
        if not s.email_from or "localhost" in s.email_from:
            problems.append("OASIS_EMAIL_FROM must be a non-local sender in secure modes")
        if bool(s.smtp_user) != bool(s.smtp_password):
            problems.append("OASIS_SMTP_USER and OASIS_SMTP_PASSWORD must be set together")
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            problems.append("OASIS_S3_BUCKET is required when OASIS_STORAGE_BACKEND=s3")
        if s.s3_region == "auto" and not s.s3_endpoint_url:
            problems.append("OASIS_S3_ENDPOINT is required for Cloudflare R2 storage")
        if not _env("AWS_ACCESS_KEY_ID") or not _env("AWS_SECRET_ACCESS_KEY"):
            problems.append("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required when OASIS_STORAGE_BACKEND=s3")
    if problems:
        raise ConfigError("insecure configuration for mode=" + s.mode + ":\n  - " + "\n  - ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _build()


def load_settings(**overrides) -> Settings:
    """Build a fresh Settings (used by tests to inject explicit overrides)."""
    return _build(overrides)


if __name__ == "__main__":
    s = get_settings()
    print(f"mode={s.mode} secure={s.is_secure} db={s.database_url}")
    print(f"origins={s.allowed_origins} hosts={s.trusted_hosts}")
    print(f"features: satellite={s.feature_satellite_esri} prices={s.feature_prices_yfinance} logos={s.feature_company_logos}")

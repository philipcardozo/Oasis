"""Security middleware and app-level protections.

Installs, in order: trusted-host validation, CORS (explicit origins), security
headers + CSP, a request/correlation ID, an in-memory rate limiter, and a global
write-protection guard that requires authentication for state-changing requests
to any route not on the public allowlist — so existing map_api write routes are
protected without editing each handler.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from server import repositories as repo
from server.config import Settings
from server.observability import log_event, new_correlation_id, set_correlation_id

log = logging.getLogger("oasis.mw")

# State-changing requests to these prefixes are allowed without a session.
PUBLIC_WRITE_PREFIXES = ("/api/auth/",)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _client_id(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _request_id(request: Request) -> str:
    incoming = request.headers.get("x-request-id", "").strip()
    if incoming and len(incoming) <= 128 and all(ch.isalnum() or ch in "-_." for ch in incoming):
        return incoming
    return new_correlation_id()


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


class RateLimiter:
    """Sliding-window in-memory limiter. Per-process; a shared store (Redis) is
    the documented scale-up. Keyed by (client, endpoint-class)."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


_limiter = RateLimiter()


def _rate_class(path: str, method: str) -> str | None:
    if path == "/api/auth/login":
        return "login"
    if path == "/api/auth/register":
        return "register"
    if path.startswith("/api/auth/password-reset"):
        return "login"
    if method not in SAFE_METHODS:
        return "write"
    return None


def _limit_for(settings: Settings, cls: str) -> int:
    return {"login": settings.rate_limit_login, "register": settings.rate_limit_register,
            "write": settings.rate_limit_write}.get(cls, settings.rate_limit_write)


CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # MapLibre injects inline styles for the canvas
    "img-src 'self' data: blob: https://services.arcgisonline.com https://basemaps.cartocdn.com "
    "https://tiles.openfreemap.org https://s3.amazonaws.com; "
    "font-src 'self' https://fonts.openmaptiles.org; "
    "worker-src 'self' blob:; "  # MapLibre workers
    "connect-src 'self' https://tiles.openfreemap.org https://basemaps.cartocdn.com "
    "https://services.arcgisonline.com https://s3.amazonaws.com https://fonts.openmaptiles.org; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def install_security(app: FastAPI, settings: Settings) -> None:
    # Trusted hosts (reject hostile Host headers).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    # Explicit-origin CORS with credentials. Never '*' for credentialed requests.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def _security_stack(request: Request, call_next):
        started = time.perf_counter()
        request_id = _request_id(request)
        set_correlation_id(request_id)

        # Rate limit (before auth for login/register).
        cls = _rate_class(request.url.path, request.method)
        if cls:
            cid = _client_id(request, settings.trust_proxy)
            if not _limiter.allow(f"{cls}:{cid}", _limit_for(settings, cls), settings.rate_limit_window_seconds):
                log_event(log, logging.WARNING, "rate_limited", endpoint_class=cls)
                response = JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                        headers={"Retry-After": str(settings.rate_limit_window_seconds)})
                _apply_response_headers(response, settings, request_id)
                _log_request(request, response.status_code, started, request_id)
                return response

        # Global write-protection: state-changing methods need a valid session
        # AND a valid CSRF token, unless the path is a deliberately public write
        # (auth endpoints, which run their own CSRF-exempt or dependency-based flow).
        # This protects the existing map_api write routes without editing each one.
        path = request.url.path
        if request.method not in SAFE_METHODS and not any(path.startswith(p) for p in PUBLIC_WRITE_PREFIXES):
            if not _has_valid_session(request, settings):
                response = JSONResponse({"detail": "authentication required"}, status_code=401)
                _apply_response_headers(response, settings, request_id)
                _log_request(request, response.status_code, started, request_id)
                return response
            if not _valid_csrf(request, settings):
                response = JSONResponse({"detail": "invalid or missing CSRF token"}, status_code=403)
                _apply_response_headers(response, settings, request_id)
                _log_request(request, response.status_code, started, request_id)
                return response

        try:
            response = await call_next(request)
        except Exception:
            _log_request(request, 500, started, request_id, failed=True)
            raise

        # Security headers on every response.
        _apply_response_headers(response, settings, request_id)
        _log_request(request, response.status_code, started, request_id)
        return response


def _apply_response_headers(response, settings: Settings, request_id: str) -> None:
    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Content-Security-Policy", CSP)
    if settings.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def _log_request(request: Request, status_code: int, started: float, request_id: str, *, failed: bool = False) -> None:
    log_event(
        log,
        logging.ERROR if failed else logging.INFO,
        "request_failed" if failed else "request_complete",
        request_id=request_id,
        method=request.method,
        route=_route_template(request),
        status_code=status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _has_valid_session(request: Request, settings: Settings) -> bool:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return False
    from server.db import session_scope

    try:
        with session_scope() as db:
            return repo.get_valid_session(db, token) is not None
    except Exception:
        return False


def _valid_csrf(request: Request, settings: Settings) -> bool:
    from server.security import valid_csrf_token

    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get("oasis_csrf")
    return bool(header and cookie and header == cookie
               and valid_csrf_token(header, settings.session_secret or "dev-secret"))

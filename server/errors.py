"""Safe error responses for the composed API."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.config import get_settings
from server.middleware import CSP
from server.observability import correlation_id, log_event

log = logging.getLogger("oasis.errors")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception):
        log_event(
            log,
            logging.ERROR,
            "unhandled_exception",
            method=request.method,
            route=getattr(request.scope.get("route"), "path", request.url.path),
            exception_type=type(exc).__name__,
        )
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Content-Security-Policy": CSP,
        }
        if cid := correlation_id():
            headers["X-Request-ID"] = cid
        if get_settings().is_secure:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return JSONResponse({"detail": "internal server error"}, status_code=500, headers=headers)

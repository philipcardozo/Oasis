"""Phase 1 composition root.

Builds a FRESH FastAPI application that reuses the existing map_api routes and
adds authentication, authorization, map-slot persistence, security middleware,
and health endpoints. It does NOT mutate the shared map_api.app singleton, so it
composes cleanly in tests and per-worker in production.

Production entrypoint:  uvicorn server.app:app

Phase 0 request-path guarantees (no external downloads, lazy loading) are
inherited unchanged — this module adds a security perimeter around them.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Mount

from server.config import get_settings
from server.observability import configure_logging

log = logging.getLogger("oasis.app")

DOC_ROUTE_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    from map_api import app as core_app

    from server.auth import router as auth_router
    from server.health import router as health_router
    from server.mapslots import router as mapslots_router
    from server.middleware import install_security

    docs_enabled = not settings.is_secure
    app = FastAPI(
        title="OASIS",
        lifespan=core_app.router.lifespan_context,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Reuse the core app's routes. Route objects are app-agnostic; keep the
    # catch-all StaticFiles Mount ("") last so API routers match first. The
    # composed app owns documentation routes so they are not duplicated in dev
    # and can be disabled entirely in secure modes.
    core_routes = list(core_app.router.routes)
    core_static = [r for r in core_routes if isinstance(r, Mount) and r.path == ""]
    core_api = [
        r
        for r in core_routes
        if r not in core_static and getattr(r, "path", None) not in DOC_ROUTE_PATHS
    ]
    app.router.routes.extend(core_api)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(mapslots_router)

    app.router.routes.extend(core_static)  # catch-all last

    # Preserve the Phase 0 gzip behaviour on the fresh app.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Security middleware wraps everything (incl. reused map_api write routes).
    install_security(app, settings)

    log.info("OASIS app assembled mode=%s routes=%d", settings.mode, len(app.routes))
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8788, reload=False)

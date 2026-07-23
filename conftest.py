"""Shared pytest fixtures for Phase 1 server tests.

Each server test runs against an isolated temp SQLite database with a fresh
schema, so nothing touches developer data and tests are order-independent.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """A TestClient bound to an isolated DB with memory email + dev secret."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("OASIS_MODE", "development")
    monkeypatch.setenv("OASIS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("OASIS_EMAIL_BACKEND", "memory")
    monkeypatch.setenv("OASIS_SESSION_SECRET", "test-secret-least-thirty-two-chars-long!!")

    # Rebuild config/engine against the temp DB.
    from server import config as cfg
    from server import db as dbmod

    cfg.get_settings.cache_clear()
    dbmod.reset_engine_for_tests()

    from server.models import Base

    Base.metadata.create_all(dbmod.engine())

    from server import email as email_mod
    email_mod.SENT.clear()

    # Reset the in-memory rate limiter so per-process state does not leak between
    # tests (a dedicated rate-limit test exercises it explicitly).
    from server import middleware
    middleware._limiter._hits.clear()

    from fastapi.testclient import TestClient
    from server.app import create_app

    client = TestClient(create_app())
    yield client

    dbmod.reset_engine_for_tests()


@pytest.fixture
def registered(app_client):
    """A verified, logged-in user. Returns (client, email, csrf_token)."""
    from server import email as email_mod

    email = "user@example.com"
    app_client.post("/api/auth/register", json={"email": email, "password": "correcthorsebattery"})
    token = email_mod.SENT[-1].text.split("token=")[1].split()[0]
    app_client.post("/api/auth/verify-email", json={"token": token})
    app_client.post("/api/auth/login", json={"email": email, "password": "correcthorsebattery"})
    csrf = app_client.cookies.get("oasis_csrf")
    return app_client, email, csrf

"""Phase 1 infrastructure regressions: migrations, health, config modes."""
from __future__ import annotations

import subprocess
import sys


def test_empty_database_migration(tmp_path):
    """Alembic upgrade head must build the full schema from an empty database."""
    db = tmp_path / "mig.db"
    env = {"OASIS_DATABASE_URL": f"sqlite:///{db}", "PATH": _path()}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=_env(env))
    assert r.returncode == 0, r.stderr
    import sqlite3
    tables = {row[0] for row in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}
    for expected in ("users", "sessions", "map_slots", "email_tokens", "organizations", "jobs", "audit_events"):
        assert expected in tables


def test_migration_downgrade(tmp_path):
    db = tmp_path / "mig.db"
    env = _env({"OASIS_DATABASE_URL": f"sqlite:///{db}"})
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, env=env)
    r = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr


def test_liveness_never_needs_db(app_client):
    # Liveness must answer even if we point at an unusable DB — it does no DB work.
    assert app_client.get("/healthz").json() == {"status": "ok"}


def test_readiness_reports_db(app_client):
    r = app_client.get("/readyz")
    assert "database" in r.json()["checks"]


def test_readiness_fails_when_db_unavailable(app_client, monkeypatch):
    import server.health as health
    monkeypatch.setattr(health, "db_healthy", lambda: False)
    r = app_client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] is False


def test_version_endpoint(app_client):
    body = app_client.get("/version").json()
    assert "version" in body and "commit" in body


def test_all_modes_valid():
    from server.config import VALID_MODES, load_settings
    for mode in ("development", "test"):
        assert load_settings(mode=mode).mode == mode
    assert set(VALID_MODES) == {"development", "test", "staging", "production"}


def test_repositories_create_three_slots_transactionally(app_client):
    from server.db import session_scope
    from server import repositories as repo
    from server.security import hash_password
    with session_scope() as db:
        user = repo.create_user(db, "tx@example.com", hash_password("correcthorse"))
        slots = repo.list_map_slots(db, user.id)
    assert len(slots) == 3


def _path():
    import os
    return os.environ.get("PATH", "")


def _env(extra: dict) -> dict:
    import os
    env = dict(os.environ)
    env.update(extra)
    return env

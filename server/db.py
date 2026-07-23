"""Database engine and session management.

SQLAlchemy 2.0. Schema is Postgres-compatible; dev/test default to SQLite so the
suite runs without a server. Route handlers never touch the engine directly —
they go through repositories with an injected session.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from server.config import get_settings

_engine = None
_SessionFactory = None


def _make_engine(url: str):
    if url.startswith("sqlite"):
        eng = create_engine(url, future=True, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _rec):  # enforce FKs on SQLite too
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng
    # Postgres (staging/production): bounded pool, pre-ping to survive restarts.
    return create_engine(url, future=True, pool_pre_ping=True, pool_size=10, max_overflow=20)


def engine():
    global _engine
    if _engine is None:
        _engine = _make_engine(get_settings().database_url)
    return _engine


def session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=engine(), class_=Session, expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error."""
    s = session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency — one session per request, committed at the end."""
    s = session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def db_healthy() -> bool:
    from sqlalchemy import text

    try:
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine_for_tests():
    """Drop cached engine/session so a test can point at a fresh DB URL."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
    get_settings.cache_clear()

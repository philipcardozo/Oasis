"""FastAPI dependencies for authentication and authorization.

current_user resolves the session cookie to a User; the authz helpers turn that
into role/ownership guards. These are the building blocks route handlers use —
authentication alone is never treated as authorization.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from server import repositories as repo
from server.config import Settings, get_settings
from server.db import get_db
from server.models import User
from server.security import valid_csrf_token


def _cookie_token(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


def optional_user(request: Request, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)) -> User | None:
    token = _cookie_token(request, settings)
    if not token:
        return None
    sess = repo.get_valid_session(db, token)
    if not sess:
        return None
    user = repo.get_user(db, sess.user_id)
    if not user or user.status != "active":
        return None
    repo.touch_session(db, sess)
    request.state.session_id = sess.id
    return user


def require_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "authentication required")
    return user


def require_verified_user(user: User = Depends(require_user)) -> User:
    if not user.is_verified:
        raise HTTPException(403, "email verification required")
    return user


def require_csrf(request: Request, user: User = Depends(require_user),
                 settings: Settings = Depends(get_settings)) -> User:
    """Double-submit CSRF for cookie-authenticated state changes."""
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get("oasis_csrf")
    if not header or not cookie or header != cookie or not valid_csrf_token(header, settings.session_secret or "dev-secret"):
        raise HTTPException(403, "invalid or missing CSRF token")
    return user


def require_org_role(org_id_param: str = "org_id", roles: tuple[str, ...] = ("owner", "admin", "member")):
    """Factory: require the user to hold one of `roles` in the path's org."""
    def _dep(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
        org_id = request.path_params.get(org_id_param)
        membership = repo.get_membership(db, org_id, user.id) if org_id else None
        if not membership or membership.status != "active" or membership.role not in roles:
            raise HTTPException(403, "insufficient organization role")
        return user
    return _dep

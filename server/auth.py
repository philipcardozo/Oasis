"""Account and session lifecycle: register, verify, login, logout, reset,
password change, session listing/revocation. Cookie-based opaque sessions.

No tokens in localStorage; the session token lives only in an HttpOnly cookie.
Auth failures are uniform to avoid user enumeration.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from server import email as email_mod
from server import repositories as repo
from server.config import Settings, get_settings
from server.db import get_db
from server.deps import require_csrf, require_user
from server.models import User
from server.observability import correlation_id, log_event
from server.security import (
    hash_password,
    ip_prefix,
    make_csrf_token,
    new_token,
    verify_password,
)

log = logging.getLogger("oasis.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

VERIFY_TTL = 60 * 60 * 24     # 24h
RESET_TTL = 60 * 60          # 1h


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetCompleteIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=1024)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name, token,
        max_age=settings.session_ttl_seconds, httponly=True,
        secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/",
    )
    # CSRF cookie is readable by JS (double-submit) but useless without the session.
    csrf = make_csrf_token(settings.session_secret or "dev-secret")
    response.set_cookie("oasis_csrf", csrf, max_age=settings.session_ttl_seconds,
                        httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/")


def _clear_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("oasis_csrf", path="/")


def _issue_session(response: Response, request: Request, db: Session, user: User, settings: Settings) -> None:
    raw = new_token()
    client_ip = request.client.host if request.client else None
    repo.create_session(db, user.id, raw, settings.session_ttl_seconds,
                        user_agent=request.headers.get("user-agent"), ip_prefix=ip_prefix(client_ip))
    _set_session_cookie(response, raw, settings)


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    existing = repo.get_user_by_email(db, body.email)
    if existing:
        # Do not reveal that the email is taken; behave like a fresh registration.
        log_event(log, logging.INFO, "register duplicate", correlation_id=correlation_id())
        return {"ok": True, "message": "check your email to verify your account"}
    user = repo.create_user(db, body.email, hash_password(body.password),
                            feature_satellite_esri=settings.feature_satellite_esri)
    raw = new_token()
    repo.create_email_token(db, user.id, raw, "verify", VERIFY_TTL)
    email_mod.send_verification(user.email, raw, settings)
    repo.record_audit(db, "auth.register", actor_id=user.id, resource_type="user", resource_id=user.id,
                      correlation_id=correlation_id())
    return {"ok": True, "message": "check your email to verify your account"}


@router.post("/verify-email")
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    tok = repo.consume_email_token(db, body.token, "verify")
    if not tok:
        raise HTTPException(400, "invalid or expired verification token")
    user = repo.get_user(db, tok.user_id)
    if user:
        repo.mark_verified(db, user)
        repo.record_audit(db, "auth.verify", actor_id=user.id, resource_type="user", resource_id=user.id)
    return {"ok": True, "verified": True}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    user = repo.get_user_by_email(db, body.email)
    ok = False
    new_hash = None
    if user and user.status == "active":
        ok, new_hash = verify_password(body.password, user.password_hash)
    if not ok or not user:
        repo.record_audit(db, "auth.login", result="fail", correlation_id=correlation_id(),
                          meta={"reason": "bad_credentials"})
        raise HTTPException(401, "invalid email or password")
    if new_hash:  # argon2 params changed -> migrate hash on successful login
        user.password_hash = new_hash
    repo.touch_login(db, user)
    _issue_session(response, request, db, user, settings)
    repo.record_audit(db, "auth.login", actor_id=user.id, result="ok", correlation_id=correlation_id())
    return {"ok": True, "user": {"id": user.id, "email": user.email, "verified": user.is_verified}}


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(require_csrf),
           db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    sid = getattr(request.state, "session_id", None)
    if sid:
        repo.revoke_session(db, user.id, sid)
    _clear_cookies(response, settings)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(require_csrf),
               db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    n = repo.revoke_all_sessions(db, user.id)
    _clear_cookies(response, settings)
    repo.record_audit(db, "auth.logout_all", actor_id=user.id, meta={"revoked": n})
    return {"ok": True, "revoked": n}


@router.get("/sessions")
def sessions(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {"sessions": [
        {"id": s.id, "created_at": s.created_at.isoformat(), "last_used_at": s.last_used_at.isoformat(),
         "expires_at": s.expires_at.isoformat(), "revoked": s.revoked_at is not None,
         "user_agent": s.user_agent, "ip_prefix": s.ip_prefix}
        for s in repo.list_sessions(db, user.id)
    ]}


@router.delete("/sessions/{session_id}")
def revoke(session_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    if not repo.revoke_session(db, user.id, session_id):
        raise HTTPException(404, "session not found")
    repo.record_audit(db, "auth.session_revoke", actor_id=user.id, resource_type="session", resource_id=session_id)
    return {"ok": True}


@router.post("/password-reset/request")
def reset_request(body: ResetRequestIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    user = repo.get_user_by_email(db, body.email)
    if user and user.status == "active":  # silent for unknown emails (no enumeration)
        raw = new_token()
        repo.create_email_token(db, user.id, raw, "reset", RESET_TTL)
        email_mod.send_password_reset(user.email, raw, settings)
    return {"ok": True, "message": "if the account exists, a reset link has been sent"}


@router.post("/password-reset/complete")
def reset_complete(body: ResetCompleteIn, db: Session = Depends(get_db)):
    tok = repo.consume_email_token(db, body.token, "reset")
    if not tok:
        raise HTTPException(400, "invalid or expired reset token")
    user = repo.get_user(db, tok.user_id)
    if not user:
        raise HTTPException(400, "invalid or expired reset token")
    user.password_hash = hash_password(body.password)
    repo.revoke_all_sessions(db, user.id)  # reset invalidates every session
    repo.record_audit(db, "auth.password_reset", actor_id=user.id)
    return {"ok": True}


@router.post("/password-change")
def password_change(body: ChangePasswordIn, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    ok, _ = verify_password(body.current_password, user.password_hash)
    if not ok:
        raise HTTPException(403, "current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    repo.record_audit(db, "auth.password_change", actor_id=user.id)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"id": user.id, "email": user.email, "verified": user.is_verified,
            "status": user.status, "created_at": user.created_at.isoformat()}


@router.delete("/account")
def delete_account(response: Response, user: User = Depends(require_csrf), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    repo.anonymize_user(db, user)
    _clear_cookies(response, settings)
    repo.record_audit(db, "auth.account_delete", actor_id=user.id)
    return {"ok": True}

"""Repository layer. Route handlers coordinate these; they never write SQL.

Each function takes an explicit Session so transactions are controlled by the
caller (the request-scoped get_db dependency or session_scope).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from server.models import (
    AuditEvent,
    EmailToken,
    Job,
    MapSlot,
    Organization,
    OrgMembership,
    SessionRow,
    User,
    utcnow,
)
from server.security import hash_token

DEFAULT_SLOTS = [
    (1, "Standard Research", "standard"),
    (2, "Dark Network View", "dark"),
    (3, "Satellite Site Analysis", "satellite"),
]


def normalize_email(email: str) -> str:
    return email.strip().lower()


# --- users -------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email_normalized == normalize_email(email)))


def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, email: str, password_hash: str) -> User:
    user = User(email=email.strip(), email_normalized=normalize_email(email), password_hash=password_hash)
    db.add(user)
    db.flush()
    create_default_map_slots(db, user.id)
    return user


def mark_verified(db: Session, user: User) -> None:
    user.is_verified = True


def touch_login(db: Session, user: User) -> None:
    user.last_login_at = utcnow()


def anonymize_user(db: Session, user: User) -> None:
    user.status = "deleted"
    user.email = f"deleted-{user.id}@invalid"
    user.email_normalized = f"deleted-{user.id}@invalid"
    user.password_hash = "!"  # unusable
    user.anonymized_at = utcnow()
    revoke_all_sessions(db, user.id)


# --- sessions ----------------------------------------------------------------

def create_session(db: Session, user_id: str, raw_token: str, ttl_seconds: int,
                   user_agent: str | None = None, ip_prefix: str | None = None) -> SessionRow:
    row = SessionRow(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        expires_at=utcnow() + timedelta(seconds=ttl_seconds),
        user_agent=(user_agent or "")[:400] or None,
        ip_prefix=ip_prefix,
    )
    db.add(row)
    db.flush()
    return row


def get_valid_session(db: Session, raw_token: str) -> SessionRow | None:
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == hash_token(raw_token)))
    if not row or row.revoked_at is not None or row.expires_at <= utcnow():
        return None
    return row


def touch_session(db: Session, row: SessionRow) -> None:
    row.last_used_at = utcnow()


def list_sessions(db: Session, user_id: str) -> list[SessionRow]:
    return list(db.scalars(select(SessionRow).where(SessionRow.user_id == user_id).order_by(SessionRow.created_at.desc())))


def revoke_session(db: Session, user_id: str, session_id: str) -> bool:
    row = db.get(SessionRow, session_id)
    if not row or row.user_id != user_id or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    return True


def revoke_all_sessions(db: Session, user_id: str, keep_id: str | None = None) -> int:
    rows = db.scalars(select(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None)))
    n = 0
    for row in rows:
        if keep_id and row.id == keep_id:
            continue
        row.revoked_at = utcnow()
        n += 1
    return n


# --- email tokens ------------------------------------------------------------

def create_email_token(db: Session, user_id: str, raw_token: str, purpose: str, ttl_seconds: int) -> EmailToken:
    tok = EmailToken(user_id=user_id, token_hash=hash_token(raw_token), purpose=purpose,
                     expires_at=utcnow() + timedelta(seconds=ttl_seconds))
    db.add(tok)
    db.flush()
    return tok


def consume_email_token(db: Session, raw_token: str, purpose: str) -> EmailToken | None:
    tok = db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(raw_token), EmailToken.purpose == purpose))
    if not tok or tok.consumed_at is not None or tok.expires_at <= utcnow():
        return None
    tok.consumed_at = utcnow()
    return tok


# --- map slots ---------------------------------------------------------------

def create_default_map_slots(db: Session, user_id: str) -> list[MapSlot]:
    slots = []
    for number, name, basemap in DEFAULT_SLOTS:
        slot = MapSlot(user_id=user_id, slot_number=number, name=name, basemap=basemap,
                       is_active=(number == 1), config={})
        db.add(slot)
        slots.append(slot)
    db.flush()
    return slots


def list_map_slots(db: Session, user_id: str) -> list[MapSlot]:
    return list(db.scalars(
        select(MapSlot).where(MapSlot.user_id == user_id, MapSlot.archived_at.is_(None)).order_by(MapSlot.slot_number)
    ))


def get_map_slot(db: Session, user_id: str, slot_id: str) -> MapSlot | None:
    slot = db.get(MapSlot, slot_id)
    if not slot or slot.user_id != user_id or slot.archived_at is not None:
        return None
    return slot


def set_active_slot(db: Session, user_id: str, slot_id: str) -> bool:
    target = get_map_slot(db, user_id, slot_id)
    if not target:
        return False
    for slot in list_map_slots(db, user_id):
        slot.is_active = (slot.id == slot_id)
    return True


# --- organizations -----------------------------------------------------------

def create_org(db: Session, name: str, slug: str, owner_id: str) -> Organization:
    org = Organization(name=name, slug=slug, owner_id=owner_id)
    db.add(org)
    db.flush()
    db.add(OrgMembership(org_id=org.id, user_id=owner_id, role="owner"))
    return org


def get_membership(db: Session, org_id: str, user_id: str) -> OrgMembership | None:
    return db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id, OrgMembership.user_id == user_id))


# --- audit -------------------------------------------------------------------

def record_audit(db: Session, action: str, actor_id: str | None = None, resource_type: str | None = None,
                 resource_id: str | None = None, result: str = "ok", correlation_id: str | None = None,
                 meta: dict | None = None) -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id,
                      result=result, correlation_id=correlation_id, meta=meta or {}))


# --- jobs --------------------------------------------------------------------

def enqueue_job(db: Session, kind: str, payload: dict, owner_id: str | None = None,
                correlation_id: str | None = None, max_attempts: int = 3) -> Job:
    job = Job(kind=kind, payload=payload, owner_id=owner_id, correlation_id=correlation_id, max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job

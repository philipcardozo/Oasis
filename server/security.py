"""Security primitives: password hashing, token minting/hashing, CSRF.

No plaintext passwords are ever stored or logged. Tokens are stored only as
SHA-256 hashes; the raw token exists solely in the cookie / email link.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Argon2id with sensible interactive cost. Tunable without breaking old hashes:
# verify_password re-hashes on login when parameters change (migration support).
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if len(password) > 1024:
        raise ValueError("password too long")
    return _ph.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, str | None]:
    """Return (ok, new_hash_or_None). new_hash is set when a rehash is needed."""
    try:
        _ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False, None
    new_hash = None
    try:
        if _ph.check_needs_rehash(stored_hash):
            new_hash = _ph.hash(password)
    except Exception:
        new_hash = None
    return True, new_hash


def new_token() -> str:
    """A high-entropy opaque token (URL-safe). Raw value is never persisted."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# --- CSRF: double-submit token signed with the session secret ----------------

def make_csrf_token(session_secret: str) -> str:
    raw = secrets.token_urlsafe(24)
    sig = hmac.new(session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw}.{sig}"


def valid_csrf_token(token: str | None, session_secret: str) -> bool:
    if not token or "." not in token:
        return False
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(sig, expected)


def ip_prefix(ip: str | None) -> str | None:
    """Truncate an IP for privacy-preserving session metadata."""
    if not ip:
        return None
    if ":" in ip:  # IPv6 -> /48-ish
        return ":".join(ip.split(":")[:3]) + "::/48"
    parts = ip.split(".")
    if len(parts) == 4:  # IPv4 -> /24
        return ".".join(parts[:3]) + ".0/24"
    return None

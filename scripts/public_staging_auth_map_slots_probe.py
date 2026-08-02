#!/usr/bin/env python3
"""Probe public-staging auth, email-token, CSRF, and map-slot behavior.

This script is designed for the real public staging URL. It stores sanitized
evidence only: no passwords, tokens, cookies, authorization values, or complete
email addresses are written to disk.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")


@dataclass(frozen=True)
class TestUser:
    label: str
    email_env: str
    password_env: str
    verify_token_env: str

    @property
    def email(self) -> str:
        return required_env(self.email_env)

    @property
    def password(self) -> str:
        return required_env(self.password_env)

    @property
    def verify_token(self) -> str:
        return os.environ.get(self.verify_token_env, "")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def env_headers(items: list[str]) -> tuple[dict[str, str], list[str]]:
    headers: dict[str, str] = {}
    names: list[str] = []
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--header must be Name=ENV_VAR, got {item!r}")
        name, env_name = item.split("=", 1)
        value = os.environ.get(env_name)
        if not value:
            raise SystemExit(f"missing environment variable for header {name}: {env_name}")
        headers[name] = value
        names.append(name)
    return headers, names


def email_domain(email: str) -> str:
    if "@" not in email:
        return "<invalid>"
    return email.rsplit("@", 1)[1].lower()


def safe_base_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="<redacted>" if parsed.query else "").geturl().rstrip("/")


def public_base_url_failures(url: str) -> list[str]:
    parsed = urlparse(url)
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("base URL is not HTTPS")
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        failures.append("base URL is not public")
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("base URL is a reserved documentation hostname")
    return failures


def timed(call: Callable[[], requests.Response]) -> tuple[float, requests.Response]:
    started = time.perf_counter()
    response = call()
    return (time.perf_counter() - started) * 1000, response


def response_sample(duration_ms: float, response: requests.Response) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "status_code": response.status_code,
        "duration_ms": round(duration_ms, 3),
        "body_bytes": len(response.content),
    }
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            sample["json_keys"] = sorted(str(key) for key in payload.keys())
    return sample


def cookie_value(session: requests.Session, name: str) -> str:
    for cookie in session.cookies:
        if cookie.name == name:
            return cookie.value or ""
    return ""


def cookie_security(session: requests.Session) -> dict[str, Any]:
    out = {
        "session_cookie_present": False,
        "session_cookie_secure": False,
        "session_cookie_httponly": False,
        "session_cookie_samesite": None,
        "session_cookie_path": None,
        "session_cookie_domain_host_only": None,
        "csrf_cookie_present": False,
        "csrf_cookie_secure": False,
        "csrf_cookie_samesite": None,
        "csrf_cookie_path": None,
        "csrf_cookie_domain_host_only": None,
    }
    for cookie in session.cookies:
        rest = {str(key).lower(): value for key, value in getattr(cookie, "_rest", {}).items()}
        rest_keys = set(rest)
        if cookie.name == "oasis_session":
            out["session_cookie_present"] = True
            out["session_cookie_secure"] = bool(cookie.secure)
            out["session_cookie_httponly"] = "httponly" in rest_keys
            out["session_cookie_samesite"] = str(rest.get("samesite") or "").lower() or None
            out["session_cookie_path"] = cookie.path
            out["session_cookie_domain_host_only"] = not bool(getattr(cookie, "domain_specified", False))
        elif cookie.name == "oasis_csrf":
            out["csrf_cookie_present"] = True
            out["csrf_cookie_secure"] = bool(cookie.secure)
            out["csrf_cookie_samesite"] = str(rest.get("samesite") or "").lower() or None
            out["csrf_cookie_path"] = cookie.path
            out["csrf_cookie_domain_host_only"] = not bool(getattr(cookie, "domain_specified", False))
    return out


def summarize(name: str, samples: list[dict[str, Any]], target_ms: int | None = None) -> dict[str, Any]:
    durations = [float(item["duration_ms"]) for item in samples]
    statuses = sorted({int(item["status_code"]) for item in samples})
    row: dict[str, Any] = {
        "name": name,
        "samples": len(samples),
        "status_codes": statuses,
        "p50_ms": round(statistics.median(durations), 3) if durations else None,
        "p95_ms": round(percentile(durations, 95), 3) if durations else None,
    }
    if target_ms is not None:
        row["target_ms"] = target_ms
        row["target_met"] = bool(durations and row["p95_ms"] <= target_ms and statuses == [200])
    else:
        row["target_ms"] = None
        row["target_met"] = None
    return row


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def make_session(args: argparse.Namespace, headers: dict[str, str]) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": "oasis-public-staging-auth-map-slots-probe",
        **headers,
    })
    if args.proxy_server:
        session.proxies.update({"http": args.proxy_server, "https": args.proxy_server})
    session.verify = not args.insecure
    return session


def request_samples(
    session: requests.Session,
    method: str,
    url: str,
    samples: int,
    *,
    timeout: int,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    out = []
    for _ in range(samples):
        duration, response = timed(lambda: session.request(method, url, timeout=timeout, **kwargs))
        out.append(response_sample(duration, response))
    return out


def register_and_verify(
    session: requests.Session,
    base_url: str,
    user: TestUser,
    timeout: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "label": user.label,
        "email_env": user.email_env,
        "email_domain": email_domain(user.email),
        "verification_token_env": user.verify_token_env,
        "verification_token_supplied": bool(user.verify_token),
    }
    duration, response = timed(lambda: session.post(
        f"{base_url}/api/auth/register",
        json={"email": user.email, "password": user.password},
        timeout=timeout,
    ))
    out["register"] = response_sample(duration, response)
    if user.verify_token:
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/verify-email",
            json={"token": user.verify_token},
            timeout=timeout,
        ))
        out["verify_email"] = response_sample(duration, response)
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/verify-email",
            json={"token": user.verify_token},
            timeout=timeout,
        ))
        out["verify_email_reuse"] = response_sample(duration, response)
    return out


def login(session: requests.Session, base_url: str, user: TestUser, timeout: int, password: str | None = None) -> dict[str, Any]:
    duration, response = timed(lambda: session.post(
        f"{base_url}/api/auth/login",
        json={"email": user.email, "password": password or user.password},
        timeout=timeout,
    ))
    return response_sample(duration, response)


def slot_numbers(slots: list[dict[str, Any]]) -> list[int]:
    return sorted(int(item.get("slot_number")) for item in slots if item.get("slot_number") is not None)


def same_value_slot_body(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": slot.get("name"),
        "description": slot.get("description"),
        "basemap": slot.get("basemap"),
        "config": slot.get("config") or {},
        "version": slot.get("version"),
    }


def rejected_status(sample: dict[str, Any], allowed: set[int]) -> bool:
    status = sample.get("status_code")
    return isinstance(status, int) and status in allowed


def exercise_slots(
    session: requests.Session,
    base_url: str,
    csrf: str,
    samples: int,
    timeout: int,
    enforce_targets: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    checks: dict[str, Any] = {}
    measurements: list[dict[str, Any]] = []

    duration, slots_response = timed(lambda: session.get(f"{base_url}/api/map-slots", timeout=timeout))
    checks["slot_list"] = response_sample(duration, slots_response)
    slots = slots_response.json().get("slots", []) if slots_response.status_code == 200 else []
    checks["default_map_slot_count"] = len(slots)
    checks["default_map_slot_numbers"] = slot_numbers(slots)
    if not slots:
        return checks, measurements, None

    slot = slots[0]
    slot_id = str(slot["id"])
    target_auth = 50 if enforce_targets else None
    target_read = 100 if enforce_targets else None
    target_write = 200 if enforce_targets else None

    measurements.append(summarize(
        "session validation GET /api/auth/me",
        request_samples(session, "GET", f"{base_url}/api/auth/me", samples, timeout=timeout),
        target_auth,
    ))
    measurements.append(summarize(
        "map-slot list GET /api/map-slots",
        request_samples(session, "GET", f"{base_url}/api/map-slots", samples, timeout=timeout),
        target_read,
    ))
    measurements.append(summarize(
        "map-slot read GET /api/map-slots/{id}",
        request_samples(session, "GET", f"{base_url}/api/map-slots/{slot_id}", samples, timeout=timeout),
        target_read,
    ))

    write_samples = []
    current_slot = slot
    for _ in range(samples):
        latest = session.get(f"{base_url}/api/map-slots/{slot_id}", timeout=timeout)
        current_slot = latest.json() if latest.status_code == 200 else current_slot
        body = same_value_slot_body(current_slot)
        duration, response = timed(lambda: session.put(
            f"{base_url}/api/map-slots/{slot_id}",
            json=body,
            headers={"X-CSRF-Token": csrf},
            timeout=timeout,
        ))
        write_samples.append(response_sample(duration, response))
        if response.status_code == 200:
            current_slot = response.json()
    measurements.append(summarize("map-slot write PUT /api/map-slots/{id}", write_samples, target_write))

    stale_body = same_value_slot_body(current_slot)
    fresh = session.get(f"{base_url}/api/map-slots/{slot_id}", timeout=timeout)
    if fresh.status_code == 200:
        fresh_body = same_value_slot_body(fresh.json())
        session.put(
            f"{base_url}/api/map-slots/{slot_id}",
            json=fresh_body,
            headers={"X-CSRF-Token": csrf},
            timeout=timeout,
        )
    duration, response = timed(lambda: session.put(
        f"{base_url}/api/map-slots/{slot_id}",
        json=stale_body,
        headers={"X-CSRF-Token": csrf},
        timeout=timeout,
    ))
    checks["stale_version_conflict"] = response_sample(duration, response)

    duration, response = timed(lambda: session.post(
        f"{base_url}/api/map-slots",
        json={"slot_number": 4, "name": "Fourth Slot Probe", "basemap": "standard", "config": {}},
        headers={"X-CSRF-Token": csrf},
        timeout=timeout,
    ))
    checks["fourth_slot_create_attempt"] = response_sample(duration, response)

    duration, response = timed(lambda: session.post(
        f"{base_url}/api/map-slots/import",
        json={"slot_number": 4, "config_json": json.dumps({"kind": "map_slot", "basemap": "standard", "config": {}})},
        headers={"X-CSRF-Token": csrf},
        timeout=timeout,
    ))
    checks["fourth_slot_import_attempt"] = response_sample(duration, response)
    return checks, measurements, current_slot


def password_reset(
    session: requests.Session,
    base_url: str,
    user: TestUser,
    args: argparse.Namespace,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "reset_token_env": args.user_a_reset_token_env,
        "reset_token_supplied": bool(os.environ.get(args.user_a_reset_token_env, "")),
        "reset_password_env": args.user_a_reset_password_env,
        "reset_password_supplied": bool(os.environ.get(args.user_a_reset_password_env, "")),
    }
    duration, response = timed(lambda: session.post(
        f"{base_url}/api/auth/password-reset/request",
        json={"email": user.email},
        timeout=args.timeout,
    ))
    out["request"] = response_sample(duration, response)
    unknown_email = os.environ.get(args.unknown_reset_email_env, f"unknown-public-reset-{int(time.time())}@example.com")
    duration, response = timed(lambda: session.post(
        f"{base_url}/api/auth/password-reset/request",
        json={"email": unknown_email},
        timeout=args.timeout,
    ))
    out["unknown_account_request"] = response_sample(duration, response)

    token = os.environ.get(args.user_a_reset_token_env, "")
    password = os.environ.get(args.user_a_reset_password_env, "")
    if token and password:
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/password-reset/complete",
            json={"token": token, "password": password},
            timeout=args.timeout,
        ))
        out["complete"] = response_sample(duration, response)
        cookie_before_login = cookie_value(session, "oasis_session")
        out["post_reset_login"] = login(session, base_url, user, args.timeout, password=password)
        cookie_after_login = cookie_value(session, "oasis_session")
        out["session_cookie_rotated_after_login"] = bool(cookie_before_login and cookie_after_login and cookie_before_login != cookie_after_login)
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/password-reset/complete",
            json={"token": token, "password": password},
            timeout=args.timeout,
        ))
        out["token_reuse"] = response_sample(duration, response)
    return out


def account_lifecycle(
    session: requests.Session,
    base_url: str,
    user: TestUser,
    args: argparse.Namespace,
    headers: dict[str, str],
) -> dict[str, Any]:
    changed_password = os.environ.get(args.lifecycle_changed_password_env, "")
    csrf = cookie_value(session, "oasis_csrf")
    out: dict[str, Any] = {
        "changed_password_env": args.lifecycle_changed_password_env,
        "changed_password_supplied": bool(changed_password),
        "csrf_cookie_present": bool(csrf),
    }

    duration, response = timed(lambda: session.get(f"{base_url}/api/auth/sessions", timeout=args.timeout))
    out["session_list"] = response_sample(duration, response)

    revoke_target = make_session(args, headers)
    revoke_target.headers["User-Agent"] = "oasis-public-staging-auth-map-slots-probe-revoke-target"
    out["revoke_target_login"] = login(revoke_target, base_url, user, args.timeout)
    duration, response = timed(lambda: session.get(f"{base_url}/api/auth/sessions", timeout=args.timeout))
    out["session_list_after_revoke_target_login"] = response_sample(duration, response)

    revoke_session_id = ""
    if response.status_code == 200:
        for row in (response.json().get("sessions") or []):
            if "revoke-target" in str(row.get("user_agent") or "") and row.get("revoked") is False:
                revoke_session_id = str(row.get("id") or "")
                break
    out["revoke_target_session_found"] = bool(revoke_session_id)

    if csrf and revoke_session_id:
        duration, response = timed(lambda: session.delete(
            f"{base_url}/api/auth/sessions/{revoke_session_id}",
            headers={"X-CSRF-Token": csrf},
            timeout=args.timeout,
        ))
        out["session_revoke"] = response_sample(duration, response)
        duration, response = timed(lambda: revoke_target.get(f"{base_url}/api/auth/me", timeout=args.timeout))
        out["revoked_session_me"] = response_sample(duration, response)

    if csrf and changed_password:
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/password-change",
            json={"current_password": user.password, "new_password": changed_password},
            headers={"X-CSRF-Token": csrf},
            timeout=args.timeout,
        ))
        out["password_change"] = response_sample(duration, response)

        old_login_session = make_session(args, headers)
        out["old_password_login_after_change"] = login(old_login_session, base_url, user, args.timeout)

        changed_session = make_session(args, headers)
        out["new_password_login_after_change"] = login(changed_session, base_url, user, args.timeout, password=changed_password)
        changed_csrf = cookie_value(changed_session, "oasis_csrf")
        out["changed_session_csrf_cookie_present"] = bool(changed_csrf)

        if changed_csrf:
            duration, response = timed(lambda: changed_session.post(
                f"{base_url}/api/auth/logout-all",
                headers={"X-CSRF-Token": changed_csrf},
                timeout=args.timeout,
            ))
            out["logout_all"] = response_sample(duration, response)
            duration, response = timed(lambda: changed_session.get(f"{base_url}/api/auth/me", timeout=args.timeout))
            out["post_logout_all_me"] = response_sample(duration, response)
            duration, response = timed(lambda: session.get(f"{base_url}/api/auth/me", timeout=args.timeout))
            out["original_session_after_logout_all_me"] = response_sample(duration, response)

        delete_session = make_session(args, headers)
        out["delete_login"] = login(delete_session, base_url, user, args.timeout, password=changed_password)
        delete_csrf = cookie_value(delete_session, "oasis_csrf")
        out["delete_session_csrf_cookie_present"] = bool(delete_csrf)
        if delete_csrf:
            duration, response = timed(lambda: delete_session.delete(
                f"{base_url}/api/auth/account",
                headers={"X-CSRF-Token": delete_csrf},
                timeout=args.timeout,
            ))
            out["account_delete"] = response_sample(duration, response)
            duration, response = timed(lambda: delete_session.get(f"{base_url}/api/auth/me", timeout=args.timeout))
            out["post_delete_me"] = response_sample(duration, response)
            deleted_login_session = make_session(args, headers)
            out["post_delete_login"] = login(deleted_login_session, base_url, user, args.timeout, password=changed_password)
    return out


def evaluate(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    users = payload.get("users") or {}
    checks = payload.get("checks") or {}

    for label in ("user_a", "user_b", "lifecycle_user"):
        user = users.get(label) or {}
        if (user.get("register") or {}).get("status_code") not in {200, 201, 202}:
            failures.append(f"{label} registration did not return a generic success")
        if not user.get("verification_token_supplied"):
            failures.append(f"{label} verification token env is missing")
        elif (user.get("verify_email") or {}).get("status_code") != 200:
            failures.append(f"{label} email verification did not succeed")
        elif (user.get("verify_email_reuse") or {}).get("status_code") != 400:
            failures.append(f"{label} email verification token reuse was not rejected")
        if (user.get("login") or {}).get("status_code") != 200:
            failures.append(f"{label} login did not succeed")

    if checks.get("session_cookie_secure") is not True:
        failures.append("session cookie is missing or not Secure")
    if checks.get("session_cookie_httponly") is not True:
        failures.append("session cookie is missing or not HttpOnly")
    if checks.get("session_cookie_samesite") != "lax":
        failures.append("session cookie SameSite is not lax")
    if checks.get("session_cookie_path") != "/":
        failures.append("session cookie path is not /")
    if checks.get("session_cookie_domain_host_only") is not True:
        failures.append("session cookie is not host-only")
    if checks.get("csrf_cookie_secure") is not True:
        failures.append("CSRF cookie is missing or not Secure")
    if checks.get("csrf_cookie_samesite") != "lax":
        failures.append("CSRF cookie SameSite is not lax")
    if checks.get("csrf_cookie_path") != "/":
        failures.append("CSRF cookie path is not /")
    if checks.get("csrf_cookie_domain_host_only") is not True:
        failures.append("CSRF cookie is not host-only")
    if (checks.get("csrf_rejection") or {}).get("status_code") != 403:
        failures.append("CSRF rejection status is not 403")
    if checks.get("default_map_slot_count") != 3 or checks.get("default_map_slot_numbers") != [1, 2, 3]:
        failures.append("exactly-three map-slot evidence is missing")
    if (checks.get("cross_user_slot_read_denied") or {}).get("status_code") not in {403, 404}:
        failures.append("cross-user map-slot read denial is missing or not 403/404")
    if (checks.get("stale_version_conflict") or {}).get("status_code") != 409:
        failures.append("stale-version conflict did not return 409")
    if not rejected_status(checks.get("fourth_slot_create_attempt") or {}, {404, 405, 409, 422}):
        failures.append("fourth map-slot create attempt was not rejected")
    if not rejected_status(checks.get("fourth_slot_import_attempt") or {}, {422}):
        failures.append("fourth map-slot import attempt was not rejected with 422")

    reset = checks.get("password_reset") or {}
    if (reset.get("request") or {}).get("status_code") != 200:
        failures.append("password reset request did not return 200")
    if (reset.get("unknown_account_request") or {}).get("status_code") != 200:
        failures.append("unknown-account password reset request did not return generic 200")
    if (reset.get("request") or {}).get("json_keys") != (reset.get("unknown_account_request") or {}).get("json_keys"):
        failures.append("known and unknown password reset responses have different JSON shape")
    if not reset.get("reset_token_supplied"):
        failures.append("password reset token env is missing")
    elif not reset.get("reset_password_supplied"):
        failures.append("password reset replacement password env is missing")
    elif (reset.get("complete") or {}).get("status_code") != 200:
        failures.append("password reset completion did not return 200")
    elif (reset.get("post_reset_login") or {}).get("status_code") != 200:
        failures.append("post-reset login did not return 200")
    elif reset.get("session_cookie_rotated_after_login") is not True:
        failures.append("session cookie did not rotate after post-reset login")
    elif (reset.get("token_reuse") or {}).get("status_code") != 400:
        failures.append("password reset token reuse was not rejected")

    lifecycle = checks.get("account_lifecycle") or {}
    if not lifecycle.get("changed_password_supplied"):
        failures.append("lifecycle changed password env is missing")
    if not lifecycle.get("csrf_cookie_present"):
        failures.append("lifecycle CSRF cookie is missing")
    if (lifecycle.get("session_list") or {}).get("status_code") != 200:
        failures.append("session listing did not return 200")
    if (lifecycle.get("revoke_target_login") or {}).get("status_code") != 200:
        failures.append("revoke-target login did not return 200")
    if not lifecycle.get("revoke_target_session_found"):
        failures.append("revoke-target session was not found in session listing")
    if (lifecycle.get("session_revoke") or {}).get("status_code") != 200:
        failures.append("session revocation did not return 200")
    if (lifecycle.get("revoked_session_me") or {}).get("status_code") != 401:
        failures.append("revoked session was still usable")
    if (lifecycle.get("password_change") or {}).get("status_code") != 200:
        failures.append("password change did not return 200")
    if (lifecycle.get("old_password_login_after_change") or {}).get("status_code") != 401:
        failures.append("old password still logged in after password change")
    if (lifecycle.get("new_password_login_after_change") or {}).get("status_code") != 200:
        failures.append("new password login did not return 200 after password change")
    if (lifecycle.get("logout_all") or {}).get("status_code") != 200:
        failures.append("logout-all did not return 200")
    if (lifecycle.get("post_logout_all_me") or {}).get("status_code") != 401:
        failures.append("changed session remained usable after logout-all")
    if (lifecycle.get("original_session_after_logout_all_me") or {}).get("status_code") != 401:
        failures.append("original session remained usable after logout-all")
    if (lifecycle.get("delete_login") or {}).get("status_code") != 200:
        failures.append("delete-session login did not return 200")
    if (lifecycle.get("account_delete") or {}).get("status_code") != 200:
        failures.append("account deletion did not return 200")
    if (lifecycle.get("post_delete_me") or {}).get("status_code") != 401:
        failures.append("deleted account session remained usable")
    if (lifecycle.get("post_delete_login") or {}).get("status_code") != 401:
        failures.append("deleted account was still able to log in")

    for row in payload.get("measurements") or []:
        if row.get("target_met") is False:
            failures.append(f"latency target missed: {row.get('name')}")
        if 200 not in set(row.get("status_codes") or []):
            failures.append(f"measurement did not include HTTP 200: {row.get('name')}")
    if not payload.get("latency_targets_enforced"):
        warnings.append("latency targets were not enforced because this is external HTTP timing")
    return failures, warnings


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if not args.base_url:
        raise SystemExit("provide --base-url or STAGING_URL")
    base_url = args.base_url.rstrip("/")
    target_failures = public_base_url_failures(base_url)
    if target_failures:
        raise SystemExit("; ".join(target_failures))
    headers, header_names = env_headers(args.header)
    user_a = TestUser("user_a", args.user_a_email_env, args.user_a_password_env, args.user_a_verification_token_env)
    user_b = TestUser("user_b", args.user_b_email_env, args.user_b_password_env, args.user_b_verification_token_env)
    lifecycle_user = TestUser("lifecycle_user", args.lifecycle_email_env, args.lifecycle_password_env, args.lifecycle_verification_token_env)
    session_a = make_session(args, headers)
    session_b = make_session(args, headers)
    session_lifecycle = make_session(args, headers)

    users: dict[str, Any] = {
        "user_a": register_and_verify(session_a, base_url, user_a, args.timeout),
        "user_b": register_and_verify(session_b, base_url, user_b, args.timeout),
        "lifecycle_user": register_and_verify(session_lifecycle, base_url, lifecycle_user, args.timeout),
    }
    users["user_a"]["login"] = login(session_a, base_url, user_a, args.timeout)
    users["user_b"]["login"] = login(session_b, base_url, user_b, args.timeout)
    users["lifecycle_user"]["login"] = login(session_lifecycle, base_url, lifecycle_user, args.timeout)

    checks: dict[str, Any] = {}
    checks.update(cookie_security(session_a))
    csrf = cookie_value(session_a, "oasis_csrf")
    checks["csrf_cookie_present"] = bool(csrf)

    slot_checks: dict[str, Any] = {}
    measurements: list[dict[str, Any]] = []
    slot = None
    if users["user_a"]["login"]["status_code"] == 200 and csrf:
        slot_checks, measurements, slot = exercise_slots(
            session_a,
            base_url,
            csrf,
            max(1, args.samples),
            args.timeout,
            args.enforce_app_targets,
        )
        checks.update(slot_checks)
        duration, response = timed(lambda: session_a.post(f"{base_url}/api/auth/logout", timeout=args.timeout))
        checks["csrf_rejection"] = response_sample(duration, response)

    if users["user_b"]["login"]["status_code"] == 200 and slot:
        duration, response = timed(lambda: session_b.get(f"{base_url}/api/map-slots/{slot['id']}", timeout=args.timeout))
        checks["cross_user_slot_read_denied"] = response_sample(duration, response)

    if users["user_a"]["login"]["status_code"] == 200:
        checks["password_reset"] = password_reset(session_a, base_url, user_a, args)

    if (
        users["lifecycle_user"]["login"]["status_code"] == 200
        and (users["lifecycle_user"].get("verify_email") or {}).get("status_code") == 200
    ):
        checks["account_lifecycle"] = account_lifecycle(session_lifecycle, base_url, lifecycle_user, args, headers)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": safe_base_url(base_url),
        "proxy_server": args.proxy_server,
        "verify_tls": not args.insecure,
        "auth_header_names_sent": header_names,
        "latency_targets_enforced": bool(args.enforce_app_targets),
        "samples_per_measurement": max(1, args.samples),
        "users": users,
        "checks": checks,
        "measurements": measurements,
    }
    failures, warnings = evaluate(payload)
    payload["failures"] = failures
    payload["warnings"] = warnings
    payload["verdict"] = "pass" if not failures else "investigate"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STAGING_URL", ""))
    parser.add_argument("--output", default=str(EVIDENCE / "27-public-auth-map-slots.json"))
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--proxy-server", default="")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--enforce-app-targets", action="store_true")
    parser.add_argument("--header", action="append", default=[], help="send Name=ENV_VAR without writing values to evidence")
    parser.add_argument("--user-a-email-env", default="OASIS_PUBLIC_TESTER_A_EMAIL")
    parser.add_argument("--user-a-password-env", default="OASIS_PUBLIC_TESTER_A_PASSWORD")
    parser.add_argument("--user-a-verification-token-env", default="OASIS_PUBLIC_TESTER_A_VERIFY_TOKEN")
    parser.add_argument("--user-a-reset-token-env", default="OASIS_PUBLIC_TESTER_A_RESET_TOKEN")
    parser.add_argument("--user-a-reset-password-env", default="OASIS_PUBLIC_TESTER_A_RESET_PASSWORD")
    parser.add_argument("--unknown-reset-email-env", default="OASIS_PUBLIC_UNKNOWN_RESET_EMAIL")
    parser.add_argument("--user-b-email-env", default="OASIS_PUBLIC_TESTER_B_EMAIL")
    parser.add_argument("--user-b-password-env", default="OASIS_PUBLIC_TESTER_B_PASSWORD")
    parser.add_argument("--user-b-verification-token-env", default="OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN")
    parser.add_argument("--lifecycle-email-env", default="OASIS_PUBLIC_LIFECYCLE_EMAIL")
    parser.add_argument("--lifecycle-password-env", default="OASIS_PUBLIC_LIFECYCLE_PASSWORD")
    parser.add_argument("--lifecycle-verification-token-env", default="OASIS_PUBLIC_LIFECYCLE_VERIFY_TOKEN")
    parser.add_argument("--lifecycle-changed-password-env", default="OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD")
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public auth/map-slot evidence to {output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"], "warnings": payload["warnings"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

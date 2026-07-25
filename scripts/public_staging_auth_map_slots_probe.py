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
        "csrf_cookie_present": False,
        "csrf_cookie_secure": False,
    }
    for cookie in session.cookies:
        rest_keys = {str(key).lower() for key in getattr(cookie, "_rest", {})}
        if cookie.name == "oasis_session":
            out["session_cookie_present"] = True
            out["session_cookie_secure"] = bool(cookie.secure)
            out["session_cookie_httponly"] = "httponly" in rest_keys
        elif cookie.name == "oasis_csrf":
            out["csrf_cookie_present"] = True
            out["csrf_cookie_secure"] = bool(cookie.secure)
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

    token = os.environ.get(args.user_a_reset_token_env, "")
    password = os.environ.get(args.user_a_reset_password_env, "")
    if token and password:
        duration, response = timed(lambda: session.post(
            f"{base_url}/api/auth/password-reset/complete",
            json={"token": token, "password": password},
            timeout=args.timeout,
        ))
        out["complete"] = response_sample(duration, response)
        out["post_reset_login"] = login(session, base_url, user, args.timeout, password=password)
    return out


def evaluate(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    users = payload.get("users") or {}
    checks = payload.get("checks") or {}

    for label in ("user_a", "user_b"):
        user = users.get(label) or {}
        if (user.get("register") or {}).get("status_code") not in {200, 201, 202}:
            failures.append(f"{label} registration did not return a generic success")
        if not user.get("verification_token_supplied"):
            failures.append(f"{label} verification token env is missing")
        elif (user.get("verify_email") or {}).get("status_code") != 200:
            failures.append(f"{label} email verification did not succeed")
        if (user.get("login") or {}).get("status_code") != 200:
            failures.append(f"{label} login did not succeed")

    if checks.get("session_cookie_secure") is not True:
        failures.append("session cookie is missing or not Secure")
    if checks.get("session_cookie_httponly") is not True:
        failures.append("session cookie is missing or not HttpOnly")
    if checks.get("csrf_cookie_secure") is not True:
        failures.append("CSRF cookie is missing or not Secure")
    if (checks.get("csrf_rejection") or {}).get("status_code") != 403:
        failures.append("CSRF rejection status is not 403")
    if checks.get("default_map_slot_count") != 3 or checks.get("default_map_slot_numbers") != [1, 2, 3]:
        failures.append("exactly-three map-slot evidence is missing")
    if (checks.get("cross_user_slot_read_denied") or {}).get("status_code") not in {403, 404}:
        failures.append("cross-user map-slot read denial is missing or not 403/404")
    if (checks.get("stale_version_conflict") or {}).get("status_code") != 409:
        failures.append("stale-version conflict did not return 409")

    reset = checks.get("password_reset") or {}
    if (reset.get("request") or {}).get("status_code") != 200:
        failures.append("password reset request did not return 200")
    if not reset.get("reset_token_supplied"):
        failures.append("password reset token env is missing")
    elif not reset.get("reset_password_supplied"):
        failures.append("password reset replacement password env is missing")
    elif (reset.get("complete") or {}).get("status_code") != 200:
        failures.append("password reset completion did not return 200")
    elif (reset.get("post_reset_login") or {}).get("status_code") != 200:
        failures.append("post-reset login did not return 200")

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
    headers, header_names = env_headers(args.header)
    user_a = TestUser("user_a", args.user_a_email_env, args.user_a_password_env, args.user_a_verification_token_env)
    user_b = TestUser("user_b", args.user_b_email_env, args.user_b_password_env, args.user_b_verification_token_env)
    session_a = make_session(args, headers)
    session_b = make_session(args, headers)

    users: dict[str, Any] = {
        "user_a": register_and_verify(session_a, base_url, user_a, args.timeout),
        "user_b": register_and_verify(session_b, base_url, user_b, args.timeout),
    }
    users["user_a"]["login"] = login(session_a, base_url, user_a, args.timeout)
    users["user_b"]["login"] = login(session_b, base_url, user_b, args.timeout)

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
    parser.add_argument("--user-b-email-env", default="OASIS_PUBLIC_TESTER_B_EMAIL")
    parser.add_argument("--user-b-password-env", default="OASIS_PUBLIC_TESTER_B_PASSWORD")
    parser.add_argument("--user-b-verification-token-env", default="OASIS_PUBLIC_TESTER_B_VERIFY_TOKEN")
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

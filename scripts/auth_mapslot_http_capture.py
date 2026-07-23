#!/usr/bin/env python3
"""Capture Phase 1 auth/session and map-slot latency over real HTTP.

The script starts server.app against a temporary SQLite database with the
memory email backend, then drives requests through an optional HTTP proxy such
as Proxyman. It does not touch developer data or staging secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
sys.path.insert(0, str(ROOT))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def timed(fn: Callable[[], requests.Response]) -> tuple[float, requests.Response]:
    started = time.perf_counter()
    response = fn()
    return (time.perf_counter() - started) * 1000, response


def response_sample(duration_ms: float, response: requests.Response) -> dict[str, Any]:
    return {
        "duration_ms": duration_ms,
        "status_code": response.status_code,
        "body_bytes": len(response.content),
        "cache_control": response.headers.get("cache-control"),
        "content_encoding": response.headers.get("content-encoding"),
        "content_length": response.headers.get("content-length"),
    }


def summarize(name: str, samples: list[dict[str, Any]], target_ms: float | None = None) -> dict[str, Any]:
    durations = [sample["duration_ms"] for sample in samples]
    out: dict[str, Any] = {
        "name": name,
        "samples": len(samples),
        "status_codes": sorted({sample["status_code"] for sample in samples}),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_bytes_min": min(sample["body_bytes"] for sample in samples),
        "body_bytes_max": max(sample["body_bytes"] for sample in samples),
        "content_encodings": sorted({sample["content_encoding"] for sample in samples if sample["content_encoding"]}),
        "cache_controls": sorted({sample["cache_control"] for sample in samples if sample["cache_control"]}),
        "sample_durations_ms": [round(sample["duration_ms"], 3) for sample in samples],
    }
    if target_ms is not None:
        out["target_ms"] = target_ms
        out["target_met"] = out["p95_ms"] < target_ms
    return out


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def configure_temp_app(tmpdir: Path):
    os.environ["OASIS_MODE"] = "development"
    os.environ["OASIS_DATABASE_URL"] = f"sqlite:///{tmpdir / 'auth-map-slot-http.db'}"
    os.environ["OASIS_EMAIL_BACKEND"] = "memory"
    os.environ["OASIS_SESSION_SECRET"] = "test-secret-least-thirty-two-chars-long!!"
    os.environ["OASIS_PUBLIC_BASE_URL"] = "http://127.0.0.1"
    os.environ["OASIS_LOG_LEVEL"] = "WARNING"

    from server import config as cfg
    from server import db as dbmod

    cfg.get_settings.cache_clear()
    dbmod.reset_engine_for_tests()

    from server.models import Base

    Base.metadata.create_all(dbmod.engine())

    from server import email as email_mod
    from server import middleware

    email_mod.SENT.clear()
    middleware._limiter._hits.clear()

    from server.app import create_app

    return create_app()


def start_server(app, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 120
    url = f"http://127.0.0.1:{port}/index.html"
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=0.75)
            if 200 <= response.status_code < 500:
                return server, thread
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(0.1)
    server.should_exit = True
    raise RuntimeError(f"server did not become ready: {url}; last_error={last_error}")


def session_for_proxy(proxy_server: str | None) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    if proxy_server:
        session.proxies.update({"http": proxy_server, "https": proxy_server})
    return session


def request_samples(
    session: requests.Session,
    method: str,
    url: str,
    samples: int,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out = []
    for _ in range(samples):
        duration, response = timed(lambda: session.request(method, url, headers=headers, json=json_body, timeout=20))
        out.append(response_sample(duration, response))
    return out


def one_shot_operation(
    session: requests.Session,
    operation: str,
    method: str,
    url: str,
    template: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    duration, response = timed(lambda: session.request(method, url, headers=headers, json=json_body, timeout=20))
    return {
        "operation": operation,
        "method": method,
        "template": template,
        **response_sample(duration, response),
    }


def email_token(text: str, param: str = "token") -> str:
    return text.split(f"{param}=", 1)[1].split()[0].split("&", 1)[0]


def current_slot(session: requests.Session, base_url: str, slot_id: str) -> dict[str, Any]:
    response = session.get(f"{base_url}/api/map-slots/{slot_id}", timeout=20)
    response.raise_for_status()
    return response.json()


def warmup_http_paths(session: requests.Session, base_url: str, slot_id: str, csrf: str) -> list[dict[str, Any]]:
    operations: list[tuple[str, Callable[[], requests.Response]]] = [
        ("GET /api/auth/me", lambda: session.get(f"{base_url}/api/auth/me", timeout=20)),
        ("GET /api/auth/sessions", lambda: session.get(f"{base_url}/api/auth/sessions", timeout=20)),
        ("GET /api/map-slots", lambda: session.get(f"{base_url}/api/map-slots", timeout=20)),
        ("GET /api/map-slots/{id}", lambda: session.get(f"{base_url}/api/map-slots/{slot_id}", timeout=20)),
        ("GET /api/map-slots/{id}/export", lambda: session.get(f"{base_url}/api/map-slots/{slot_id}/export", timeout=20)),
    ]
    out = []
    for name, fn in operations:
        duration, response = timed(fn)
        out.append({"operation": name, **response_sample(duration, response)})

    slot = current_slot(session, base_url, slot_id)
    duration, response = timed(
        lambda: session.put(
            f"{base_url}/api/map-slots/{slot_id}",
            headers={"X-CSRF-Token": csrf},
            json={"basemap": slot["basemap"], "version": slot["version"]},
            timeout=20,
        )
    )
    out.append({"operation": "PUT /api/map-slots/{id}", **response_sample(duration, response)})

    slot = current_slot(session, base_url, slot_id)
    duration, response = timed(
        lambda: session.post(
            f"{base_url}/api/map-slots/{slot_id}/rename",
            headers={"X-CSRF-Token": csrf},
            json={"name": slot["name"], "version": slot["version"]},
            timeout=20,
        )
    )
    out.append({"operation": "POST /api/map-slots/{id}/rename", **response_sample(duration, response)})
    return out


def capture_safe_extra_routes(
    session: requests.Session,
    base_url: str,
    csrf: str,
    email: str,
    password: str,
    slots: list[dict[str, Any]],
    proxy_server: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    from server import email as email_mod

    operations = [
        one_shot_operation(session, "health GET /healthz", "GET", f"{base_url}/healthz", "/healthz"),
        one_shot_operation(session, "readiness GET /readyz", "GET", f"{base_url}/readyz", "/readyz"),
        one_shot_operation(session, "version GET /version", "GET", f"{base_url}/version", "/version"),
    ]
    notes = []
    current_password = password
    current_csrf = csrf

    if len(slots) >= 2:
        operations.append(
            one_shot_operation(
                session,
                "map-slot duplicate POST /api/map-slots/{id}/duplicate-to/{target_id}",
                "POST",
                f"{base_url}/api/map-slots/{slots[0]['id']}/duplicate-to/{slots[1]['id']}",
                "/api/map-slots/{slot_id}/duplicate-to/{target_id}",
                headers={"X-CSRF-Token": current_csrf},
            )
        )

    before_reset_emails = len(email_mod.SENT)
    operations.append(
        one_shot_operation(
            session,
            "password reset request POST /api/auth/password-reset/request",
            "POST",
            f"{base_url}/api/auth/password-reset/request",
            "/api/auth/password-reset/request",
            json_body={"email": email},
        )
    )
    if len(email_mod.SENT) > before_reset_emails:
        reset_token = email_token(email_mod.SENT[-1].text)
        current_password = "reset-http-perf-password"
        operations.append(
            one_shot_operation(
                session,
                "password reset complete POST /api/auth/password-reset/complete",
                "POST",
                f"{base_url}/api/auth/password-reset/complete",
                "/api/auth/password-reset/complete",
                json_body={"token": reset_token, "password": current_password},
            )
        )
        login_response = session.post(
            f"{base_url}/api/auth/login",
            json={"email": email, "password": current_password},
            timeout=20,
        )
        notes.append({
            "operation": "post-reset relogin",
            "status_code": login_response.status_code,
            "body_bytes": len(login_response.content),
        })
        current_csrf = session.cookies.get("oasis_csrf") or current_csrf
    else:
        notes.append({"operation": "password reset complete skipped", "reason": "memory email token was not captured"})

    changed_password = "changed-http-perf-password"
    operations.append(
        one_shot_operation(
            session,
            "password change POST /api/auth/password-change",
            "POST",
            f"{base_url}/api/auth/password-change",
            "/api/auth/password-change",
            headers={"X-CSRF-Token": current_csrf},
            json_body={"current_password": current_password, "new_password": changed_password},
        )
    )
    current_password = changed_password

    secondary = session_for_proxy(proxy_server)
    secondary.headers.update({"User-Agent": "oasis-perf-secondary-session"})
    secondary_login = secondary.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": current_password},
        timeout=20,
    )
    notes.append({
        "operation": "secondary login for session revoke",
        "status_code": secondary_login.status_code,
        "body_bytes": len(secondary_login.content),
    })
    secondary_csrf = secondary.cookies.get("oasis_csrf") or ""
    secondary_sessions = secondary.get(f"{base_url}/api/auth/sessions", timeout=20)
    revoke_id = None
    if secondary_sessions.status_code == 200:
        for item in secondary_sessions.json().get("sessions", []):
            if item.get("user_agent") == "oasis-perf-secondary-session":
                revoke_id = item["id"]
                break
    if revoke_id:
        operations.append(
            one_shot_operation(
                secondary,
                "session revoke DELETE /api/auth/sessions/{session_id}",
                "DELETE",
                f"{base_url}/api/auth/sessions/{revoke_id}",
                "/api/auth/sessions/{session_id}",
                headers={"X-CSRF-Token": secondary_csrf},
            )
        )
    else:
        notes.append({"operation": "session revoke skipped", "reason": "secondary session id was not found"})

    login_response = session.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": current_password},
        timeout=20,
    )
    notes.append({
        "operation": "pre-logout-all relogin",
        "status_code": login_response.status_code,
        "body_bytes": len(login_response.content),
    })
    current_csrf = session.cookies.get("oasis_csrf") or current_csrf
    operations.append(
        one_shot_operation(
            session,
            "logout-all POST /api/auth/logout-all",
            "POST",
            f"{base_url}/api/auth/logout-all",
            "/api/auth/logout-all",
            headers={"X-CSRF-Token": current_csrf},
        )
    )

    delete_session = session_for_proxy(proxy_server)
    delete_email = "http-perf-delete-user@example.com"
    delete_password = "delete-http-perf-password"
    register_response = delete_session.post(
        f"{base_url}/api/auth/register",
        json={"email": delete_email, "password": delete_password},
        timeout=20,
    )
    notes.append({
        "operation": "delete-account register",
        "status_code": register_response.status_code,
        "body_bytes": len(register_response.content),
    })
    if email_mod.SENT:
        verify_token = email_token(email_mod.SENT[-1].text)
        verify_response = delete_session.post(
            f"{base_url}/api/auth/verify-email",
            json={"token": verify_token},
            timeout=20,
        )
        login_response = delete_session.post(
            f"{base_url}/api/auth/login",
            json={"email": delete_email, "password": delete_password},
            timeout=20,
        )
        notes.extend([
            {
                "operation": "delete-account verify",
                "status_code": verify_response.status_code,
                "body_bytes": len(verify_response.content),
            },
            {
                "operation": "delete-account login",
                "status_code": login_response.status_code,
                "body_bytes": len(login_response.content),
            },
        ])
        delete_csrf = delete_session.cookies.get("oasis_csrf") or ""
        operations.append(
            one_shot_operation(
                delete_session,
                "account delete DELETE /api/auth/account",
                "DELETE",
                f"{base_url}/api/auth/account",
                "/api/auth/account",
                headers={"X-CSRF-Token": delete_csrf},
            )
        )

    return operations, notes, current_password, current_csrf


def versioned_samples(
    session: requests.Session,
    method: str,
    base_url: str,
    slot_id: str,
    samples: int,
    csrf: str,
    body_for_index: Callable[[int, dict[str, Any]], dict[str, Any]],
    path_suffix: str = "",
) -> list[dict[str, Any]]:
    out = []
    for i in range(samples):
        slot = current_slot(session, base_url, slot_id)
        body = body_for_index(i, slot)
        duration, response = timed(
            lambda: session.request(
                method,
                f"{base_url}/api/map-slots/{slot_id}{path_suffix}",
                headers={"X-CSRF-Token": csrf},
                json=body,
                timeout=20,
            )
        )
        out.append(response_sample(duration, response))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--proxy-server", default=os.environ.get("OASIS_PROXY_SERVER", ""))
    parser.add_argument("--output-file", default="06-local-auth-and-map-slots-http.json")
    args = parser.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oasis-auth-map-slot-http-") as tmp:
        port = free_port()
        app = configure_temp_app(Path(tmp))
        server, server_thread = start_server(app, port)
        base_url = f"http://127.0.0.1:{port}"
        session = session_for_proxy(args.proxy_server or None)
        setup: dict[str, Any] = {"base_url": base_url}

        try:
            email = "http-perf-user@example.com"
            password = "correcthorsebattery"

            duration, response = timed(
                lambda: session.post(
                    f"{base_url}/api/auth/register",
                    json={"email": email, "password": password},
                    timeout=20,
                )
            )
            setup["register"] = response_sample(duration, response)

            from server import email as email_mod

            token = email_mod.SENT[-1].text.split("token=")[1].split()[0]
            duration, response = timed(
                lambda: session.post(f"{base_url}/api/auth/verify-email", json={"token": token}, timeout=20)
            )
            setup["verify_email"] = response_sample(duration, response)

            duration, response = timed(
                lambda: session.post(
                    f"{base_url}/api/auth/login",
                    json={"email": email, "password": password},
                    timeout=20,
                )
            )
            setup["login"] = response_sample(duration, response)

            csrf = session.cookies.get("oasis_csrf") or ""
            setup["csrf_cookie_present"] = bool(csrf)
            setup["session_cookie_present"] = bool(session.cookies.get("oasis_session"))

            slots_response = session.get(f"{base_url}/api/map-slots", timeout=20)
            slots_response.raise_for_status()
            slots = slots_response.json()["slots"]
            slot_id = slots[0]["id"]
            warmup_operations = warmup_http_paths(session, base_url, slot_id, csrf)

            export_response = session.get(f"{base_url}/api/map-slots/{slot_id}/export", timeout=20)
            export_response.raise_for_status()
            exported = export_response.json()

            measurements = [
                summarize(
                    "session validation GET /api/auth/me",
                    request_samples(session, "GET", f"{base_url}/api/auth/me", args.samples),
                    50,
                ),
                summarize(
                    "session list GET /api/auth/sessions",
                    request_samples(session, "GET", f"{base_url}/api/auth/sessions", args.samples),
                ),
                summarize(
                    "map-slot list GET /api/map-slots",
                    request_samples(session, "GET", f"{base_url}/api/map-slots", args.samples),
                    100,
                ),
                summarize(
                    "map-slot read GET /api/map-slots/{id}",
                    request_samples(session, "GET", f"{base_url}/api/map-slots/{slot_id}", args.samples),
                    100,
                ),
                summarize(
                    "map-slot write PUT /api/map-slots/{id}",
                    versioned_samples(
                        session,
                        "PUT",
                        base_url,
                        slot_id,
                        args.samples,
                        csrf,
                        lambda i, slot: {"basemap": ["dark", "standard"][i % 2], "version": slot["version"]},
                    ),
                    200,
                ),
                summarize(
                    "map-slot rename POST /api/map-slots/{id}/rename",
                    versioned_samples(
                        session,
                        "POST",
                        base_url,
                        slot_id,
                        args.samples,
                        csrf,
                        lambda i, slot: {"name": f"HTTP Perf View {i}", "version": slot["version"]},
                        "/rename",
                    ),
                    200,
                ),
                summarize(
                    "map-slot export GET /api/map-slots/{id}/export",
                    request_samples(session, "GET", f"{base_url}/api/map-slots/{slot_id}/export", args.samples),
                ),
            ]

            import_body = {"slot_number": 2, "config_json": json.dumps(exported)}
            import_duration, import_response = timed(
                lambda: session.post(
                    f"{base_url}/api/map-slots/import",
                    headers={"X-CSRF-Token": csrf},
                    json=import_body,
                    timeout=20,
                )
            )
            reset_duration, reset_response = timed(
                lambda: session.post(
                    f"{base_url}/api/map-slots/{slot_id}/reset",
                    headers={"X-CSRF-Token": csrf},
                    timeout=20,
                )
            )
            activate_duration, activate_response = timed(
                lambda: session.post(
                    f"{base_url}/api/map-slots/{slot_id}/activate",
                    headers={"X-CSRF-Token": csrf},
                    timeout=20,
                )
            )
            csrf_duration, csrf_response = timed(lambda: session.post(f"{base_url}/api/auth/logout", timeout=20))
            extra_operations, extra_operation_notes, _, _ = capture_safe_extra_routes(
                session,
                base_url,
                csrf,
                email,
                password,
                slots,
                args.proxy_server or None,
            )
        finally:
            server.should_exit = True
            server_thread.join(timeout=5)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "python": platform.python_version(),
        "transport": "real HTTP via requests",
        "proxy_server": args.proxy_server or None,
        "database": "temporary sqlite",
        "samples_per_measurement": args.samples,
        "setup": setup,
        "default_map_slot_count": len(slots),
        "default_map_slot_numbers": [slot["slot_number"] for slot in slots],
        "warmup_operations": warmup_operations,
        "measurements": measurements,
        "single_operations": {
            "map-slot import POST /api/map-slots/import": response_sample(import_duration, import_response),
            "map-slot reset POST /api/map-slots/{id}/reset": response_sample(reset_duration, reset_response),
            "map-slot activate POST /api/map-slots/{id}/activate": response_sample(activate_duration, activate_response),
        },
        "extra_operations": extra_operations,
        "extra_operation_notes": extra_operation_notes,
        "csrf_rejection": {
            "operation": "POST /api/auth/logout without X-CSRF-Token",
            **response_sample(csrf_duration, csrf_response),
        },
    }

    path = EVIDENCE / args.output_file
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote HTTP auth/map-slot performance evidence to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

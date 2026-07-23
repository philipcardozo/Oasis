#!/usr/bin/env python3
"""Run controlled Compose failure exercises and write acceptance evidence."""

from __future__ import annotations

import json
import os
import platform
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
BASE_URL = os.environ.get("OASIS_COMPOSE_URL", "https://localhost:8443").rstrip("/")
ENV_FILE = os.environ.get("OASIS_COMPOSE_ENV_FILE", ".env.staging.local")
DOCKER_PATH = "/Applications/Docker.app/Contents/Resources/bin:" + os.environ.get("PATH", "")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run(args: list[str], *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": DOCKER_PATH}
    proc = subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def compose(*args: str, check: bool = True, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return run(["docker", "compose", "--env-file", ENV_FILE, *args], check=check, timeout=timeout)


def request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.request(
            method,
            f"{BASE_URL}{path}",
            timeout=kwargs.pop("timeout", 12),
            verify=False,
            **kwargs,
        )
        return {
            "ok": True,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "body_sample": response.text[:300],
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc)[:300],
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def wait_for(path: str, expected: set[int], *, deadline_s: int = 90) -> dict[str, Any]:
    deadline = time.time() + deadline_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = request("GET", path, timeout=8)
        if last.get("status_code") in expected:
            return last
        time.sleep(1)
    return last | {"timed_out": True}


def psql(sql: str) -> str:
    proc = compose("exec", "-T", "db", "psql", "-U", "oasis", "-d", "oasis", "-At", "-F", "\t", "-c", sql)
    return proc.stdout.strip()


def job_snapshot(correlation_id: str) -> dict[str, Any]:
    row = psql(
        "select id,status,attempts,max_attempts,coalesce(error,''),"
        "coalesce(result::text,'{}'),coalesce(correlation_id,'') "
        f"from jobs where correlation_id = '{correlation_id}' order by created_at desc limit 1;"
    )
    if not row:
        return {"found": False}
    job_id, status, attempts, max_attempts, error, result, corr = row.split("\t", 6)
    return {
        "found": True,
        "id": job_id,
        "status": status,
        "attempts": int(attempts),
        "max_attempts": int(max_attempts),
        "error": error,
        "result": result,
        "correlation_id": corr,
    }


def insert_noop_job(correlation_id: str) -> str:
    sql = (
        "insert into jobs "
        "(id, kind, status, payload, result, attempts, max_attempts, correlation_id, created_at) "
        "values (substr(md5(random()::text || clock_timestamp()::text), 1, 32), "
        f"'noop', 'queued', '{{\"exercise\":\"worker_restart\"}}'::json, '{{}}'::json, "
        f"0, 3, '{correlation_id}', now()) returning id;"
    )
    return psql(sql)


def wait_job_done(correlation_id: str, *, deadline_s: int = 90) -> dict[str, Any]:
    deadline = time.time() + deadline_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = job_snapshot(correlation_id)
        if last.get("status") in {"done", "failed"}:
            return last
        time.sleep(2)
    return last | {"timed_out": True}


def seed_login_user() -> tuple[str, str]:
    email = f"failure-drill-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(24) + "Aa1!"
    seed_code = r"""
import os
from server import repositories as repo
from server.db import session_scope
from server.security import hash_password

email = os.environ["OASIS_FAILURE_EMAIL"]
password = os.environ["OASIS_FAILURE_PASSWORD"]
with session_scope() as db:
    user = repo.get_user_by_email(db, email)
    if user is None:
        user = repo.create_user(db, email, hash_password(password))
    else:
        user.password_hash = hash_password(password)
    user.status = "active"
    user.is_verified = True
    if len(repo.list_map_slots(db, user.id)) < 3:
        repo.create_default_map_slots(db, user.id)
"""
    compose(
        "exec",
        "-T",
        "-e",
        f"OASIS_FAILURE_EMAIL={email}",
        "-e",
        f"OASIS_FAILURE_PASSWORD={password}",
        "api",
        "python",
        "-c",
        seed_code,
    )
    return email, password


def login_and_slots(email: str, password: str) -> dict[str, Any]:
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
        verify=False,
    )
    out: dict[str, Any] = {
        "login_status": login.status_code,
        "secure_session_cookie": False,
        "secure_csrf_cookie": False,
    }
    for cookie in session.cookies:
        if cookie.name == "oasis_session":
            out["secure_session_cookie"] = bool(cookie.secure)
        if cookie.name == "oasis_csrf":
            out["secure_csrf_cookie"] = bool(cookie.secure)
    if login.status_code == 200:
        slots = session.get(f"{BASE_URL}/api/map-slots", timeout=20, verify=False)
        out["map_slots_status"] = slots.status_code
        out["map_slot_count"] = len(slots.json().get("slots", [])) if slots.ok else None
    return out


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    correlation_id = "failure-exercise-20260723"
    evidence: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "env_file": ENV_FILE,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "exercises": {},
    }

    login_email, login_password = seed_login_user()
    evidence["seed_user"] = {"email_domain": login_email.split("@", 1)[1]}

    evidence["preflight"] = {
        "ps": compose("ps", "--format", "json").stdout.strip().splitlines(),
        "healthz": wait_for("/healthz", {200}, deadline_s=60),
        "readyz": wait_for("/readyz", {200}, deadline_s=60),
    }

    compose("stop", "db")
    evidence["exercises"]["stop_postgres"] = {
        "healthz_while_db_stopped": wait_for("/healthz", {200}, deadline_s=30),
        "readyz_while_db_stopped": wait_for("/readyz", {503, 500, 502}, deadline_s=30),
    }
    compose("start", "db")
    evidence["exercises"]["recover_postgres"] = {
        "readyz_after_db_start": wait_for("/readyz", {200}, deadline_s=90),
    }

    compose("stop", "worker")
    job_id = insert_noop_job(correlation_id)
    evidence["exercises"]["stop_worker"] = {
        "app_healthz": request("GET", "/healthz"),
        "index_html": request("GET", "/index.html"),
        "queued_job_id": job_id,
        "queued_job": job_snapshot(correlation_id),
    }
    compose("start", "worker")
    evidence["exercises"]["recover_worker"] = {
        "job_after_worker_restart": wait_job_done(correlation_id),
        "api_healthz_while_worker_runs": request("GET", "/healthz"),
    }

    compose("restart", "api")
    evidence["exercises"]["restart_api"] = {
        "healthz_after_api_restart": wait_for("/healthz", {200}, deadline_s=90),
        "readyz_after_api_restart": wait_for("/readyz", {200}, deadline_s=90),
    }

    compose("restart")
    full_restart = {
        "healthz_after_compose_restart": wait_for("/healthz", {200}, deadline_s=120),
        "readyz_after_compose_restart": wait_for("/readyz", {200}, deadline_s=120),
    }
    if full_restart["readyz_after_compose_restart"].get("status_code") != 200:
        compose("down", "--remove-orphans")
        compose("up", "-d", timeout=240)
        full_restart["port_forward_recovery"] = "compose down/up preserving named volumes"
        full_restart["healthz_after_port_recovery"] = wait_for("/healthz", {200}, deadline_s=120)
        full_restart["readyz_after_port_recovery"] = wait_for("/readyz", {200}, deadline_s=120)
    evidence["exercises"]["restart_full_stack"] = full_restart

    evidence["persistence_after_restarts"] = login_and_slots(login_email, login_password)
    evidence["postflight"] = {
        "ps": compose("ps", "--format", "json").stdout.strip().splitlines(),
        "job_final": job_snapshot(correlation_id),
    }

    checks = [
        evidence["preflight"]["healthz"].get("status_code") == 200,
        evidence["preflight"]["readyz"].get("status_code") == 200,
        evidence["exercises"]["stop_postgres"]["healthz_while_db_stopped"].get("status_code") == 200,
        evidence["exercises"]["stop_postgres"]["readyz_while_db_stopped"].get("status_code") in {500, 502, 503},
        evidence["exercises"]["recover_postgres"]["readyz_after_db_start"].get("status_code") == 200,
        evidence["exercises"]["stop_worker"]["index_html"].get("status_code") == 200,
        evidence["exercises"]["stop_worker"]["queued_job"].get("status") == "queued",
        evidence["exercises"]["recover_worker"]["job_after_worker_restart"].get("status") == "done",
        evidence["exercises"]["restart_api"]["readyz_after_api_restart"].get("status_code") == 200,
        evidence["exercises"]["restart_full_stack"].get("readyz_after_compose_restart", {}).get("status_code") == 200
        or evidence["exercises"]["restart_full_stack"].get("readyz_after_port_recovery", {}).get("status_code") == 200,
        evidence["persistence_after_restarts"].get("login_status") == 200,
        evidence["persistence_after_restarts"].get("map_slot_count") == 3,
        evidence["postflight"]["job_final"].get("correlation_id") == correlation_id,
    ]
    evidence["verdict"] = "pass" if all(checks) else "fail"

    out = EVIDENCE / "23-compose-failure-exercises.json"
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": evidence["verdict"], "evidence": str(out)}, indent=2))
    return 0 if evidence["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

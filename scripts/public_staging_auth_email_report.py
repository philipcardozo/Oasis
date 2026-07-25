#!/usr/bin/env python3
"""Generate public-staging auth/email acceptance evidence."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PERF_EVIDENCE = ROOT / "docs" / "evidence" / "performance"
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text())


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def status(sample: dict[str, Any] | None) -> int | None:
    return sample.get("status_code") if isinstance(sample, dict) else None


def contains_complete_email(value: Any) -> bool:
    if isinstance(value, str):
        return bool(EMAIL_RE.search(value))
    if isinstance(value, dict):
        return any(contains_complete_email(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_complete_email(item) for item in value)
    return False


def secret_like_values(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            child = f"{path}.{key}" if path else str(key)
            if isinstance(item, str):
                allowed_env_pointer = lowered.endswith("_env") or lowered.endswith("_names_sent")
                if not allowed_env_pointer and any(marker in lowered for marker in ("password", "token", "cookie", "authorization", "secret")):
                    findings.append(child)
            findings.extend(secret_like_values(item, child))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            findings.extend(secret_like_values(item, f"{path}[{idx}]"))
    return findings


def evaluate(auth: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    rows: dict[str, Any] = {}

    if auth.get("verdict") != "pass":
        failures.append("auth/map-slot evidence verdict is not pass")
    if contains_complete_email(auth):
        failures.append("auth evidence contains a complete email address")
    secret_paths = secret_like_values(auth)
    if secret_paths:
        failures.append(f"auth evidence contains secret-like string values: {', '.join(secret_paths)}")

    users = auth.get("users") or {}
    for label in ("user_a", "user_b"):
        user = users.get(label) or {}
        rows[f"{label}_registration_status"] = status(user.get("register"))
        rows[f"{label}_verification_token_supplied"] = user.get("verification_token_supplied")
        rows[f"{label}_verification_status"] = status(user.get("verify_email"))
        rows[f"{label}_login_status"] = status(user.get("login"))
        if rows[f"{label}_registration_status"] not in {200, 201, 202}:
            failures.append(f"{label} registration did not return generic success")
        if rows[f"{label}_verification_token_supplied"] is not True:
            failures.append(f"{label} verification token was not supplied from delivered email")
        if rows[f"{label}_verification_status"] != 200:
            failures.append(f"{label} email verification did not return 200")
        if rows[f"{label}_login_status"] != 200:
            failures.append(f"{label} login did not return 200")

    checks = auth.get("checks") or {}
    reset = checks.get("password_reset") or {}
    rows.update({
        "password_reset_request_status": status(reset.get("request")),
        "password_reset_token_supplied": reset.get("reset_token_supplied"),
        "password_reset_complete_status": status(reset.get("complete")),
        "post_reset_login_status": status(reset.get("post_reset_login")),
        "session_cookie_secure": checks.get("session_cookie_secure"),
        "session_cookie_httponly": checks.get("session_cookie_httponly"),
        "csrf_cookie_secure": checks.get("csrf_cookie_secure"),
        "csrf_rejection_status": status(checks.get("csrf_rejection")),
    })
    if rows["password_reset_request_status"] != 200:
        failures.append("password reset request did not return 200")
    if rows["password_reset_token_supplied"] is not True:
        failures.append("password reset token was not supplied from delivered email")
    if rows["password_reset_complete_status"] != 200:
        failures.append("password reset completion did not return 200")
    if rows["post_reset_login_status"] != 200:
        failures.append("post-reset login did not return 200")
    if rows["session_cookie_secure"] is not True:
        failures.append("session cookie is not Secure")
    if rows["session_cookie_httponly"] is not True:
        failures.append("session cookie is not HttpOnly")
    if rows["csrf_cookie_secure"] is not True:
        failures.append("CSRF cookie is not Secure")
    if rows["csrf_rejection_status"] != 403:
        failures.append("CSRF rejection did not return 403")

    return failures, rows


def build_payload(auth: dict[str, Any], auth_path: str) -> dict[str, Any]:
    failures, rows = evaluate(auth)
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "inputs": {"auth_map_slots": display_path(auth_path)},
        "auth_captured_at": auth.get("captured_at"),
        "auth_base_url": auth.get("base_url"),
        "rows": rows,
        "failures": failures,
        "verdict": "pass" if not failures else "investigate",
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Authentication And Email Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Auth evidence captured: `{payload['auth_captured_at']}`",
        f"Base URL: `{payload['auth_base_url']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Checks",
        "",
        "| Check | Value |",
        "|---|---|",
    ]
    for key, value in payload["rows"].items():
        lines.append(f"| {key.replace('_', ' ')} | `{value}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report is derived from sanitized auth/map-slot evidence and contains no passwords, tokens, cookies, authorization values, or complete email addresses.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-map-slots", default=str(PERF_EVIDENCE / "27-public-auth-map-slots.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "06-auth-email.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "auth-email-summary.json"))
    args = parser.parse_args()

    auth = load_json(Path(args.auth_map_slots))
    payload = build_payload(auth, args.auth_map_slots)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging auth/email report to {output}")
    print(f"Wrote public staging auth/email summary to {summary_output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

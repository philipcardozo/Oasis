#!/usr/bin/env python3
"""Build public-staging transactional-email delivery evidence.

Auth probes prove endpoint behavior. This report proves the public-staging
email delivery surface around that behavior: sender-domain configuration,
non-production identity, single-use/expiry/redaction, enumeration resistance,
and bounded retry evidence for delivery failures.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
PLACEHOLDER_MARKERS = ("<", ">", "replace-", "record exact", "required when")
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")
EMAIL_PLACEHOLDER_VALUES = {"staging sender domain", "transactional email sandbox"}

PROVIDER_CHECKS = {
    "transactional_service_configured": "transactional email service is configured",
    "smtp_backend_in_secure_mode": "SMTP backend is used in secure staging mode",
    "staging_or_sandbox_mode": "email service is in staging/sandbox mode",
    "non_production_sender_identity": "sender identity is non-production",
    "sender_domain_verified": "sender domain is verified",
    "spf_configured": "SPF is configured",
    "dkim_configured": "DKIM is configured",
    "dmarc_configured": "DMARC is configured",
    "absolute_links_staging_hostname": "email links use the public staging hostname",
    "no_production_sender_identity": "production sender identity is not used",
}

DELIVERY_CHECKS = {
    "registration_verification_delivered": "registration verification email was delivered",
    "password_reset_delivered": "password reset email was delivered",
    "security_notices_supported_or_not_applicable": "security notices are supported or not applicable",
    "provider_message_ids_recorded": "provider message IDs are recorded without secrets",
    "public_hostname_in_email_links": "delivered email links use the public hostname",
    "no_token_values_in_evidence": "evidence includes no token values",
}

TOKEN_CHECKS = {
    "verification_tokens_single_use": "verification tokens are single-use",
    "reset_tokens_single_use": "password reset tokens are single-use",
    "verification_token_expiry_configured": "verification token expiry is configured",
    "reset_token_expiry_configured": "password reset token expiry is configured",
    "tokens_not_logged": "tokens do not appear in logs",
    "user_enumeration_prevented": "password reset remains enumeration-resistant",
}

FAILURE_CHECKS = {
    "smtp_failure_probe_recorded": "SMTP/provider failure was probed",
    "delivery_failure_retried_through_worker": "delivery failure is retried through worker or job system",
    "retry_bounded": "email retry behavior is bounded",
    "dead_letter_or_terminal_failure_recorded": "terminal email failure is recorded",
    "request_remains_enumeration_resistant": "failure response remains enumeration-resistant",
    "tokens_not_exposed_on_failure": "email failure exposes no tokens",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def bool_row(key: str, label: str, value: bool, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "value": bool(value), **extra}


def public_base_url_failures(url: str) -> list[str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("email base URL is not HTTPS")
    if not host or host in LOCAL_PUBLIC_HOSTS or host.endswith(".local"):
        failures.append("email base URL is not a non-local public hostname")
    if host in RESERVED_PUBLIC_HOSTS or host.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("email base URL is a reserved documentation hostname")
    return failures


def has_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in EMAIL_PLACEHOLDER_VALUES or any(marker in text for marker in PLACEHOLDER_MARKERS)


def check_rows(data: dict[str, Any], section: str, required: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    checks = data.get(section) or {}
    rows = [bool_row(key, label, checks.get(key) is True) for key, label in required.items()]
    failures = [f"email {section} check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def auth_email_pass(auth: dict[str, Any] | None) -> bool:
    if not auth or auth.get("verdict") != "pass" or auth.get("failures"):
        return False
    rows = auth.get("rows") or {}
    required = {
        "user_a_verification_status": 200,
        "user_a_verification_reuse_status": 400,
        "password_reset_request_status": 200,
        "password_reset_unknown_request_status": 200,
        "password_reset_unknown_shape_matches": True,
        "password_reset_complete_status": 200,
        "password_reset_token_reuse_status": 400,
    }
    return all(rows.get(key) == expected for key, expected in required.items())


def infra_email_pass(infra: dict[str, Any] | None) -> bool:
    if not infra or not infra.get("input_captured_at"):
        return False
    result = ((infra.get("results") or {}).get("render_services") or {})
    if result.get("verdict") != "pass" or result.get("failures"):
        return False
    rows = {row.get("label"): row.get("value") for row in result.get("rows") or []}
    return rows.get("SMTP email settings are configured") is True and rows.get("evidence contains only secret names/status, not values") is True


def ops_email_pass(ops: dict[str, Any] | None) -> bool:
    if not ops or not ops.get("input_captured_at"):
        return False
    worker = ((ops.get("results") or {}).get("worker_jobs") or {})
    rows = {row.get("key"): row.get("value") for row in worker.get("rows") or []}
    return (
        worker.get("verdict") == "pass"
        and rows.get("failure_retry") is True
        and rows.get("timeout_bounded") is True
        and rows.get("correlation_id") is True
    )


def cross_check_rows(auth: dict[str, Any] | None, infra: dict[str, Any] | None, ops: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    rows = [
        bool_row("auth_email_summary_pass", "auth/email summary proves delivery flows and token safety", auth_email_pass(auth)),
        bool_row("infra_email_summary_pass", "infra summary proves SMTP configuration without secret values", infra_email_pass(infra)),
        bool_row("ops_worker_retry_summary_pass", "ops summary proves bounded worker retry evidence", ops_email_pass(ops)),
    ]
    failures = [f"email cross-check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def build_payload(
    data: dict[str, Any],
    auth: dict[str, Any] | None,
    infra: dict[str, Any] | None,
    ops: dict[str, Any] | None,
    *,
    input_path: str,
    auth_path: str,
    infra_path: str,
    ops_path: str,
) -> dict[str, Any]:
    failures: list[str] = []
    provider, provider_failures = check_rows(data, "provider_configuration", PROVIDER_CHECKS)
    delivery, delivery_failures = check_rows(data, "delivery_flows", DELIVERY_CHECKS)
    tokens, token_failures = check_rows(data, "token_safety", TOKEN_CHECKS)
    failure_handling, failure_failures = check_rows(data, "failure_handling", FAILURE_CHECKS)
    cross_checks, cross_failures = cross_check_rows(auth, infra, ops)
    failures.extend(provider_failures + delivery_failures + token_failures + failure_failures + cross_failures)

    if not data.get("input_captured_at"):
        failures.append("email input captured timestamp is missing")
    failures.extend(public_base_url_failures(str(data.get("base_url") or "")))
    if not str(data.get("provider") or ""):
        failures.append("email provider is missing")
    elif has_placeholder(data.get("provider")):
        failures.append("email provider is still a placeholder")
    if has_placeholder(data.get("sender_domain_alias")):
        failures.append("email sender domain alias is still a placeholder")
    if data.get("secret_free_evidence") is not True:
        failures.append("email evidence is not marked secret-free")

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": data.get("input_captured_at"),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": data.get("base_url"),
        "provider": data.get("provider"),
        "sender_domain_alias": data.get("sender_domain_alias"),
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "inputs": {
            "email_delivery_evidence": display_path(input_path),
            "auth_email_summary": display_path(auth_path),
            "infra_summary": display_path(infra_path),
            "ops_summary": display_path(ops_path),
        },
        "provider_configuration": {"rows": provider},
        "delivery_flows": {"rows": delivery},
        "token_safety": {"rows": tokens},
        "failure_handling": {"rows": failure_handling},
        "cross_checks": {"rows": cross_checks},
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Email Delivery Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Provider: `{payload['provider']}`",
        f"Sender domain alias: `{payload['sender_domain_alias']}`",
        f"Verdict: **{payload['verdict']}**",
    ]
    for title, section in (
        ("Provider Configuration", "provider_configuration"),
        ("Delivery Flows", "delivery_flows"),
        ("Token Safety", "token_safety"),
        ("Failure Handling", "failure_handling"),
        ("Cross Checks", "cross_checks"),
    ):
        lines.extend(["", f"## {title}", "", "| Check | Result |", "|---|---|"])
        for row in payload[section]["rows"]:
            lines.append(f"| {row['label']} | `{row['value']}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report contains sanitized email-delivery evidence only.")
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": "https://staging.example.com",
        "provider": "transactional email sandbox",
        "sender_domain_alias": "staging sender domain",
        "secret_free_evidence": True,
        "provider_configuration": {key: True for key in PROVIDER_CHECKS},
        "delivery_flows": {key: True for key in DELIVERY_CHECKS},
        "token_safety": {key: True for key in TOKEN_CHECKS},
        "failure_handling": {key: True for key in FAILURE_CHECKS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret email-delivery evidence template and exit")
    parser.add_argument("--input", default=str(PUBLIC_EVIDENCE / "email-delivery-evidence.json"))
    parser.add_argument("--auth-email-summary", default=str(PUBLIC_EVIDENCE / "auth-email-summary.json"))
    parser.add_argument("--infra-summary", default=str(PUBLIC_EVIDENCE / "infra-evidence-summary.json"))
    parser.add_argument("--ops-summary", default=str(PUBLIC_EVIDENCE / "ops-evidence-summary.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "20-email-delivery.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "email-delivery-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    data = load_json(Path(args.input))
    if data is None:
        raise SystemExit(f"missing input: {args.input}")
    payload = build_payload(
        data,
        load_json(Path(args.auth_email_summary)),
        load_json(Path(args.infra_summary)),
        load_json(Path(args.ops_summary)),
        input_path=args.input,
        auth_path=args.auth_email_summary,
        infra_path=args.infra_summary,
        ops_path=args.ops_summary,
    )
    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging email-delivery report to {output}")
    print(f"Wrote public staging email-delivery summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

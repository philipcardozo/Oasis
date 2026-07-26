#!/usr/bin/env python3
"""Build public-staging rate-limit evidence.

Public staging can temporarily use the in-process limiter only for a controlled
single API replica. This report makes that limitation explicit and requires
edge controls plus route-family probes before the private-beta gate can pass.
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

ROUTE_FAMILIES = {
    "login_attempts": "login attempts",
    "registration": "registration",
    "password_reset": "password reset",
    "search": "search",
    "financial_models": "financial models",
    "exports": "exports",
    "map_slot_writes": "map-slot writes",
    "administrative_operations": "administrative operations",
}

EDGE_CHECKS = {
    "edge_controls_enabled": "edge-level abuse controls are enabled",
    "waf_or_rate_rules_enabled": "WAF or rate rules are enabled",
    "outer_access_enforced": "outer access boundary is enforced before OASIS",
    "provider_logs_reviewed": "edge/provider rate-limit logs were reviewed",
    "no_hidden_url_dependency": "hidden URL is not the access control",
}

CLIENT_IP_CHECKS = {
    "trusted_proxy_enabled": "OASIS trust-proxy setting matches the edge design",
    "x_forwarded_for_honored_only_from_edge": "X-Forwarded-For is trusted only from the approved edge",
    "client_ip_probe_recorded": "client-IP probe was recorded",
    "spoofed_forwarded_for_rejected_or_ignored": "spoofed forwarded-for header is rejected or ignored",
    "rate_limit_key_uses_client_ip": "rate-limit key uses the effective client IP",
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


def route_security_pass(route_security: dict[str, Any] | None) -> bool:
    if not route_security:
        return False
    if route_security.get("verdict") != "pass":
        return False
    class_summary = (route_security.get("inventory") or {}).get("class_summary") or {}
    return class_summary.get("public-write-auth-flow-rate-limited") == 5


def preflight_https(preflight: dict[str, Any] | None) -> bool:
    if not preflight:
        return False
    return preflight.get("verdict") == "pass" and (preflight.get("url") or {}).get("scheme") == "https"


def bool_row(key: str, label: str, value: bool, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "value": bool(value), **extra}


def route_family_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows = []
    failures = []
    families = data.get("route_families") or {}
    for key, label in ROUTE_FAMILIES.items():
        item = families.get(key) or {}
        statuses = set(item.get("limit_exceeded_statuses") or [])
        allowed_status = bool(statuses and statuses.issubset({401, 403, 429}))
        value = (
            item.get("tested") is True
            and item.get("configured") is True
            and allowed_status
            and int(item.get("sample_count") or 0) > 0
            and item.get("secret_free_evidence") is True
        )
        if item.get("app_429_expected") is True:
            value = value and 429 in statuses and item.get("retry_after_present") is True
        row = bool_row(
            key,
            label,
            value,
            configured=item.get("configured"),
            tested=item.get("tested"),
            sample_count=item.get("sample_count"),
            statuses=sorted(statuses),
            limit_source=item.get("limit_source"),
        )
        rows.append(row)
        if not value:
            failures.append(f"route family rate-limit evidence is not proven: {key}")
    return rows, failures


def edge_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    edge = data.get("edge_controls") or {}
    rows = [bool_row(key, label, edge.get(key) is True) for key, label in EDGE_CHECKS.items()]
    if "cloudflare" not in str(edge.get("provider") or "").lower():
        rows.append(bool_row("provider_cloudflare", "edge provider is Cloudflare", False, provider=edge.get("provider")))
    else:
        rows.append(bool_row("provider_cloudflare", "edge provider is Cloudflare", True, provider=edge.get("provider")))
    failures = [f"edge rate-limit check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def client_ip_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    client_ip = data.get("client_ip") or {}
    rows = [bool_row(key, label, client_ip.get(key) is True) for key, label in CLIENT_IP_CHECKS.items()]
    failures = [f"client IP check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def deployment_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    shape = data.get("deployment_shape") or {}
    replicas = int(shape.get("api_replicas") or 0)
    shared_store = shape.get("shared_rate_limit_store") is True
    per_process_documented = shape.get("per_process_limiter_documented") is True
    single_replica_ok = replicas == 1 and per_process_documented
    multi_replica_ok = replicas > 1 and shared_store
    rows = [
        bool_row("api_replica_count_recorded", "API replica count is recorded", replicas > 0, api_replicas=replicas),
        bool_row("single_replica_policy_ok", "single-replica temporary limiter policy is documented", replicas != 1 or single_replica_ok),
        bool_row("multi_replica_shared_store", "multiple replicas use a shared rate-limit store", replicas <= 1 or multi_replica_ok),
        bool_row("no_unbounded_public_replica", "public staging is not using an unbounded limiter shape", single_replica_ok or multi_replica_ok),
    ]
    failures = [f"deployment rate-limit shape check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def build_payload(data: dict[str, Any], route_security: dict[str, Any] | None, preflight: dict[str, Any] | None, *, input_path: str, route_security_path: str, preflight_path: str) -> dict[str, Any]:
    failures: list[str] = []
    deployment, deployment_failures = deployment_rows(data)
    edge, edge_failures = edge_rows(data)
    client_ip, client_failures = client_ip_rows(data)
    families, family_failures = route_family_rows(data)
    failures.extend(deployment_failures + edge_failures + client_failures + family_failures)

    cross_checks = [
        bool_row("route_security_summary_pass", "route-security summary has pass verdict and rate-limited auth class", route_security_pass(route_security)),
        bool_row("preflight_https_pass", "public preflight is HTTPS and pass", preflight_https(preflight)),
    ]
    failures.extend(f"rate-limit cross-check is not true: {row['key']}" for row in cross_checks if row["value"] is not True)

    if not data.get("input_captured_at"):
        failures.append("rate-limit input captured timestamp is missing")
    base_url = str(data.get("base_url") or "")
    if urlparse(base_url).scheme != "https":
        failures.append("rate-limit base URL is not HTTPS")

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": data.get("input_captured_at"),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": base_url,
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "inputs": {
            "rate_limit_evidence": display_path(input_path),
            "route_security_summary": display_path(route_security_path),
            "preflight": display_path(preflight_path),
        },
        "deployment_shape": {"rows": deployment},
        "edge_controls": {"rows": edge},
        "client_ip": {"rows": client_ip},
        "route_families": {"rows": families},
        "cross_checks": {"rows": cross_checks},
    }
    return payload


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Rate Limiting Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Verdict: **{payload['verdict']}**",
    ]
    for title, section in (
        ("Deployment Shape", "deployment_shape"),
        ("Edge Controls", "edge_controls"),
        ("Client IP Handling", "client_ip"),
        ("Route Families", "route_families"),
        ("Cross Checks", "cross_checks"),
    ):
        lines.extend(["", f"## {title}", "", "| Check | Result |", "|---|---|"])
        for row in payload[section]["rows"]:
            lines.append(f"| {row['label']} | `{row['value']}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report contains sanitized rate-limit evidence only.")
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    family = {
        "configured": True,
        "tested": True,
        "sample_count": 12,
        "limit_source": "app+edge",
        "limit_exceeded_statuses": [429],
        "retry_after_present": True,
        "app_429_expected": True,
        "secret_free_evidence": True,
    }
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": "https://staging.example.com",
        "deployment_shape": {
            "api_replicas": 1,
            "shared_rate_limit_store": False,
            "per_process_limiter_documented": True,
        },
        "edge_controls": {
            "provider": "Cloudflare",
            "edge_controls_enabled": True,
            "waf_or_rate_rules_enabled": True,
            "outer_access_enforced": True,
            "provider_logs_reviewed": True,
            "no_hidden_url_dependency": True,
        },
        "client_ip": {
            "trusted_proxy_enabled": True,
            "x_forwarded_for_honored_only_from_edge": True,
            "client_ip_probe_recorded": True,
            "spoofed_forwarded_for_rejected_or_ignored": True,
            "rate_limit_key_uses_client_ip": True,
        },
        "route_families": {key: dict(family) for key in ROUTE_FAMILIES},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret rate-limit evidence template and exit")
    parser.add_argument("--input", default=str(PUBLIC_EVIDENCE / "rate-limit-evidence.json"))
    parser.add_argument("--route-security", default=str(PUBLIC_EVIDENCE / "route-security-summary.json"))
    parser.add_argument("--preflight", default=str(PUBLIC_EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "18-rate-limiting.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "rate-limit-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    data = load_json(Path(args.input))
    if data is None:
        raise SystemExit(f"missing input: {args.input}")
    payload = build_payload(
        data,
        load_json(Path(args.route_security)),
        load_json(Path(args.preflight)),
        input_path=args.input,
        route_security_path=args.route_security,
        preflight_path=args.preflight,
    )
    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging rate-limit report to {output}")
    print(f"Wrote public staging rate-limit summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

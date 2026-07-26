#!/usr/bin/env python3
"""Build public-staging controlled failure-exercise evidence.

This report covers the Phase 1.75 failure exercises as a single strict gate.
It accepts only sanitized structured evidence and cross-checks the operation,
browser/map, object-storage, and email-delivery summaries that prove adjacent
behavior.
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

DATABASE_CHECKS = {
    "readiness_fails": "readiness fails during database interruption",
    "liveness_truthful": "liveness remains truthful during database interruption",
    "api_recovers_after_restore": "API recovers after database restoration",
    "no_data_corruption": "no data corruption occurs",
    "no_sqlite_fallback": "staging never falls back to SQLite",
}

WORKER_CHECKS = {
    "browsing_continues": "browsing continues while worker is interrupted",
    "jobs_remain_pending": "jobs remain pending while worker is interrupted",
    "work_resumes_safely": "work resumes safely after worker restoration",
    "api_responsive_while_worker_down": "API remains responsive while worker is down",
    "no_duplicate_completion": "no duplicate job completion occurs",
}

API_REPLACEMENT_CHECKS = {
    "traffic_healthy_instances_only": "traffic returns to healthy API instances only",
    "sessions_persist": "sessions persist through API replacement",
    "map_slots_persist": "map slots persist through API replacement",
    "no_migration_race": "no migration race occurs",
    "replacement_revision_recorded": "replacement revision is recorded",
}

FAILED_DEPLOYMENT_CHECKS = {
    "failing_health_revision_used_or_simulated": "failing health-check revision was used or safely simulated",
    "traffic_not_shifted": "traffic is not shifted to the failed revision",
    "previous_revision_available": "previous revision remains available",
    "rollback_command_recorded": "rollback command or provider action is recorded",
    "rollback_verified": "rollback works after the failed deploy",
}

MAP_OUTAGE_CHECKS = {
    "application_usable": "application remains usable during map-provider outage",
    "preferred_basemap_preserved": "preferred basemap remains saved",
    "fallback_works": "fallback map behavior works",
    "retry_bounded": "map retry behavior is bounded",
    "no_unlicensed_provider_enabled": "unlicensed providers remain disabled",
}

OBJECT_STORAGE_FAILURE_CHECKS = {
    "export_status_accurate": "export status is accurate during object-storage failure",
    "partial_output_not_offered": "partial output is not offered",
    "retry_bounded": "object-storage retry behavior is bounded",
    "no_secret_leak": "object-storage failure exposes no secrets",
}

EMAIL_FAILURE_CHECKS = {
    "request_enumeration_resistant": "email failure response remains enumeration-resistant",
    "delivery_retried": "email delivery is retried",
    "retry_bounded": "email retry behavior is bounded",
    "tokens_not_exposed": "email failure exposes no tokens",
}

CROSS_CHECKS = {
    "ops_worker_summary_pass": "ops summary proves worker interruption/recovery behavior",
    "ops_backup_summary_pass": "ops summary proves persistent database restore behavior",
    "ops_rollback_summary_pass": "ops summary proves API replacement and failed-deploy rollback behavior",
    "ops_alerts_summary_pass": "ops summary proves readiness, worker, storage, and latency alerts",
    "browser_map_failure_pass": "browser/map summary proves map-provider failure behavior",
    "storage_failure_pass": "object-storage summary proves storage failure behavior",
    "email_failure_pass": "email-delivery summary proves email failure behavior",
}

SECTIONS = {
    "database_interruption": DATABASE_CHECKS,
    "worker_interruption": WORKER_CHECKS,
    "api_replacement": API_REPLACEMENT_CHECKS,
    "failed_deployment": FAILED_DEPLOYMENT_CHECKS,
    "map_provider_outage": MAP_OUTAGE_CHECKS,
    "object_storage_failure": OBJECT_STORAGE_FAILURE_CHECKS,
    "email_failure": EMAIL_FAILURE_CHECKS,
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


def section_rows(data: dict[str, Any], section: str, required: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    checks = data.get(section) or {}
    rows = [bool_row(key, label, checks.get(key) is True) for key, label in required.items()]
    failures = [f"failure exercise {section} check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def rows_by_key(summary: dict[str, Any] | None, section: str, *, nested_results: bool = False) -> dict[str, Any]:
    if not summary:
        return {}
    source = ((summary.get("results") or {}).get(section) or {}) if nested_results else (summary.get(section) or {})
    return {row.get("key"): row.get("value") for row in source.get("rows") or []}


def ops_result_pass(ops: dict[str, Any] | None, section: str) -> bool:
    if not ops or not ops.get("input_captured_at"):
        return False
    result = (ops.get("results") or {}).get(section) or {}
    return result.get("verdict") == "pass" and not result.get("failures") and not result.get("warnings")


def ops_worker_pass(ops: dict[str, Any] | None) -> bool:
    rows = rows_by_key(ops, "worker_jobs", nested_results=True)
    return (
        ops_result_pass(ops, "worker_jobs")
        and rows.get("worker_restart_recovery") is True
        and rows.get("api_responsive_while_worker_runs") is True
        and rows.get("no_duplicate_completion") is True
    )


def ops_backup_pass(ops: dict[str, Any] | None) -> bool:
    rows = rows_by_key(ops, "backup_restore", nested_results=True)
    return (
        ops_result_pass(ops, "backup_restore")
        and rows.get("restore_separate_database") is True
        and rows.get("migration_validation") is True
        and rows.get("auth_verified") is True
        and rows.get("map_slots_verified") is True
        and rows.get("authorization_verified") is True
    )


def ops_rollback_pass(ops: dict[str, Any] | None) -> bool:
    rows = rows_by_key(ops, "failure_rollback", nested_results=True)
    return (
        ops_result_pass(ops, "failure_rollback")
        and rows.get("failed_health_no_traffic_shift") is True
        and rows.get("previous_revision_available") is True
        and rows.get("login_session_persistence") is True
        and rows.get("map_slots_persisted") is True
        and rows.get("migration_race_absent") is True
        and rows.get("rollback_command_recorded") is True
    )


def ops_alerts_pass(ops: dict[str, Any] | None) -> bool:
    rows = rows_by_key(ops, "observability_alerts", nested_results=True)
    return (
        ops_result_pass(ops, "observability_alerts")
        and rows.get("alert.api_readiness_failure") is True
        and rows.get("alert.worker_failure") is True
        and rows.get("alert.storage_quota_pressure") is True
        and rows.get("alert.high_response_latency") is True
    )


def browser_map_failure_pass(browser_map: dict[str, Any] | None) -> bool:
    if not browser_map:
        return False
    target = browser_map.get("target") or {}
    base_url = str(target.get("matrix_base_url") or target.get("summary_base_url") or "")
    provider = browser_map.get("map_provider") or {}
    rows = rows_by_key(browser_map, "map_provider")
    return (
        urlparse(base_url).scheme == "https"
        and provider.get("verdict") == "pass"
        and not provider.get("failures")
        and rows.get("preferred_basemap_preserved_after_failure") is True
        and rows.get("standard_available") is True
        and rows.get("disabled_providers_unused") is True
    )


def storage_failure_pass(storage: dict[str, Any] | None) -> bool:
    rows = rows_by_key(storage, "failure_behavior")
    return (
        bool(storage)
        and storage.get("verdict") == "pass"
        and not storage.get("failures")
        and rows.get("storage_unavailable_probe_recorded") is True
        and rows.get("export_status_accurate") is True
        and rows.get("partial_output_not_offered") is True
        and rows.get("retry_bounded") is True
        and rows.get("no_secret_leak_in_errors") is True
    )


def email_failure_pass(email: dict[str, Any] | None) -> bool:
    rows = rows_by_key(email, "failure_handling")
    return (
        bool(email)
        and email.get("verdict") == "pass"
        and not email.get("failures")
        and rows.get("smtp_failure_probe_recorded") is True
        and rows.get("delivery_failure_retried_through_worker") is True
        and rows.get("retry_bounded") is True
        and rows.get("request_remains_enumeration_resistant") is True
        and rows.get("tokens_not_exposed_on_failure") is True
    )


def cross_check_rows(
    ops: dict[str, Any] | None,
    browser_map: dict[str, Any] | None,
    storage: dict[str, Any] | None,
    email: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    values = {
        "ops_worker_summary_pass": ops_worker_pass(ops),
        "ops_backup_summary_pass": ops_backup_pass(ops),
        "ops_rollback_summary_pass": ops_rollback_pass(ops),
        "ops_alerts_summary_pass": ops_alerts_pass(ops),
        "browser_map_failure_pass": browser_map_failure_pass(browser_map),
        "storage_failure_pass": storage_failure_pass(storage),
        "email_failure_pass": email_failure_pass(email),
    }
    rows = [bool_row(key, label, values[key]) for key, label in CROSS_CHECKS.items()]
    failures = [f"failure exercise cross-check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def build_payload(
    data: dict[str, Any],
    ops: dict[str, Any] | None,
    browser_map: dict[str, Any] | None,
    storage: dict[str, Any] | None,
    email: dict[str, Any] | None,
    *,
    input_path: str,
    ops_path: str,
    browser_map_path: str,
    storage_path: str,
    email_path: str,
) -> dict[str, Any]:
    failures: list[str] = []
    payload_sections: dict[str, dict[str, Any]] = {}
    for section, required in SECTIONS.items():
        rows, section_failures = section_rows(data, section, required)
        payload_sections[section] = {"rows": rows}
        failures.extend(section_failures)
    cross_checks, cross_failures = cross_check_rows(ops, browser_map, storage, email)
    failures.extend(cross_failures)

    if not data.get("input_captured_at"):
        failures.append("failure exercise input captured timestamp is missing")
    if urlparse(str(data.get("base_url") or "")).scheme != "https":
        failures.append("failure exercise base URL is not HTTPS")
    if data.get("secret_free_evidence") is not True:
        failures.append("failure exercise evidence is not marked secret-free")

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": data.get("input_captured_at"),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": data.get("base_url"),
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "inputs": {
            "failure_exercises_evidence": display_path(input_path),
            "ops_summary": display_path(ops_path),
            "browser_map_summary": display_path(browser_map_path),
            "storage_summary": display_path(storage_path),
            "email_delivery_summary": display_path(email_path),
        },
        **payload_sections,
        "cross_checks": {"rows": cross_checks},
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Failure Exercise Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Verdict: **{payload['verdict']}**",
    ]
    for title, section in (
        ("Database Interruption", "database_interruption"),
        ("Worker Interruption", "worker_interruption"),
        ("API Replacement", "api_replacement"),
        ("Failed Deployment", "failed_deployment"),
        ("Map Provider Outage", "map_provider_outage"),
        ("Object Storage Failure", "object_storage_failure"),
        ("Email Failure", "email_failure"),
        ("Cross Checks", "cross_checks"),
    ):
        lines.extend(["", f"## {title}", "", "| Check | Result |", "|---|---|"])
        for row in payload[section]["rows"]:
            lines.append(f"| {row['label']} | `{row['value']}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report contains sanitized failure-exercise evidence only.")
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": "https://staging.example.com",
        "secret_free_evidence": True,
        **{section: {key: True for key in required} for section, required in SECTIONS.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret failure-exercises evidence template and exit")
    parser.add_argument("--input", default=str(PUBLIC_EVIDENCE / "failure-exercises-evidence.json"))
    parser.add_argument("--ops-summary", default=str(PUBLIC_EVIDENCE / "ops-evidence-summary.json"))
    parser.add_argument("--browser-map-summary", default=str(PUBLIC_EVIDENCE / "browser-map-summary.json"))
    parser.add_argument("--storage-summary", default=str(PUBLIC_EVIDENCE / "storage-summary.json"))
    parser.add_argument("--email-delivery-summary", default=str(PUBLIC_EVIDENCE / "email-delivery-summary.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "21-failure-exercises.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "failure-exercises-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    data = load_json(Path(args.input))
    if data is None:
        raise SystemExit(f"missing input: {args.input}")
    payload = build_payload(
        data,
        load_json(Path(args.ops_summary)),
        load_json(Path(args.browser_map_summary)),
        load_json(Path(args.storage_summary)),
        load_json(Path(args.email_delivery_summary)),
        input_path=args.input,
        ops_path=args.ops_summary,
        browser_map_path=args.browser_map_summary,
        storage_path=args.storage_summary,
        email_path=args.email_delivery_summary,
    )
    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging failure-exercises report to {output}")
    print(f"Wrote public staging failure-exercises summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

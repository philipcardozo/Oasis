#!/usr/bin/env python3
"""Generate strict public-staging operations evidence reports.

Input is a structured, non-secret JSON file produced from provider dashboards,
public probes, temporary restore deployments, and operator notes. This script
does not prove public staging by itself; it prevents ad hoc Markdown from
claiming pass without the required structured evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"

REPORTS = {
    "worker_jobs": "10-worker-jobs.md",
    "network_isolation": "11-network-isolation.md",
    "backup_restore": "12-backup-restore.md",
    "failure_rollback": "13-failure-rollback.md",
    "observability_alerts": "14-observability-alerts.md",
}

WORKER_REQUIRED = {
    "job_created": "controlled noop job was created",
    "worker_claimed": "worker claimed the job",
    "job_completed": "job completed",
    "failure_retry": "failed job retried or reached bounded terminal failure",
    "timeout_bounded": "timeout behavior is bounded",
    "idempotency": "idempotency was verified",
    "correlation_id": "correlation ID was recorded",
    "api_responsive_while_worker_runs": "API remained responsive while worker ran",
    "worker_restart_recovery": "worker restart recovered pending work",
    "no_duplicate_completion": "no duplicate completion occurred",
    "external_acquisition_disabled": "external acquisition stayed disabled except explicit worker job",
}

NETWORK_REQUIRED = {
    "api_no_sec": "API made no SEC requests during normal user activity",
    "api_no_logo_services": "API made no logo-service requests during normal user activity",
    "api_no_yahoo": "API made no Yahoo/yfinance requests during normal user activity",
    "api_no_dataset_refresh": "API did not start dataset refresh operations",
    "browser_map_hosts_approved": "browser map hosts were approved",
    "worker_only_acquisition": "only the worker can perform approved acquisition",
    "secrets_not_observed": "secrets were not observed in outbound requests",
    "disabled_providers_unused": "disabled providers remained unused",
    "evidence_by_service_identity": "evidence is broken down by service identity",
}

BACKUP_REQUIRED = {
    "two_users": "two users exist in the drill dataset",
    "sessions": "sessions exist in the drill dataset",
    "three_slots_per_user": "each user has exactly three map slots",
    "customized_maps": "customized maps were included",
    "audit_events": "audit events were included",
    "job_records": "job records were included",
    "on_demand_backup": "on-demand backup was created",
    "checksum_recorded": "backup checksum was recorded",
    "backup_size_recorded": "backup size was recorded",
    "restore_separate_database": "restore used a separate database",
    "migration_validation": "migration validation succeeded after restore",
    "temporary_restore_deploy": "temporary OASIS restore deployment was used",
    "auth_verified": "authentication succeeded against restored database",
    "map_slots_verified": "map slots verified after restore",
    "authorization_verified": "authorization verified after restore",
    "job_metadata_verified": "job metadata verified after restore",
    "object_storage_private": "object storage remained private",
}

ROLLBACK_REQUIRED = {
    "api_rollback": "API rollback was exercised",
    "worker_rollback": "worker rollback was exercised",
    "same_previous_revision": "API and worker rolled back to the same previous revision",
    "healthz": "healthz passed after rollback",
    "readyz": "readyz passed after rollback",
    "version": "version matched expected rollback revision",
    "login_session_persistence": "login/session persistence survived rollback",
    "map_slots_persisted": "map slots persisted through rollback",
    "worker_job_recovery": "worker job recovery worked after rollback",
    "failed_health_no_traffic_shift": "failed-health deploy did not receive traffic",
    "previous_revision_available": "previous revision remained available",
    "migration_race_absent": "no migration race was observed",
    "rollback_command_recorded": "rollback command/equivalent provider action was recorded",
}

OBS_SIGNALS = {
    "request_count": "request count",
    "request_duration": "request duration",
    "status_codes": "status codes",
    "route_templates": "route templates",
    "auth_failures": "authentication failures",
    "rate_limit_events": "rate-limit events",
    "database_connections": "database connection usage",
    "database_query_latency": "database query latency",
    "worker_job_state": "worker job state",
    "export_failures": "export failures",
    "cache_hits_misses": "cache hit/miss behavior",
    "dataset_freshness": "dataset freshness",
    "storage_usage": "storage/disk usage",
    "deployment_revision": "deployment revision",
    "api_worker_health": "API and worker health",
}

OBS_ALERTS = {
    "api_readiness_failure": "API readiness failure",
    "elevated_5xx": "elevated 5xx rate",
    "auth_failure_spike": "authentication failure spike",
    "database_connection_exhaustion": "database connection exhaustion",
    "worker_queue_backlog": "worker queue backlog",
    "worker_failure": "worker failure",
    "backup_failure": "backup failure",
    "storage_quota_pressure": "storage quota pressure",
    "certificate_expiration": "certificate expiration",
    "high_response_latency": "high response latency",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text())


def check_bool(section: dict[str, Any], required: dict[str, str]) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    checks = section.get("checks") or {}
    for key, label in required.items():
        value = checks.get(key)
        rows.append({"key": key, "label": label, "value": value})
        if value is not True:
            failures.append(f"{key} is not true")
    return failures, rows


def false_checks(required: dict[str, str]) -> dict[str, bool]:
    return {key: False for key in required}


def evidence_template() -> dict[str, Any]:
    return {
        "captured_at": "replace-with-capture-time",
        "worker_jobs": {
            "captured_at": "replace-with-capture-time",
            "source": "Render worker logs and public API probes",
            "secrets_in_evidence": False,
            "checks": false_checks(WORKER_REQUIRED),
            "job": {
                "kind": "controlled-noop",
                "final_status": "replace-with-final-status",
                "correlation_id": "",
                "completion_count": 0,
            },
        },
        "network_isolation": {
            "captured_at": "replace-with-capture-time",
            "source": "provider egress logs grouped by service identity",
            "secrets_in_evidence": False,
            "checks": false_checks(NETWORK_REQUIRED),
            "counts": {
                "api_sec_requests": 0,
                "api_logo_requests": 0,
                "api_yahoo_requests": 0,
                "api_dataset_refreshes": 0,
            },
        },
        "backup_restore": {
            "captured_at": "replace-with-capture-time",
            "source": "managed Postgres backup and restore drill",
            "secrets_in_evidence": False,
            "checks": false_checks(BACKUP_REQUIRED),
            "backup": {
                "source_database": "oasis_staging",
                "restore_database": "replace-with-separate-restore-database-name",
                "sha256": "",
                "size_bytes": 0,
                "recovery_time_seconds": 0,
            },
        },
        "failure_rollback": {
            "captured_at": "replace-with-capture-time",
            "source": "Render deploy history and public probes",
            "secrets_in_evidence": False,
            "checks": false_checks(ROLLBACK_REQUIRED),
            "rollback": {
                "from_revision": "",
                "to_revision": "",
            },
        },
        "observability_alerts": {
            "captured_at": "replace-with-capture-time",
            "source": "provider logs, metrics, traces, and alert dashboard",
            "secrets_in_evidence": False,
            "signals": false_checks(OBS_SIGNALS),
            "alerts": false_checks(OBS_ALERTS),
            "redaction": {
                "passwords": False,
                "tokens": False,
                "cookies": False,
                "authorization_headers": False,
                "database_urls": False,
                "smtp_credentials": False,
                "storage_credentials": False,
            },
        },
    }


def evaluate_worker(section: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures, rows = check_bool(section, WORKER_REQUIRED)
    warnings: list[str] = []
    job = section.get("job") or {}
    if job.get("kind") not in {"noop", "controlled-noop"}:
        failures.append("worker job kind is not a controlled noop")
    if job.get("final_status") != "done":
        failures.append("worker job final_status is not done")
    if not job.get("correlation_id"):
        failures.append("worker job correlation_id is missing")
    if int(job.get("completion_count") or 0) != 1:
        failures.append("worker job completion_count is not exactly 1")
    return failures, warnings, rows


def evaluate_network(section: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures, rows = check_bool(section, NETWORK_REQUIRED)
    warnings: list[str] = []
    for name, count_key in (
        ("SEC", "api_sec_requests"),
        ("logo services", "api_logo_requests"),
        ("Yahoo/yfinance", "api_yahoo_requests"),
        ("API dataset refreshes", "api_dataset_refreshes"),
    ):
        count = int((section.get("counts") or {}).get(count_key) or 0)
        if count != 0:
            failures.append(f"{name} count is {count}, expected 0")
    return failures, warnings, rows


def evaluate_backup(section: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures, rows = check_bool(section, BACKUP_REQUIRED)
    warnings: list[str] = []
    backup = section.get("backup") or {}
    if int(backup.get("size_bytes") or 0) <= 0:
        failures.append("backup size_bytes is missing or zero")
    if not str(backup.get("sha256") or ""):
        failures.append("backup sha256 is missing")
    if str(backup.get("restore_database") or "") in {"", str(backup.get("source_database") or "")}:
        failures.append("restore database is missing or not separate")
    if float(backup.get("recovery_time_seconds") or 0) <= 0:
        failures.append("recovery time is missing or zero")
    return failures, warnings, rows


def evaluate_rollback(section: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures, rows = check_bool(section, ROLLBACK_REQUIRED)
    warnings: list[str] = []
    rollback = section.get("rollback") or {}
    if rollback.get("from_revision") == rollback.get("to_revision"):
        failures.append("rollback from_revision and to_revision are identical")
    if not rollback.get("to_revision"):
        failures.append("rollback target revision is missing")
    return failures, warnings, rows


def evaluate_observability(section: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    signal_failures, signal_rows = check_bool({"checks": section.get("signals") or {}}, OBS_SIGNALS)
    alert_failures, alert_rows = check_bool({"checks": section.get("alerts") or {}}, OBS_ALERTS)
    failures.extend(f"signal {item}" for item in signal_failures)
    failures.extend(f"alert {item}" for item in alert_failures)
    rows.extend({"key": f"signal.{row['key']}", "label": row["label"], "value": row["value"]} for row in signal_rows)
    rows.extend({"key": f"alert.{row['key']}", "label": row["label"], "value": row["value"]} for row in alert_rows)
    redaction = section.get("redaction") or {}
    for key in ("passwords", "tokens", "cookies", "authorization_headers", "database_urls", "smtp_credentials", "storage_credentials"):
        value = redaction.get(key)
        rows.append({"key": f"redaction.{key}", "label": f"{key.replace('_', ' ')} redacted", "value": value})
        if value is not True:
            failures.append(f"redaction {key} is not true")
    return failures, warnings, rows


EVALUATORS = {
    "worker_jobs": evaluate_worker,
    "network_isolation": evaluate_network,
    "backup_restore": evaluate_backup,
    "failure_rollback": evaluate_rollback,
    "observability_alerts": evaluate_observability,
}


def evaluate_section(kind: str, section: dict[str, Any] | None) -> dict[str, Any]:
    if not section:
        return {"kind": kind, "verdict": "investigate", "failures": [f"{kind} evidence section is missing"], "warnings": [], "rows": []}
    failures, warnings, rows = EVALUATORS[kind](section)
    if section.get("secrets_in_evidence") is True:
        failures.append("secrets_in_evidence is true")
    return {
        "kind": kind,
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "warnings": warnings,
        "rows": rows,
    }


def markdown(kind: str, section: dict[str, Any] | None, result: dict[str, Any], payload: dict[str, Any]) -> str:
    title = {
        "worker_jobs": "Public Staging Worker Job Evidence",
        "network_isolation": "Public Staging Network Isolation Evidence",
        "backup_restore": "Public Staging Backup Restore Evidence",
        "failure_rollback": "Public Staging Failure And Rollback Evidence",
        "observability_alerts": "Public Staging Observability And Alerts Evidence",
    }[kind]
    lines = [
        f"# {title}",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Source captured: `{(section or {}).get('captured_at', 'missing')}`",
        f"Evidence source: `{(section or {}).get('source', 'missing')}`",
        f"Verdict: **{result['verdict']}**",
        "",
        "## Checks",
        "",
        "| Check | Evidence value |",
        "|---|---|",
    ]
    for row in result["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")
    if result["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in result["failures"])
    if result["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in result["warnings"])
    lines.append("")
    lines.append("This generated report contains no secrets, cookies, credentials, private token URLs, or full authorization headers.")
    return "\n".join(lines) + "\n"


def build_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "input_captured_at": input_data.get("captured_at"),
        "results": {
            kind: evaluate_section(kind, input_data.get(kind))
            for kind in REPORTS
        },
    }


def write_reports(input_data: dict[str, Any], payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for kind, filename in REPORTS.items():
        section = input_data.get(kind)
        result = payload["results"][kind]
        (output_dir / filename).write_text(markdown(kind, section, result, payload))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret ops-evidence.json template and exit")
    parser.add_argument("--input", default=str(EVIDENCE / "ops-evidence.json"))
    parser.add_argument("--output-dir", default=str(EVIDENCE))
    parser.add_argument("--summary-output", default=str(EVIDENCE / "ops-evidence-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(evidence_template(), indent=2, sort_keys=True))
        return 0

    input_data = load_json(Path(args.input))
    payload = build_payload(input_data)
    output_dir = Path(args.output_dir)
    write_reports(input_data, payload, output_dir)
    summary = Path(args.summary_output)
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    failures = {
        kind: result["failures"]
        for kind, result in payload["results"].items()
        if result["verdict"] != "pass"
    }
    print(f"Wrote public staging ops reports to {output_dir}")
    print(json.dumps({"verdict": "pass" if not failures else "investigate", "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

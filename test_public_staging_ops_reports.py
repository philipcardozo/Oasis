"""Public-staging operations report regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_ops_reports import build_payload, evaluate_section


def test_ops_reports_pass_with_complete_structured_evidence():
    payload = build_payload(_evidence())

    assert {kind: result["verdict"] for kind, result in payload["results"].items()} == {
        "worker_jobs": "pass",
        "network_isolation": "pass",
        "backup_restore": "pass",
        "failure_rollback": "pass",
        "observability_alerts": "pass",
    }


def test_worker_report_rejects_missing_worker_recovery():
    section = _evidence()["worker_jobs"]
    section["checks"]["worker_restart_recovery"] = False

    result = evaluate_section("worker_jobs", section)

    assert result["verdict"] == "investigate"
    assert "worker_restart_recovery is not true" in result["failures"]


def test_network_report_rejects_api_acquisition_counts():
    section = _evidence()["network_isolation"]
    section["counts"]["api_sec_requests"] = 1

    result = evaluate_section("network_isolation", section)

    assert result["verdict"] == "investigate"
    assert "SEC count is 1, expected 0" in result["failures"]


def test_backup_report_rejects_primary_database_restore():
    section = _evidence()["backup_restore"]
    section["backup"]["restore_database"] = "oasis_staging"

    result = evaluate_section("backup_restore", section)

    assert result["verdict"] == "investigate"
    assert "restore database is missing or not separate" in result["failures"]


def test_ops_reports_reject_placeholder_structured_fields():
    worker = _evidence()["worker_jobs"]
    worker["job"]["final_status"] = "replace-with-final-status"
    assert "worker job final_status is still a placeholder" in evaluate_section("worker_jobs", worker)["failures"]

    backup = _evidence()["backup_restore"]
    backup["backup"]["restore_database"] = "replace-with-separate-restore-database-name"
    assert "restore database is still a placeholder" in evaluate_section("backup_restore", backup)["failures"]

    rollback = _evidence()["failure_rollback"]
    rollback["rollback"]["to_revision"] = "replace-with-rollback-target"
    assert "rollback revision is still a placeholder" in evaluate_section("failure_rollback", rollback)["failures"]


def test_rollback_report_requires_api_restart_persistence():
    section = _evidence()["failure_rollback"]
    section["checks"]["api_restart_session_persistence"] = False
    section["checks"]["api_restart_map_slots_persisted"] = False

    result = evaluate_section("failure_rollback", section)

    assert result["verdict"] == "investigate"
    assert "api_restart_session_persistence is not true" in result["failures"]
    assert "api_restart_map_slots_persisted is not true" in result["failures"]


def test_ops_report_cli_writes_markdown_verdicts(tmp_path):
    input_path = tmp_path / "ops-evidence.json"
    output_dir = tmp_path / "public-staging"
    input_path.write_text(json.dumps(_evidence()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_ops_reports.py",
            f"--input={input_path}",
            f"--output-dir={output_dir}",
            f"--summary-output={tmp_path / 'summary.json'}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verdict: **pass**" in (output_dir / "10-worker-jobs.md").read_text()
    assert "Verdict: **pass**" in (output_dir / "14-observability-alerts.md").read_text()


def test_ops_template_is_not_self_approving():
    result = subprocess.run(
        [sys.executable, "scripts/public_staging_ops_reports.py", "--print-template"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    template = json.loads(result.stdout)
    payload = build_payload(template)
    assert {kind: result["verdict"] for kind, result in payload["results"].items()} == {
        "worker_jobs": "investigate",
        "network_isolation": "investigate",
        "backup_restore": "investigate",
        "failure_rollback": "investigate",
        "observability_alerts": "investigate",
    }


def _evidence() -> dict:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "worker_jobs": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Render logs and public API probes",
            "secrets_in_evidence": False,
            "checks": {
                "job_created": True,
                "worker_claimed": True,
                "job_completed": True,
                "failure_retry": True,
                "timeout_bounded": True,
                "idempotency": True,
                "correlation_id": True,
                "api_responsive_while_worker_runs": True,
                "worker_restart_recovery": True,
                "no_duplicate_completion": True,
                "external_acquisition_disabled": True,
            },
            "job": {
                "kind": "noop",
                "final_status": "done",
                "correlation_id": "public-worker-20260725",
                "completion_count": 1,
            },
        },
        "network_isolation": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "provider egress logs grouped by service",
            "secrets_in_evidence": False,
            "checks": {
                "api_no_sec": True,
                "api_no_logo_services": True,
                "api_no_yahoo": True,
                "api_no_dataset_refresh": True,
                "browser_map_hosts_approved": True,
                "worker_only_acquisition": True,
                "secrets_not_observed": True,
                "disabled_providers_unused": True,
                "evidence_by_service_identity": True,
            },
            "counts": {
                "api_sec_requests": 0,
                "api_logo_requests": 0,
                "api_yahoo_requests": 0,
                "api_dataset_refreshes": 0,
            },
        },
        "backup_restore": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "managed Postgres backup restore drill",
            "secrets_in_evidence": False,
            "checks": {
                "two_users": True,
                "sessions": True,
                "three_slots_per_user": True,
                "customized_maps": True,
                "audit_events": True,
                "job_records": True,
                "on_demand_backup": True,
                "checksum_recorded": True,
                "backup_size_recorded": True,
                "restore_separate_database": True,
                "migration_validation": True,
                "temporary_restore_deploy": True,
                "auth_verified": True,
                "map_slots_verified": True,
                "authorization_verified": True,
                "job_metadata_verified": True,
                "object_storage_private": True,
            },
            "backup": {
                "source_database": "oasis_staging",
                "restore_database": "oasis_staging_restore",
                "sha256": "c" * 64,
                "size_bytes": 12345,
                "recovery_time_seconds": 42,
            },
        },
        "failure_rollback": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Render deploy history and public probes",
            "secrets_in_evidence": False,
            "checks": {
                "api_rollback": True,
                "worker_rollback": True,
                "same_previous_revision": True,
                "healthz": True,
                "readyz": True,
                "version": True,
                "login_session_persistence": True,
                "map_slots_persisted": True,
                "post_restart_readyz": True,
                "api_restart_session_persistence": True,
                "api_restart_map_slots_persisted": True,
                "worker_job_recovery": True,
                "failed_health_no_traffic_shift": True,
                "previous_revision_available": True,
                "migration_race_absent": True,
                "rollback_command_recorded": True,
            },
            "rollback": {
                "from_revision": "new",
                "to_revision": "previous",
            },
        },
        "observability_alerts": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Render logs, OpenTelemetry collector, alert dashboard",
            "secrets_in_evidence": False,
            "signals": {
                "request_count": True,
                "request_duration": True,
                "status_codes": True,
                "route_templates": True,
                "auth_failures": True,
                "rate_limit_events": True,
                "database_connections": True,
                "database_query_latency": True,
                "worker_job_state": True,
                "export_failures": True,
                "cache_hits_misses": True,
                "dataset_freshness": True,
                "storage_usage": True,
                "deployment_revision": True,
                "api_worker_health": True,
            },
            "alerts": {
                "api_readiness_failure": True,
                "elevated_5xx": True,
                "auth_failure_spike": True,
                "database_connection_exhaustion": True,
                "worker_queue_backlog": True,
                "worker_failure": True,
                "backup_failure": True,
                "storage_quota_pressure": True,
                "certificate_expiration": True,
                "high_response_latency": True,
            },
            "redaction": {
                "passwords": True,
                "tokens": True,
                "cookies": True,
                "authorization_headers": True,
                "database_urls": True,
                "smtp_credentials": True,
                "storage_credentials": True,
            },
        },
    }

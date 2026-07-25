"""Public-staging infrastructure report regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_infra_reports import build_payload, evaluate_cloudflare_access, evaluate_migration_version


DIGEST = "sha256:" + "a" * 64


def test_infra_reports_pass_with_complete_structured_evidence():
    payload = build_payload(_infra(), _preflight(), _render_deploy(), _image_manifest())

    assert {kind: result["verdict"] for kind, result in payload["results"].items()} == {
        "dns_tls_edge": "pass",
        "cloudflare_access": "pass",
        "render_services": "pass",
        "migration_version": "pass",
    }


def test_dns_tls_report_rejects_failed_preflight():
    preflight = _preflight()
    preflight["tls"]["ok"] = False
    preflight["verdict"] = "investigate"

    payload = build_payload(_infra(), preflight, _render_deploy(), _image_manifest())

    result = payload["results"]["dns_tls_edge"]
    assert result["verdict"] == "investigate"
    assert "TLS probe is not ok" in result["failures"]


def test_cloudflare_report_rejects_missing_outer_boundary():
    infra = _infra()
    section = infra["cloudflare_access"]
    section["checks"]["enabled"] = False

    result = evaluate_cloudflare_access(infra)

    assert result["verdict"] == "investigate"
    assert "enabled is not true" in result["failures"]


def test_migration_report_rejects_revision_mismatch():
    infra = _infra()
    infra["migration"]["current_revision"] = ["deadbeef"]

    result = evaluate_migration_version(infra, _render_deploy(), _image_manifest())

    assert result["verdict"] == "investigate"
    assert "current revision is ['deadbeef'], expected ['29995ef61d8e']" in result["failures"]


def test_infra_reports_reject_secret_like_values():
    infra = _infra()
    infra["cloudflare_access"]["service_token"] = "sk_12345678901234567890123456789012"

    payload = build_payload(infra, _preflight(), _render_deploy(), _image_manifest())

    assert all(result["verdict"] == "investigate" for result in payload["results"].values())
    assert any("secret-like values" in item for item in payload["results"]["cloudflare_access"]["failures"])


def test_infra_template_is_not_self_approving():
    result = subprocess.run(
        [sys.executable, "scripts/public_staging_infra_reports.py", "--print-template"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    template = json.loads(result.stdout)
    payload = build_payload(template, _preflight(), _render_deploy(), _image_manifest())
    assert payload["results"]["dns_tls_edge"]["verdict"] == "investigate"
    assert payload["results"]["cloudflare_access"]["verdict"] == "investigate"
    assert payload["results"]["render_services"]["verdict"] == "investigate"
    assert payload["results"]["migration_version"]["verdict"] == "investigate"


def test_infra_report_cli_writes_markdown_verdicts(tmp_path):
    infra = tmp_path / "infra-evidence.json"
    preflight = tmp_path / "00-public-staging-preflight.json"
    render_deploy = tmp_path / "02-render-deploy.json"
    image_manifest = tmp_path / "01-image-manifest.json"
    output_dir = tmp_path / "public-staging"
    infra.write_text(json.dumps(_infra()))
    preflight.write_text(json.dumps(_preflight()))
    render_deploy.write_text(json.dumps(_render_deploy()))
    image_manifest.write_text(json.dumps(_image_manifest()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_infra_reports.py",
            f"--input={infra}",
            f"--preflight={preflight}",
            f"--render-deploy={render_deploy}",
            f"--image-manifest={image_manifest}",
            f"--output-dir={output_dir}",
            f"--summary-output={tmp_path / 'summary.json'}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verdict: **pass**" in (output_dir / "02-dns-tls-edge.md").read_text()
    assert "Verdict: **pass**" in (output_dir / "03-cloudflare-access.md").read_text()
    assert "Verdict: **pass**" in (output_dir / "04-render-services.md").read_text()
    assert "Verdict: **pass**" in (output_dir / "05-migration-version.md").read_text()


def _infra() -> dict:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "dns_tls_edge": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Cloudflare DNS and public preflight",
            "allow_hsts_subdomains": False,
            "checks": {
                "dns_record_documented": True,
                "tls_certificate_documented": True,
                "https_redirect_documented": True,
                "trusted_hosts_configured": True,
                "allowed_origins_configured": True,
                "public_base_url_configured": True,
                "staging_hsts_scope_reviewed": True,
            },
        },
        "cloudflare_access": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Cloudflare Access policy and public probes",
            "provider": "Cloudflare Access",
            "unauthenticated_status": 302,
            "service_token_status": 200,
            "oasis_auth_status": 200,
            "header_names_only": True,
            "checks": {
                "enabled": True,
                "policy_allowlist": True,
                "unauthenticated_denied": True,
                "service_token_probe": True,
                "oasis_auth_inside_boundary": True,
                "registration_allowlist": True,
                "hidden_url_not_only_control": True,
                "access_logs_reviewed": True,
                "waf_or_rate_rules": True,
            },
        },
        "render_services": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Render services dashboard, deploy logs, and environment group names",
            "checks": {
                "api_service": True,
                "worker_service": True,
                "managed_postgres": True,
                "private_database_connectivity": True,
                "postgres_tls": True,
                "postgres_backups": True,
                "secrets_provider_managed": True,
                "secret_values_redacted": True,
                "required_env_present": True,
                "smtp_configured": True,
                "s3_storage_configured": True,
                "object_storage_private": True,
                "api_worker_separate_commands": True,
                "api_worker_same_image": True,
                "api_worker_same_commit": True,
                "health_checks_configured": True,
                "rollback_available": True,
                "logs_available": True,
                "no_sqlite_fallback": True,
            },
        },
        "migration": {
            "captured_at": "2026-07-25T00:00:00Z",
            "source": "Render API predeploy log and server.migration_check JSON",
            "expected_revision": "29995ef61d8e",
            "current_revision": ["29995ef61d8e"],
            "database_url_redacted": True,
            "checks": {
                "predeploy_ran": True,
                "alembic_upgrade_head": True,
                "migration_check_ok": True,
                "predeploy_before_worker": True,
                "database_engine_postgresql": True,
                "no_sqlite_fallback": True,
                "deployed_version_checked": True,
                "failure_stops_release": True,
            },
        },
    }


def _preflight() -> dict:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "verdict": "pass",
        "base_url": "https://staging.example.com",
        "url": {"scheme": "https", "hostname": "staging.example.com", "port": 443},
        "auth_header_names_sent": ["CF-Access-Client-Id", "CF-Access-Client-Secret"],
        "dns": {"ok": True, "addresses": ["203.0.113.10"]},
        "tls": {"ok": True, "issuer_common_name": "WE1"},
        "http_to_https_redirect": {"status": 301},
        "endpoints": {
            "/index.html": {
                "ok": True,
                "status": 200,
                "headers": {
                    "x-content-type-options": "nosniff",
                    "referrer-policy": "strict-origin",
                    "content-security-policy": "default-src 'self'",
                    "strict-transport-security": "max-age=31536000",
                },
            },
            "/healthz": {"ok": True, "status": 200, "headers": {}},
            "/readyz": {"ok": True, "status": 200, "headers": {}},
            "/version": {"ok": True, "status": 200, "headers": {}, "body_text": '{"commit":"abcdef123456"}'},
        },
    }


def _render_deploy() -> dict:
    image = f"ghcr.io/example/oasis@{DIGEST}"
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "verdict": "pass",
        "image_url": image,
        "deployments": [
            {"role": "api", "ok": True, "terminal": True, "deploy_id": "dep-api", "service_id_sha256_16": "a" * 16},
            {"role": "worker", "ok": True, "terminal": True, "deploy_id": "dep-worker", "service_id_sha256_16": "b" * 16},
        ],
    }


def _image_manifest() -> dict:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "verdict": "pass",
        "commit": "abcdef123456",
        "image": f"ghcr.io/example/oasis@{DIGEST}",
        "digest": DIGEST,
        "migration_check": "pass",
    }

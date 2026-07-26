"""Strict public-staging evidence audit regressions."""
from __future__ import annotations

import json
from pathlib import Path

import scripts.public_staging_gate_audit as audit
from scripts.public_staging_deployment_report import build_payload as build_deployment_payload
from scripts.public_staging_infra_reports import build_payload as build_infra_payload
from scripts.public_staging_licensing_report import build_payload as build_licensing_payload
from scripts.public_staging_ops_reports import build_payload as build_ops_payload
from scripts.public_staging_rate_limit_report import build_payload as build_rate_limit_payload
from scripts.public_staging_storage_report import build_payload as build_storage_payload
from test_public_staging_deployment_report import (
    _image_manifest as deployment_image_manifest,
    _preflight as deployment_preflight,
    _render_deploy as deployment_render_deploy,
    _run as deployment_run,
    _workflow_text as deployment_workflow_text,
)
from test_public_staging_infra_reports import (
    _image_manifest as infra_image_manifest,
    _infra as infra_evidence,
    _preflight as infra_preflight,
    _render_deploy as infra_render_deploy,
)
from test_public_staging_licensing_report import (
    _browser_map_summary as licensing_browser_map_summary,
    _evidence as licensing_evidence,
)
from test_public_staging_ops_reports import _evidence as ops_evidence
from test_public_staging_rate_limit_report import (
    _evidence as rate_limit_evidence,
    _preflight as rate_limit_preflight,
    _route_security as rate_limit_route_security,
)
from test_public_staging_storage_report import (
    _evidence as storage_evidence,
    _infra_summary as storage_infra_summary,
    _ops_summary as storage_ops_summary,
)


DIGEST = "sha256:" + "a" * 64


def test_markdown_evidence_without_pass_verdict_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "09-route-security.md").write_text("# Route Security\n\nFindings captured.\n")

    result = audit.evaluate("route", "Route security", ["09-route-security.md"])

    assert result["status"] == "weak"
    assert "missing Markdown pass verdict" in result["weak"][0]


def test_markdown_evidence_with_investigate_verdict_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text(
        "# Performance\n\nVerdict: **investigate**\n\nThis generated report contains sanitized evidence only.\n"
    )

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "weak"
    assert "markdown verdict=**investigate**" in result["weak"][0]


def test_generated_markdown_evidence_with_pass_verdict_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text(_performance_report())

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_handwritten_markdown_pass_without_generated_marker_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text("# Performance\n\nVerdict: **pass**\n")

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "weak"
    assert "missing generated report marker" in result["weak"][0]


def test_markdown_evidence_with_authorization_value_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text(
        _performance_report()
        + "\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n\n"
    )

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "weak"
    assert any("authorization header value is present" in item for item in result["weak"])


def test_generated_markdown_pass_with_missing_expected_sections_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text(
        "# Public Staging Performance Evidence\n\n"
        "Verdict: **pass**\n\n"
        "This generated report contains sanitized evidence only.\n"
    )

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "weak"
    assert any("missing generated report content: ## Browser Flows" in item for item in result["weak"])
    assert any("missing generated report content: ## DNS And TLS" in item for item in result["weak"])


def test_non_evidence_docs_do_not_need_generated_marker(tmp_path, monkeypatch):
    _configure_tmp_audit(tmp_path, monkeypatch)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "NOTE.md").write_text("# Note\n")

    result = audit.evaluate("docs", "Docs", ["docs/NOTE.md"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_required_documentation_set_is_proven_when_present(tmp_path, monkeypatch):
    _configure_tmp_audit(tmp_path, monkeypatch)
    _write_required_docs(tmp_path)

    result = audit.evaluate("docs", "Documentation is current", audit.REQUIRED_DOCS)

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_missing_required_adr_keeps_docs_current_missing(tmp_path, monkeypatch):
    _configure_tmp_audit(tmp_path, monkeypatch)
    _write_required_docs(tmp_path)
    (tmp_path / "docs" / "adr" / "0014-deployment-automation.md").unlink()

    result = audit.evaluate("docs", "Documentation is current", audit.REQUIRED_DOCS)

    assert result["status"] == "missing"
    assert "docs/adr/0014-deployment-automation.md" in result["missing"]


def test_required_placeholder_doc_is_weak(tmp_path, monkeypatch):
    _configure_tmp_audit(tmp_path, monkeypatch)
    _write_required_docs(tmp_path)
    (tmp_path / "docs" / "PUBLIC-STAGING-RUNBOOK.md").write_text("# TODO\n")

    result = audit.evaluate("docs", "Documentation is current", audit.REQUIRED_DOCS)

    assert result["status"] == "weak"
    assert any("placeholder" in item for item in result["weak"])


def test_valid_preflight_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(_preflight()))

    result = audit.evaluate("preflight", "Preflight", ["00-public-staging-preflight.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_json_evidence_with_raw_token_value_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    preflight = _preflight()
    preflight["auth"] = {"access_token": "sk_1234567890abcdef1234567890abcdef"}
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(preflight))

    result = audit.evaluate("preflight", "Preflight", ["00-public-staging-preflight.json"])

    assert result["status"] == "weak"
    assert any("secret-like value at auth.access_token" in item for item in result["weak"])


def test_json_evidence_allows_env_names_and_redaction_markers(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    preflight = _preflight()
    preflight["auth_header_names_sent"] = ["CF-Access-Client-Id", "CF-Access-Client-Secret"]
    preflight["auth"] = {
        "client_secret_env": "OASIS_CF_ACCESS_CLIENT_SECRET",
        "access_token": "<redacted>",
    }
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(preflight))

    result = audit.evaluate("preflight", "Preflight", ["00-public-staging-preflight.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_preflight_json_pass_with_unsafe_hsts_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    preflight = _preflight()
    preflight["endpoints"]["/index.html"]["headers"]["strict-transport-security"] = "max-age=31536000; includeSubDomains"
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(preflight))

    result = audit.evaluate("preflight", "Preflight", ["00-public-staging-preflight.json"])

    assert result["status"] == "weak"
    assert any("HSTS includeSubDomains is not allowed" in item for item in result["weak"])


def test_preflight_version_must_match_image_manifest_commit(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    preflight = _preflight()
    preflight["endpoints"]["/version"]["body_text"] = '{"commit":"different"}'
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(preflight))
    (evidence / "01-image-manifest.json").write_text(json.dumps(_image_manifest()))

    result = audit.evaluate("preflight", "Preflight", ["00-public-staging-preflight.json"])

    assert result["status"] == "weak"
    assert any("/version does not include image manifest commit" in item for item in result["weak"])


def test_valid_image_manifest_and_render_deploy_are_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "01-image-manifest.json").write_text(json.dumps(_image_manifest()))
    (evidence / "02-render-deploy.json").write_text(json.dumps(_render_deploy()))

    result = audit.evaluate("deploy", "Deploy", ["01-image-manifest.json", "02-render-deploy.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_valid_auth_email_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "auth-email-summary.json").write_text(json.dumps(_auth_email_summary()))

    result = audit.evaluate("auth", "Auth email", ["auth-email-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_auth_email_summary_requires_reset_cookie_and_csrf_evidence(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = _auth_email_summary()
    summary["rows"]["password_reset_complete_status"] = 400
    summary["rows"]["session_cookie_httponly"] = False
    summary["rows"]["csrf_rejection_status"] = 200
    (evidence / "auth-email-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("auth", "Auth email", ["auth-email-summary.json"])

    assert result["status"] == "weak"
    assert any("password_reset_complete_status is not 200" in item for item in result["weak"])
    assert any("session_cookie_httponly is not True" in item for item in result["weak"])
    assert any("csrf_rejection_status is not 403" in item for item in result["weak"])


def test_valid_browser_map_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "browser-map-summary.json").write_text(json.dumps(_browser_map_summary()))

    result = audit.evaluate("browser", "Browser map", ["browser-map-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_browser_map_summary_requires_browser_and_provider_checks(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = _browser_map_summary()
    summary["browser"]["rows"][0]["failed_checks"] = ["three_map_slots"]
    summary["browser"]["network_rows"][0]["requested_bulk"] = True
    summary["map_provider"]["observed_external_hosts"].append("unexpected.example")
    summary["map_provider"]["rows"][0]["value"] = False
    (evidence / "browser-map-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("browser", "Browser map", ["browser-map-summary.json"])

    assert result["status"] == "weak"
    assert any("browser has failed checks: chrome" in item for item in result["weak"])
    assert any("first paint requested /api/universe/bulk" in item for item in result["weak"])
    assert any("observed unexpected external host: unexpected.example" in item for item in result["weak"])
    assert any("provider check is not true: vendored_maplibre" in item for item in result["weak"])


def test_valid_performance_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "performance-evidence-summary.json").write_text(json.dumps(_performance_summary()))

    result = audit.evaluate("performance", "Performance", ["performance-evidence-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_performance_summary_requires_proxyman_and_app_layer_rows(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = _performance_summary()
    summary["target"]["proxy_server"] = ""
    summary["browser"]["direct_comparison_present"] = False
    summary["auth_map_slot"]["rows"] = summary["auth_map_slot"]["rows"][:1]
    (evidence / "performance-evidence-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("performance", "Performance", ["performance-evidence-summary.json"])

    assert result["status"] == "weak"
    assert any("Proxyman proxy is not recorded" in item for item in result["weak"])
    assert any("direct network comparison is missing" in item for item in result["weak"])
    assert any("missing map-slot read app-layer latency" in item for item in result["weak"])
    assert any("missing map-slot write app-layer latency" in item for item in result["weak"])


def test_valid_route_security_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "route-security-summary.json").write_text(json.dumps(_route_security_summary()))

    result = audit.evaluate("route", "Route security", ["route-security-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_route_security_summary_requires_auth_inventory_and_headers(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = _route_security_summary()
    summary["warnings"] = ["stale conflict was not measured"]
    summary["preflight"]["index_headers"].remove("permissions-policy")
    summary["inventory"]["class_summary"]["public-write-auth-flow-rate-limited"] = 4
    summary["auth_security"]["csrf_rejection_status"] = 200
    (evidence / "route-security-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("route", "Route security", ["route-security-summary.json"])

    assert result["status"] == "weak"
    assert any("has warnings" in item for item in result["weak"])
    assert any("missing header evidence: permissions-policy" in item for item in result["weak"])
    assert any("rate-limited public auth-flow class count is not 5" in item for item in result["weak"])
    assert any("CSRF rejection status is not 403" in item for item in result["weak"])


def test_valid_ops_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "ops-evidence-summary.json").write_text(json.dumps(build_ops_payload(ops_evidence())))

    result = audit.evaluate("ops", "Operations", ["ops-evidence-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_ops_summary_requires_worker_network_restore_rollback_and_alerts(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_ops_payload(ops_evidence())
    _set_ops_row(summary, "worker_jobs", "worker_restart_recovery", False)
    _set_ops_row(summary, "network_isolation", "api_no_sec", False)
    _set_ops_row(summary, "backup_restore", "restore_separate_database", False)
    _set_ops_row(summary, "failure_rollback", "api_rollback", False)
    _set_ops_row(summary, "observability_alerts", "alert.api_readiness_failure", False)
    (evidence / "ops-evidence-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("ops", "Operations", ["ops-evidence-summary.json"])

    assert result["status"] == "weak"
    assert any("worker_jobs required check is not true: worker_restart_recovery" in item for item in result["weak"])
    assert any("network_isolation required check is not true: api_no_sec" in item for item in result["weak"])
    assert any("backup_restore required check is not true: restore_separate_database" in item for item in result["weak"])
    assert any("failure_rollback required check is not true: api_rollback" in item for item in result["weak"])
    assert any("observability_alerts required check is not true: alert.api_readiness_failure" in item for item in result["weak"])


def test_valid_infra_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_infra_payload(infra_evidence(), infra_preflight(), infra_render_deploy(), infra_image_manifest())
    (evidence / "infra-evidence-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("infra", "Infrastructure", ["infra-evidence-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_infra_summary_requires_dns_access_render_and_migration_sections(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_infra_payload(infra_evidence(), infra_preflight(), infra_render_deploy(), infra_image_manifest())
    summary["results"]["dns_tls_edge"]["verdict"] = "investigate"
    _set_infra_row(summary, "dns_tls_edge", "TLS ok", False)
    summary["results"]["cloudflare_access"]["failures"] = ["service-token probe did not return 200"]
    _set_infra_row(summary, "cloudflare_access", "service-token status", 403)
    summary["results"]["render_services"]["rows"] = [
        row for row in summary["results"]["render_services"]["rows"]
        if row.get("label") != "Render managed PostgreSQL exists"
    ]
    summary["results"]["migration_version"]["rows"] = [
        row for row in summary["results"]["migration_version"]["rows"]
        if row.get("label") != "DATABASE_URL redacted"
    ]
    _set_infra_row(summary, "migration_version", "current revision", "deadbeef")
    (evidence / "infra-evidence-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("infra", "Infrastructure", ["infra-evidence-summary.json"])

    assert result["status"] == "weak"
    assert any("dns_tls_edge verdict is not pass" in item for item in result["weak"])
    assert any("dns_tls_edge TLS ok is not True" in item for item in result["weak"])
    assert any("cloudflare_access has failures" in item for item in result["weak"])
    assert any("cloudflare_access service-token status is not 200" in item for item in result["weak"])
    assert any("render_services missing row: Render managed PostgreSQL exists" in item for item in result["weak"])
    assert any("migration_version missing row: DATABASE_URL redacted" in item for item in result["weak"])
    assert any("migration_version current revision is not 29995ef61d8e" in item for item in result["weak"])


def test_valid_deployment_automation_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_deployment_payload(
        workflow_text=deployment_workflow_text(),
        run=deployment_run(),
        image_manifest=deployment_image_manifest(),
        render_deploy=deployment_render_deploy(),
        preflight=deployment_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )
    (evidence / "deployment-automation-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("deployment", "Deployment automation", ["deployment-automation-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_deployment_automation_summary_requires_run_and_artifact_checks(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_deployment_payload(
        workflow_text=deployment_workflow_text(),
        run=deployment_run(),
        image_manifest=deployment_image_manifest(),
        render_deploy=deployment_render_deploy(),
        preflight=deployment_preflight(),
        workflow_path=".github/workflows/deploy.yml",
    )
    summary["target"]["environment"] = "production"
    summary["warnings"] = ["workflow run audit trail was incomplete"]
    _set_deployment_row(summary, "run", "manual_approval", False)
    _set_deployment_row(summary, "artifacts", "render_image_matches_manifest", False)
    (evidence / "deployment-automation-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("deployment", "Deployment automation", ["deployment-automation-summary.json"])

    assert result["status"] == "weak"
    assert any("deployment automation environment is not staging" in item for item in result["weak"])
    assert any("deployment automation summary has warnings" in item for item in result["weak"])
    assert any("run required check is not true: manual_approval" in item for item in result["weak"])
    assert any("artifacts required check is not true: render_image_matches_manifest" in item for item in result["weak"])


def test_valid_licensing_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_licensing_payload(
        licensing_evidence(),
        licensing_browser_map_summary(),
        input_path="licensing-evidence.json",
        browser_map_path="browser-map-summary.json",
    )
    (evidence / "licensing-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("licensing", "Licensing", ["licensing-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_licensing_summary_requires_disabled_providers_and_browser_checks(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_licensing_payload(
        licensing_evidence(),
        licensing_browser_map_summary(),
        input_path="licensing-evidence.json",
        browser_map_path="browser-map-summary.json",
    )
    summary["providers"]["rows"][0]["failures"] = ["terms review missing"]
    _set_licensing_row(summary, "feature_flags", "OASIS_FEATURE_LOGOS", False)
    _set_licensing_row(summary, "browser_map", "disabled_providers_unused", False)
    (evidence / "licensing-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("licensing", "Licensing", ["licensing-summary.json"])

    assert result["status"] == "weak"
    assert any("provider has failures" in item for item in result["weak"])
    assert any("feature flag check is not true: OASIS_FEATURE_LOGOS" in item for item in result["weak"])
    assert any("browser/map check is not true: disabled_providers_unused" in item for item in result["weak"])


def test_valid_rate_limit_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_rate_limit_payload(
        rate_limit_evidence(),
        rate_limit_route_security(),
        rate_limit_preflight(),
        input_path="rate-limit-evidence.json",
        route_security_path="route-security-summary.json",
        preflight_path="00-public-staging-preflight.json",
    )
    (evidence / "rate-limit-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("rate-limit", "Rate limiting", ["rate-limit-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_rate_limit_summary_requires_edge_client_ip_and_route_family_checks(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_rate_limit_payload(
        rate_limit_evidence(),
        rate_limit_route_security(),
        rate_limit_preflight(),
        input_path="rate-limit-evidence.json",
        route_security_path="route-security-summary.json",
        preflight_path="00-public-staging-preflight.json",
    )
    _set_rate_limit_row(summary, "edge_controls", "waf_or_rate_rules_enabled", False)
    _set_rate_limit_row(summary, "client_ip", "spoofed_forwarded_for_rejected_or_ignored", False)
    _set_rate_limit_row(summary, "route_families", "exports", False)
    (evidence / "rate-limit-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("rate-limit", "Rate limiting", ["rate-limit-summary.json"])

    assert result["status"] == "weak"
    assert any("edge_controls required check is not true: waf_or_rate_rules_enabled" in item for item in result["weak"])
    assert any("client_ip required check is not true: spoofed_forwarded_for_rejected_or_ignored" in item for item in result["weak"])
    assert any("route_families required check is not true: exports" in item for item in result["weak"])


def test_valid_storage_summary_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_storage_payload(
        storage_evidence(),
        storage_infra_summary(),
        storage_ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )
    (evidence / "storage-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("storage", "Object storage", ["storage-summary.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_storage_summary_requires_access_validation_failure_and_cross_checks(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    summary = build_storage_payload(
        storage_evidence(),
        storage_infra_summary(),
        storage_ops_summary(),
        input_path="storage-evidence.json",
        infra_path="infra-evidence-summary.json",
        ops_path="ops-evidence-summary.json",
    )
    _set_storage_row(summary, "access_controls", "public_bucket_listing_disabled", False)
    _set_storage_row(summary, "validation_limits", "content_type_validation", False)
    _set_storage_row(summary, "failure_behavior", "partial_output_not_offered", False)
    _set_storage_row(summary, "cross_checks", "ops_storage_summary_pass", False)
    (evidence / "storage-summary.json").write_text(json.dumps(summary))

    result = audit.evaluate("storage", "Object storage", ["storage-summary.json"])

    assert result["status"] == "weak"
    assert any("access_controls required check is not true: public_bucket_listing_disabled" in item for item in result["weak"])
    assert any("validation_limits required check is not true: content_type_validation" in item for item in result["weak"])
    assert any("failure_behavior required check is not true: partial_output_not_offered" in item for item in result["weak"])
    assert any("cross_checks required check is not true: ops_storage_summary_pass" in item for item in result["weak"])


def test_image_manifest_json_pass_with_latest_tag_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    manifest = _image_manifest()
    manifest["image"] = "ghcr.io/example/oasis:latest"
    (evidence / "01-image-manifest.json").write_text(json.dumps(manifest))

    result = audit.evaluate("image", "Image", ["01-image-manifest.json"])

    assert result["status"] == "weak"
    assert any("image is not digest pinned" in item for item in result["weak"])
    assert any("image uses latest" in item for item in result["weak"])


def test_render_deploy_json_pass_without_worker_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "01-image-manifest.json").write_text(json.dumps(_image_manifest()))
    deploy = _render_deploy()
    deploy["deployments"] = [deploy["deployments"][0]]
    (evidence / "02-render-deploy.json").write_text(json.dumps(deploy))

    result = audit.evaluate("deploy", "Deploy", ["02-render-deploy.json"])

    assert result["status"] == "weak"
    assert any("roles must be exactly api and worker" in item for item in result["weak"])


def test_render_deploy_json_pass_without_migration_sequence_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "01-image-manifest.json").write_text(json.dumps(_image_manifest()))
    deploy = _render_deploy()
    deploy["sequence"] = ["deploy API image", "deploy worker image"]
    (evidence / "02-render-deploy.json").write_text(json.dumps(deploy))

    result = audit.evaluate("deploy", "Deploy", ["02-render-deploy.json"])

    assert result["status"] == "weak"
    assert any("sequence missing alembic upgrade head" in item for item in result["weak"])
    assert any("sequence missing server.migration_check" in item for item in result["weak"])
    assert any("sequence missing before worker" in item for item in result["weak"])


def _configure_tmp_audit(tmp_path: Path, monkeypatch) -> Path:
    evidence = tmp_path / "docs" / "evidence" / "public-staging"
    evidence.mkdir(parents=True)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "EVIDENCE", evidence)
    return evidence


def _set_ops_row(summary: dict, section: str, key: str, value: bool) -> None:
    for row in summary["results"][section]["rows"]:
        if row.get("key") == key:
            row["value"] = value
            return
    raise AssertionError(f"missing ops summary row: {section}.{key}")


def _set_infra_row(summary: dict, section: str, label: str, value: object) -> None:
    for row in summary["results"][section]["rows"]:
        if row.get("label") == label:
            row["value"] = value
            return
    raise AssertionError(f"missing infra summary row: {section}.{label}")


def _set_deployment_row(summary: dict, section: str, key: str, value: bool) -> None:
    for row in summary[section]["rows"]:
        if row.get("key") == key:
            row["value"] = value
            return
    raise AssertionError(f"missing deployment summary row: {section}.{key}")


def _set_licensing_row(summary: dict, section: str, key: str, value: bool) -> None:
    for row in summary[section]["rows"]:
        if row.get("key") == key:
            row["value"] = value
            return
    raise AssertionError(f"missing licensing summary row: {section}.{key}")


def _set_rate_limit_row(summary: dict, section: str, key: str, value: bool) -> None:
    for row in summary[section]["rows"]:
        if row.get("key") == key:
            row["value"] = value
            return
    raise AssertionError(f"missing rate-limit summary row: {section}.{key}")


def _set_storage_row(summary: dict, section: str, key: str, value: bool) -> None:
    for row in summary[section]["rows"]:
        if row.get("key") == key:
            row["value"] = value
            return
    raise AssertionError(f"missing storage summary row: {section}.{key}")


def _write_required_docs(tmp_path: Path) -> None:
    for name in audit.REQUIRED_DOCS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n\nRequired Phase 1.75 public staging documentation.\n")


def _performance_report() -> str:
    return (
        "# Public Staging Performance Evidence\n\n"
        "Verdict: **pass**\n\n"
        "## Browser Flows\n\n"
        "| Flow | Requests |\n"
        "|---|---:|\n"
        "| first-paint | 4 |\n\n"
        "## DNS And TLS\n\n"
        "- Preflight verdict: `pass`\n\n"
        "This generated report contains sanitized evidence only.\n"
    )


def _auth_email_summary() -> dict:
    return {
        "verdict": "pass",
        "failures": [],
        "auth_captured_at": "2026-07-25T00:00:00Z",
        "auth_base_url": "https://staging.example.com",
        "rows": {
            "user_a_registration_status": 201,
            "user_a_verification_token_supplied": True,
            "user_a_verification_status": 200,
            "user_a_login_status": 200,
            "user_b_registration_status": 201,
            "user_b_verification_token_supplied": True,
            "user_b_verification_status": 200,
            "user_b_login_status": 200,
            "password_reset_request_status": 200,
            "password_reset_token_supplied": True,
            "password_reset_complete_status": 200,
            "post_reset_login_status": 200,
            "session_cookie_secure": True,
            "session_cookie_httponly": True,
            "csrf_cookie_secure": True,
            "csrf_rejection_status": 403,
        },
    }


def _browser_map_summary() -> dict:
    browser_checks = {
        "application_shell": True,
        "registration_login": True,
        "session_persistence": True,
        "standard_basemap": True,
        "dark_basemap": True,
        "satellite_disabled_or_failure": True,
        "geographic_features": True,
        "search": True,
        "entity_selection": True,
        "drawer_rail": True,
        "three_map_slots": True,
        "export_workflow": True,
        "password_reset": True,
        "logout": True,
        "responsive_layout": True,
        "keyboard_navigation": True,
        "basic_accessibility": True,
        "no_console_errors": True,
    }
    browser_rows = [
        {
            "key": key,
            "name": key,
            "browser_version": version,
            "os": os_name,
            "os_version": os_version,
            "available": available,
            "unavailable_reason": reason,
            "failed_checks": [] if available else [],
            "checks": browser_checks if available else {},
        }
        for key, version, os_name, os_version, available, reason in [
            ("chrome", "150.0", "macOS", "26.5.2", True, ""),
            ("edge_or_brave", "150.0", "macOS", "26.5.2", True, ""),
            ("firefox", "142.0", "macOS", "26.5.2", True, ""),
            ("safari_macos", "19.0", "macOS", "26.5.2", True, ""),
            ("mobile_safari", "", "iOS", "", False, "device unavailable for first public drill"),
            ("chrome_android", "", "Android", "", False, "device unavailable for first public drill"),
        ]
    ]
    return {
        "target": {
            "matrix_base_url": "https://staging.example.com",
            "summary_base_url": "https://staging.example.com",
        },
        "browser": {
            "verdict": "pass",
            "failures": [],
            "rows": browser_rows,
            "network_rows": [
                {
                    "name": "26-public-staging-03-local-first-paint",
                    "flow": "cold first paint",
                    "requested_bulk": False,
                    "requested_unpkg": False,
                    "console_errors": 0,
                    "failed_requests": 0,
                    "external_hosts": [],
                },
                {
                    "name": "26-public-staging-06-map-interaction",
                    "flow": "map interaction",
                    "requested_bulk": False,
                    "requested_unpkg": False,
                    "console_errors": 0,
                    "failed_requests": 0,
                    "external_hosts": ["tiles.openfreemap.org"],
                },
            ],
        },
        "map_provider": {
            "verdict": "pass",
            "failures": [],
            "approved_hosts": ["tiles.openfreemap.org"],
            "observed_external_hosts": ["tiles.openfreemap.org"],
            "rows": [
                {"key": "vendored_maplibre", "value": True},
                {"key": "no_unpkg", "value": True},
                {"key": "no_provider_credentials", "value": True},
                {"key": "attribution_displayed", "value": True},
                {"key": "standard_available", "value": True},
                {"key": "disabled_providers_unused", "value": True},
                {"key": "preferred_basemap_preserved_after_failure", "value": True},
                {"key": "style_requests_expected", "value": True},
                {"key": "tile_requests_expected", "value": True},
                {"key": "terrain_requests_expected_or_disabled", "value": True},
                {"key": "csp_ok", "value": True},
                {"key": "cors_ok", "value": True},
            ],
        },
    }


def _performance_summary() -> dict:
    return {
        "verdict": "pass",
        "failures": [],
        "warnings": [],
        "target": {
            "base_url": "https://staging.example.com",
            "proxy_server": "http://127.0.0.1:9090",
        },
        "browser": {
            "direct_comparison_present": True,
            "flows": [
                {
                    "name": "26-public-staging-03-local-first-paint",
                    "flow": "cold first paint",
                    "bulk": False,
                    "unpkg": False,
                    "console_errors": 0,
                    "failed_requests": 0,
                },
                {
                    "name": "26-public-staging-05-local-search-intent",
                    "flow": "search intent and bulk load",
                    "bulk": True,
                    "unpkg": False,
                    "console_errors": 0,
                    "failed_requests": 0,
                },
            ],
        },
        "preflight": {
            "verdict": "pass",
            "dns_ms": 12.3,
            "tls_ms": 44.5,
        },
        "auth_map_slot": {
            "rows": [
                {"name": "session validation GET /api/auth/me", "p95_ms": 10, "target_met": True},
                {"name": "map-slot read GET /api/map-slots/{id}", "p95_ms": 20, "target_met": True},
                {"name": "map-slot write PUT /api/map-slots/{id}", "p95_ms": 30, "target_met": True},
            ],
        },
        "route_probe": {
            "verdict": "pass",
            "rows": [
                {
                    "name": "entity comps",
                    "method": "GET",
                    "template": "/api/entity/{entity_id}/comps",
                    "p95_ms": 150,
                    "ok": True,
                }
            ],
        },
    }


def _route_security_summary() -> dict:
    return {
        "verdict": "pass",
        "failures": [],
        "warnings": [],
        "route_probe": {
            "verdict": "pass",
            "failure_count": 0,
            "summary": {
                "count": 4,
                "families": {"health": 1, "auth/map slots": 3},
                "unauthenticated": [
                    {
                        "name": "map slots unauthenticated",
                        "template": "/api/map-slots",
                        "status_codes": [401],
                        "ok": True,
                    },
                    {
                        "name": "auth me unauthenticated",
                        "template": "/api/auth/me",
                        "status_codes": [401],
                        "ok": True,
                    },
                    {
                        "name": "auth sessions unauthenticated",
                        "template": "/api/auth/sessions",
                        "status_codes": [403],
                        "ok": True,
                    },
                ],
            },
        },
        "preflight": {
            "verdict": "pass",
            "index_headers": [
                "content-security-policy",
                "permissions-policy",
                "referrer-policy",
                "strict-transport-security",
                "x-content-type-options",
            ],
        },
        "inventory": {
            "unique_method_paths": 92,
            "class_summary": {
                "public-read": 61,
                "owner-only-session-csrf": 6,
                "public-write-auth-flow-rate-limited": 5,
            },
        },
        "auth_security": {
            "verdict": "pass",
            "csrf_rejection_status": 403,
            "cross_user_status": 404,
            "stale_conflict_status": 409,
            "default_map_slot_count": 3,
            "default_map_slot_numbers": [1, 2, 3],
        },
    }


def _preflight() -> dict:
    return {
        "verdict": "pass",
        "base_url": "https://staging.example.com",
        "url": {"scheme": "https", "hostname": "staging.example.com"},
        "dns": {"ok": True},
        "tls": {"ok": True},
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


def _image_manifest() -> dict:
    return {
        "verdict": "pass",
        "commit": "abcdef123456",
        "image": f"ghcr.io/example/oasis@{DIGEST}",
        "image_name": "ghcr.io/example/oasis",
        "digest": DIGEST,
        "registry": "ghcr.io",
        "architecture": "linux/amd64",
        "checks": {
            "migration_validation": "pass",
            "python_tests": "pass",
            "playwright_tests": "pass",
            "image_scan": "pass",
            "sbom": "present",
            "provenance": "present",
        },
    }


def _render_deploy() -> dict:
    return {
        "verdict": "pass",
        "image_url": f"ghcr.io/example/oasis@{DIGEST}",
        "sequence": [
            "deploy API image with Render preDeployCommand",
            "Render preDeployCommand runs alembic upgrade head",
            "Render preDeployCommand runs server.migration_check against the deployed database",
            "wait for API deploy terminal success before worker deploy",
            "deploy worker image",
            "wait for worker deploy terminal success",
        ],
        "deployments": [
            {
                "role": "api",
                "ok": True,
                "terminal": True,
                "timed_out": False,
                "deploy_id": "dep-api",
                "service_id_sha256_16": "a" * 16,
            },
            {
                "role": "worker",
                "ok": True,
                "terminal": True,
                "timed_out": False,
                "deploy_id": "dep-worker",
                "service_id_sha256_16": "b" * 16,
            },
        ],
    }

"""Strict public-staging evidence audit regressions."""
from __future__ import annotations

import json
from pathlib import Path

import scripts.public_staging_gate_audit as audit


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

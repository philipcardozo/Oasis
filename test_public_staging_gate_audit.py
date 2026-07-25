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
    (evidence / "15-performance.md").write_text(
        "# Performance\n\nVerdict: **pass**\n\nThis generated report contains sanitized evidence only.\n"
    )

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_handwritten_markdown_pass_without_generated_marker_is_weak(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "15-performance.md").write_text("# Performance\n\nVerdict: **pass**\n")

    result = audit.evaluate("performance", "Performance", ["15-performance.md"])

    assert result["status"] == "weak"
    assert "missing generated report marker" in result["weak"][0]


def test_non_evidence_docs_do_not_need_generated_marker(tmp_path, monkeypatch):
    _configure_tmp_audit(tmp_path, monkeypatch)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "PHASE-1-75-PUBLIC-STAGING.md").write_text("# Phase\n")

    result = audit.evaluate("docs", "Docs", ["docs/PHASE-1-75-PUBLIC-STAGING.md"])

    assert result["status"] == "proven"
    assert result["weak"] == []


def test_valid_preflight_json_evidence_is_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "00-public-staging-preflight.json").write_text(json.dumps(_preflight()))

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


def test_valid_image_manifest_and_render_deploy_are_proven(tmp_path, monkeypatch):
    evidence = _configure_tmp_audit(tmp_path, monkeypatch)
    (evidence / "01-image-manifest.json").write_text(json.dumps(_image_manifest()))
    (evidence / "02-render-deploy.json").write_text(json.dumps(_render_deploy()))

    result = audit.evaluate("deploy", "Deploy", ["01-image-manifest.json", "02-render-deploy.json"])

    assert result["status"] == "proven"
    assert result["weak"] == []


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


def _configure_tmp_audit(tmp_path: Path, monkeypatch) -> Path:
    evidence = tmp_path / "docs" / "evidence" / "public-staging"
    evidence.mkdir(parents=True)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "EVIDENCE", evidence)
    return evidence


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

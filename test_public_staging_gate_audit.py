"""Strict public-staging evidence audit regressions."""
from __future__ import annotations

from pathlib import Path

import scripts.public_staging_gate_audit as audit


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


def _configure_tmp_audit(tmp_path: Path, monkeypatch) -> Path:
    evidence = tmp_path / "docs" / "evidence" / "public-staging"
    evidence.mkdir(parents=True)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "EVIDENCE", evidence)
    return evidence
